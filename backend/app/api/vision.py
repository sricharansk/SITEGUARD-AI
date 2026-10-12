"""Vision analysis of image evidence: run, list, review observations, calibrate thresholds (docs/API.md#vision)."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import load_incident, load_project, ok
from app.api.schemas import CalibrationIn, ObservationReviewIn, VisionRunIn
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError, NotFound
from app.core.ratelimit import RateLimiter
from app.core.security import Permission, Principal, current_principal
from app.models import Evidence, ObservationReview, Site, VisionAnalysis, VisionCalibration, VisionObservation
from app.services import vision

router = APIRouter(tags=["vision"])
# Each analysis starts an image decoder process and may call a paid model, so it is limited per user.
analysis_limiter = RateLimiter(get_settings().vision_rate_limit_per_minute)


@router.get("/vision/taxonomy")
def taxonomy(_: Principal = Depends(current_principal)):
    """Labels each task looks for, their default threshold and the agent taxonomy label they map to."""
    return ok(
        {
            "version": vision.TAXONOMY_VERSION,
            "default_threshold": vision.DEFAULT_THRESHOLD,
            "disclaimer": vision.DISCLAIMER,
            "quality_limits": vision.QUALITY_LIMITS,
            "classes": [
                {
                    "label": c.label,
                    "name": c.name,
                    "category": c.category,
                    "task": c.task,
                    "description": c.description,
                    "maps_to": c.maps_to,
                }
                for c in vision.CLASSES
            ],
        }
    )


@router.post("/evidence/{evidence_id}/vision", status_code=201)
def analyze(
    evidence_id: str,
    body: VisionRunIn,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Run the configured analyzer on one image. A failed analysis is stored and returned with status FAILED."""
    ev = db.get(Evidence, evidence_id)
    if ev is None:
        raise NotFound("Evidence not found")
    inc = load_incident(db, p, ev.incident_id, Permission.RUN_AGENTS)
    analysis_limiter.check(p.id)
    analysis = vision.analyze_evidence(db, ev, inc, body.task, p.id)
    db.commit()
    return ok(ser.vision_analysis(analysis))


@router.get("/incidents/{incident_id}/vision")
def list_analyses(incident_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    inc = load_incident(db, p, incident_id)
    rows = db.scalars(
        select(VisionAnalysis).where(VisionAnalysis.incident_id == inc.id).order_by(VisionAnalysis.created_at)
    )
    return ok({"disclaimer": vision.DISCLAIMER, "analyses": [ser.vision_analysis(a) for a in rows]})


@router.post("/vision/observations/{observation_id}/review")
def review(
    observation_id: str,
    body: ObservationReviewIn,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """An engineer confirms or rejects an observation. Only confirmed observations count as validated facts."""
    obs = db.get(VisionObservation, observation_id)
    if obs is None:
        raise NotFound("Observation not found")
    inc = load_incident(db, p, obs.incident_id, Permission.RUN_AGENTS)
    vision.review(db, obs, inc, ObservationReview(body.decision), body.note, p.id)
    db.commit()
    return ok(ser.vision_observation(obs))


@router.get("/projects/{project_id}/vision/calibration")
def list_calibration(project_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project = load_project(db, p, project_id)
    rows = db.scalars(
        select(VisionCalibration)
        .where(VisionCalibration.project_id == project.id)
        .order_by(VisionCalibration.label, VisionCalibration.site_id)
    )
    return ok([ser.calibration(c) for c in rows])


@router.put("/projects/{project_id}/vision/calibration")
def set_calibration(
    project_id: str,
    body: CalibrationIn,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Set the detection threshold for one label on the project, or on one of its sites. Audited with a reason."""
    project = load_project(db, p, project_id, Permission.MANAGE_PROJECTS)
    if body.label not in vision.BY_LABEL:
        raise AppError(f"Unknown vision label '{body.label}'")
    if body.site_id is not None:
        site = db.get(Site, body.site_id)
        if site is None or site.project_id != project.id:
            raise AppError("Site does not belong to this project")
    row = vision.calibrate(
        db,
        organization_id=project.organization_id,
        project_id=project.id,
        site_id=body.site_id,
        label=body.label,
        threshold=body.threshold,
        reason=body.reason,
        user_id=p.id,
    )
    db.commit()
    return ok(ser.calibration(row))
