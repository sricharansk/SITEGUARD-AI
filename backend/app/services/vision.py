"""Vision analysis of image evidence (Playbook Prompts 25-27; docs/AGENTS.md#vision; DECISIONS 020).

Pipeline: check the stored file against its recorded SHA-256 -> decode, orient, strip metadata and measure image
quality in a resource-limited child process -> run the configured analyzer with the labels for the task -> apply
project/site calibrated thresholds -> store every detection as an observation with its provenance.

Observations are machine output for human review. They are never proof that a hazard, defect or breach exists, and
the absence of an observation never means the absence of a hazard. Agents use CONFIRMED observations as validated
facts and list UNREVIEWED ones as open questions.
"""

import base64
import hashlib
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.vision import AnalyzerOutput, LabelSpec, PreparedImage, VisionAnalyzer, get_analyzer
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound
from app.models import (
    Evidence,
    Incident,
    ObservationReview,
    VisionAnalysis,
    VisionCalibration,
    VisionObservation,
    VisionTask,
    utcnow,
)
from app.services import audit
from app.services import evidence as evidence_store
from app.services.isolation import WorkerCrashed, WorkerTimeout, run_worker

TAXONOMY_VERSION = "2026.10-1"
DEFAULT_THRESHOLD = 0.5
DISCLAIMER = (
    "Machine-generated visual observations for human review. They are not proof that a hazard, defect or "
    "non-compliance exists, and no observation does not mean no hazard or defect."
)
IMAGE_TYPES = {"image/jpeg": "JPEG", "image/png": "PNG"}


@dataclass(frozen=True)
class VisionClass:
    label: str
    name: str
    category: str  # PPE | HAZARD | DEFECT
    description: str  # what an analyzer must look for
    maps_to: str | None  # hazard or defect label in the agents' taxonomy (agents/rules.py), if any

    @property
    def task(self) -> VisionTask:
        return VisionTask.DEFECT if self.category == "DEFECT" else VisionTask.PPE_HAZARD


_PPE = "Missing or incorrect PPE"
_FALL = "Fall from height"
_WATER = "Water ingress / waterproofing"
CLASSES: tuple[VisionClass, ...] = (
    VisionClass("no_hard_hat", "Person without a hard hat", "PPE", "A person on site whose head is uncovered", _PPE),
    VisionClass(
        "no_hi_vis", "Person without high-visibility clothing", "PPE", "A person on site without a hi-vis vest", _PPE
    ),
    VisionClass(
        "no_harness_at_height",
        "Person at height without a visible harness",
        "PPE",
        "A person at an edge, on a roof, scaffold or MEWP with no harness or lanyard visible",
        _FALL,
    ),
    VisionClass(
        "no_eye_protection",
        "Person cutting, grinding or welding without eye protection",
        "PPE",
        "A person doing hot work or cutting with no glasses, goggles or visor visible",
        _PPE,
    ),
    VisionClass(
        "unprotected_edge",
        "Unprotected edge",
        "HAZARD",
        "A slab, roof or platform edge with no guardrail, barrier or toe board",
        _FALL,
    ),
    VisionClass(
        "uncovered_opening",
        "Uncovered floor opening",
        "HAZARD",
        "A hole or opening in a floor or deck with no fixed, marked cover",
        _FALL,
    ),
    VisionClass(
        "unsupported_excavation",
        "Unsupported excavation",
        "HAZARD",
        "A trench or excavation without shoring, battering, edge barrier or safe access",
        "Excavation collapse / caught-in",
    ),
    VisionClass(
        "suspended_load_over_people",
        "Suspended load over people",
        "HAZARD",
        "A crane or hoist load above or next to people, or an unattended suspended load",
        "Lifting operation / crane",
    ),
    VisionClass(
        "unsafe_ladder", "Unsafe ladder", "HAZARD", "A ladder that is damaged, unsecured or badly angled", _FALL
    ),
    VisionClass(
        "exposed_electrical",
        "Exposed or damaged electrical equipment",
        "HAZARD",
        "Damaged cables, open panels or exposed conductors",
        "Electrical contact",
    ),
    VisionClass(
        "hot_work_without_controls",
        "Hot work without visible controls",
        "HAZARD",
        "Welding or cutting near combustibles with no screen, fire blanket or extinguisher visible",
        "Fire / hot work",
    ),
    VisionClass(
        "unsecured_materials_at_height",
        "Unsecured materials at height",
        "HAZARD",
        "Loose materials or tools near an edge or on scaffolding that could fall",
        "Struck by falling or moving object",
    ),
    VisionClass(
        "blocked_access_route",
        "Blocked access or escape route",
        "HAZARD",
        "Materials or debris obstructing a walkway, stair or emergency route",
        None,
    ),
    VisionClass("crack", "Crack", "DEFECT", "A visible crack in concrete, masonry or render", "Cracking"),
    VisionClass("spalling", "Spalling", "DEFECT", "Concrete surface that has broken or flaked away", "Cracking"),
    VisionClass(
        "honeycombing",
        "Honeycombing or voids",
        "DEFECT",
        "Voids or exposed coarse aggregate on a formed concrete surface",
        "Concrete honeycombing / voids",
    ),
    VisionClass(
        "exposed_reinforcement",
        "Exposed reinforcement",
        "DEFECT",
        "Reinforcing bars visible at the concrete surface",
        "Reinforcement / cover nonconformance",
    ),
    VisionClass("corrosion", "Corrosion", "DEFECT", "Rust or corrosion staining on steel or reinforcement", None),
    VisionClass(
        "moisture_staining", "Moisture staining", "DEFECT", "Damp patches, water marks or active leaks", _WATER
    ),
    VisionClass(
        "efflorescence", "Efflorescence", "DEFECT", "White salt deposits on concrete or masonry surfaces", _WATER
    ),
)
BY_LABEL = {c.label: c for c in CLASSES}

# Image-quality checks: deterministic warnings that the picture may hide what an analyzer is looking for.
QUALITY_LIMITS = {"min_short_side": 480, "dark_below": 40, "bright_above": 225, "contrast_below": 20, "sharp_below": 8}


def classes_for(task: VisionTask) -> list[VisionClass]:
    return [c for c in CLASSES if c.task == task]


def label_spec(c: VisionClass) -> LabelSpec:
    return LabelSpec(c.label, c.name, c.description)


def quality_flags(width: int, height: int, quality: dict) -> list[str]:
    flags = []
    if min(width, height) < QUALITY_LIMITS["min_short_side"]:
        flags.append("LOW_RESOLUTION")
    if quality["mean_luminance"] < QUALITY_LIMITS["dark_below"]:
        flags.append("TOO_DARK")
    if quality["mean_luminance"] > QUALITY_LIMITS["bright_above"]:
        flags.append("OVEREXPOSED")
    if quality["contrast"] < QUALITY_LIMITS["contrast_below"]:
        flags.append("LOW_CONTRAST")
    if quality["sharpness"] < QUALITY_LIMITS["sharp_below"]:
        flags.append("POSSIBLY_BLURRED")
    return flags


def prepare_image(content: bytes, content_type: str) -> PreparedImage:
    """Decode, orient and re-encode an untrusted image in a resource-limited child process."""
    s = get_settings()
    expected = IMAGE_TYPES.get(content_type)
    if expected is None:
        raise AppError("Vision analysis needs a JPEG or PNG image", "UNSUPPORTED_FILE")
    try:
        result = run_worker(
            "app.services.vision_worker",
            [expected, str(s.vision_max_pixels), str(s.vision_max_side)],
            content,
            timeout=s.vision_timeout_seconds,
            memory_mb=s.vision_memory_mb,
        )
    except WorkerTimeout as exc:
        raise AppError("Image took too long to decode", "IMAGE_UNREADABLE") from exc
    except WorkerCrashed:
        raise AppError("Image could not be decoded within the resource limits", "IMAGE_UNREADABLE") from None
    if not result.get("ok"):
        raise AppError(result.get("error") or "Image could not be decoded", "IMAGE_UNREADABLE")
    quality = dict(result["quality"])
    quality["flags"] = quality_flags(result["width"], result["height"], quality)
    preprocessing = {
        k: result[k] for k in ("format", "original_size", "orientation_corrected", "metadata_removed", "analysis_size")
    }
    return PreparedImage(
        jpeg=base64.b64decode(result["image_b64"]),
        width=result["width"],
        height=result["height"],
        preprocessing=preprocessing,
        quality=quality,
    )


def resolve_thresholds(db: Session, inc: Incident, labels: list[str]) -> dict[str, dict]:
    """Threshold per label: a site calibration beats a project calibration, which beats the default."""
    rows = list(db.scalars(select(VisionCalibration).where(VisionCalibration.project_id == inc.project_id)))
    out = {}
    for label in labels:
        site = next((r for r in rows if r.label == label and r.site_id and r.site_id == inc.site_id), None)
        project = next((r for r in rows if r.label == label and r.site_id is None), None)
        if site:
            out[label] = {"threshold": site.threshold, "source": f"site:{site.site_id}"}
        elif project:
            out[label] = {"threshold": project.threshold, "source": "project"}
        else:
            out[label] = {"threshold": DEFAULT_THRESHOLD, "source": "default"}
    return out


def _clean_box(box: dict | None) -> dict | None:
    """Keep a box only if it is a valid region inside the image; analyzers' coordinates are not trusted."""
    if not box:
        return None
    try:
        x, y, w, h = (float(box[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError):
        return None
    eps = 1e-6
    if min(x, y) < 0 or w <= 0 or h <= 0 or x + w > 1 + eps or y + h > 1 + eps:
        return None
    return {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}


def _limitations(analyzer: VisionAnalyzer, quality: dict, discarded: int, boxes_dropped: int, notes: str) -> list:
    out = [
        "No observation does not mean no hazard or defect: analyzers miss things, and only the listed labels are "
        "looked for."
    ]
    if analyzer.name == "baseline":
        out.append(
            "No detection model is configured (DECISIONS O8), so only image-quality checks ran and no PPE, hazard "
            "or defect detections were attempted."
        )
    if analyzer.name == "anthropic":
        out.append("Confidence is self-reported by the model and boxes are approximate.")
    if quality.get("flags"):
        out.append(f"Image quality may hide details: {', '.join(quality['flags'])}.")
    if discarded:
        out.append(f"{discarded} detection(s) used labels outside the taxonomy and were discarded.")
    if boxes_dropped:
        out.append(f"{boxes_dropped} box(es) were outside the image and were dropped; the labels were kept.")
    if notes:
        out.append(f"Analyzer note (machine text): {notes[:300]}")
    return out


def analyze_evidence(
    db: Session,
    ev: Evidence,
    inc: Incident,
    task: VisionTask,
    user_id: str,
    analyzer: VisionAnalyzer | None = None,
) -> VisionAnalysis:
    if inc.status.value == "CLOSED":
        raise Conflict("Closed incidents cannot be analyzed", "INVALID_STATE")
    if ev.content_type not in IMAGE_TYPES:
        raise AppError("Vision analysis needs a JPEG or PNG image", "UNSUPPORTED_FILE")
    path = evidence_store.path_for(ev.storage_key)
    if not path.exists():
        raise NotFound("Evidence file missing from storage")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != ev.sha256:
        audit.record(
            db,
            organization_id=inc.organization_id,
            actor_id=user_id,
            actor_type="SYSTEM",
            action="evidence.integrity_failed",
            entity_type="evidence",
            entity_id=ev.id,
            details={"incident_id": inc.id, "recorded_sha256": ev.sha256},
        )
        db.commit()
        raise Conflict("Stored evidence does not match its recorded SHA-256", "EVIDENCE_INTEGRITY")

    image = prepare_image(content, ev.content_type)
    analyzer = analyzer or get_analyzer()
    classes = classes_for(task)
    thresholds = resolve_thresholds(db, inc, [c.label for c in classes])
    analysis = VisionAnalysis(
        organization_id=inc.organization_id,
        project_id=inc.project_id,
        incident_id=inc.id,
        evidence_id=ev.id,
        evidence_sha256=ev.sha256,
        task=task,
        analyzer=analyzer.name,
        model=analyzer.model,
        model_version=analyzer.model_version,
        taxonomy_version=TAXONOMY_VERSION,
        status="COMPLETED",
        preprocessing=image.preprocessing,
        image_quality=image.quality,
        thresholds=thresholds,
        requested_by=user_id,
    )
    started = time.perf_counter()
    output: AnalyzerOutput | None = None
    try:
        output = analyzer.analyze(image, [label_spec(c) for c in classes])
    except Exception as exc:  # a failed analysis is a visible state, never "nothing found"
        analysis.status = "FAILED"
        analysis.error = f"{type(exc).__name__}: analyzer failed; no observations were recorded"[:300]
    analysis.duration_ms = round((time.perf_counter() - started) * 1000)
    db.add(analysis)
    db.flush()

    discarded = boxes_dropped = 0
    observations: list[VisionObservation] = []
    for det in output.detections if output else []:
        cls = BY_LABEL.get(det.label)
        if cls is None or cls.task != task:
            discarded += 1
            continue
        box = _clean_box(det.box)
        if det.box and box is None:
            boxes_dropped += 1
        confidence = min(max(float(det.confidence), 0.0), 1.0)
        threshold = thresholds[cls.label]["threshold"]
        observations.append(
            VisionObservation(
                analysis_id=analysis.id,
                incident_id=inc.id,
                evidence_id=ev.id,
                ordinal=len(observations),
                category=cls.category,
                label=cls.label,
                confidence=round(confidence, 4),
                threshold=threshold,
                above_threshold=confidence >= threshold,
                box=box,
                polygon=det.polygon if analyzer.supports_segments else None,
                note=det.note[:300] if det.note else None,
            )
        )
    db.add_all(observations)
    analysis.limitations = (
        _limitations(analyzer, image.quality, discarded, boxes_dropped, output.notes if output else "")
        if analysis.status == "COMPLETED"
        else ["The analyzer failed; nothing can be concluded from this image."]
    )
    db.flush()
    db.refresh(analysis)
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=user_id,
        action="vision.analyze" if analysis.status == "COMPLETED" else "vision.analyze.failed",
        entity_type="evidence",
        entity_id=ev.id,
        details={
            "incident_id": inc.id,
            "analysis_id": analysis.id,
            "evidence_sha256": ev.sha256,
            "task": task.value,
            "analyzer": analysis.analyzer,
            "model": analysis.model,
            "model_version": analysis.model_version,
            "taxonomy_version": TAXONOMY_VERSION,
            "observations": len(observations),
            "above_threshold": sum(o.above_threshold for o in observations),
        },
    )
    return analysis


def review(
    db: Session, obs: VisionObservation, inc: Incident, decision: ObservationReview, note: str, user_id: str
) -> VisionObservation:
    """A person confirms or rejects an observation. Earlier decisions stay in the audit trail."""
    before = obs.review_status.value
    obs.review_status = decision
    obs.reviewed_by = user_id
    obs.reviewed_at = utcnow()
    obs.review_note = note
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=user_id,
        action="vision.review",
        entity_type="vision_observation",
        entity_id=obs.id,
        details={
            "incident_id": inc.id,
            "label": obs.label,
            "category": obs.category,
            "before": before,
            "after": decision.value,
            "note": note,
        },
    )
    return obs


def calibrate(
    db: Session,
    *,
    organization_id: str,
    project_id: str,
    site_id: str | None,
    label: str,
    threshold: float,
    reason: str,
    user_id: str,
) -> VisionCalibration:
    row = db.scalar(
        select(VisionCalibration).where(
            VisionCalibration.project_id == project_id,
            VisionCalibration.label == label,
            VisionCalibration.site_id.is_(None) if site_id is None else VisionCalibration.site_id == site_id,
        )
    )
    before = row.threshold if row else None
    if row is None:
        row = VisionCalibration(
            organization_id=organization_id,
            project_id=project_id,
            site_id=site_id,
            label=label,
            threshold=threshold,
            reason=reason,
            updated_by=user_id,
        )
        db.add(row)
    else:
        row.threshold, row.reason, row.updated_by = threshold, reason, user_id
    db.flush()
    audit.record(
        db,
        organization_id=organization_id,
        actor_id=user_id,
        action="vision.calibrate",
        entity_type="project",
        entity_id=project_id,
        details={"site_id": site_id, "label": label, "before": before, "after": threshold, "reason": reason},
    )
    return row


def for_agents(db: Session, incident_id: str) -> list[dict]:
    """Above-threshold observations that nobody rejected, from completed analyses, for the agents' evidence pack."""
    rows = db.execute(
        select(VisionObservation, VisionAnalysis)
        .join(VisionAnalysis, VisionAnalysis.id == VisionObservation.analysis_id)
        .where(
            VisionObservation.incident_id == incident_id,
            VisionObservation.above_threshold,
            VisionObservation.review_status != ObservationReview.REJECTED,
            VisionAnalysis.status == "COMPLETED",
        )
        .order_by(VisionAnalysis.created_at, VisionObservation.ordinal)
    ).all()
    out = []
    for obs, analysis in rows:
        cls = BY_LABEL.get(obs.label)
        out.append(
            {
                "ref": f"vision:{obs.id}",
                "evidence_id": obs.evidence_id,
                "category": obs.category,
                "label": obs.label,
                "name": cls.name if cls else obs.label,
                "maps_to": cls.maps_to if cls else None,
                "confidence": obs.confidence,
                "review_status": obs.review_status.value,
                "analyzer": analysis.analyzer,
                "model_version": analysis.model_version,
            }
        )
    return out
