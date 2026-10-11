"""Conflict and uncertainty handling for investigations (Playbook Prompt 30; docs/AGENTS.md#conflicts-and-uncertainty).

The workflow never picks a winner silently. When agents disagree with each other or with the report, when cited
documents give different values for the same requirement, or when vision analyses of the same photo disagree, both
sides are stored as an OPEN conflict, people are notified, and the incident cannot close until a person records a
decision. A later investigation marks still-open conflicts SUPERSEDED (kept, never deleted) and records its own.
"""

import itertools
import json
import re
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.models import (
    AgentConflict,
    Document,
    DocumentChunk,
    Incident,
    ObservationReview,
    VisionAnalysis,
    VisionObservation,
    utcnow,
)
from app.services import audit
from app.services.answer import _MEASURE, _SENTENCE, _UNIT, _terms

SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
AGENT_NAMES = ("triage", "safety", "quality", "rca", "compliance", "capa")
_CHUNK_REF = re.compile(r"\bchunk:([0-9a-f-]{36})\b")


@dataclass
class Finding:
    kind: str
    summary: str
    details: dict = field(default_factory=dict)
    refs: list[str] = field(default_factory=list)


def _gap(a: str, b: str) -> int:
    return SEVERITY_ORDER.index(a) - SEVERITY_ORDER.index(b)


def agent_findings(inc: Incident, state: dict) -> list[Finding]:
    """Disagreements between agents, and between AI output and what was reported."""
    out: list[Finding] = []
    reported = inc.severity.value
    tri = state.get("triage")
    if tri:
        proposed = tri["severity_candidate"]
        if abs(_gap(proposed, reported)) >= 2:
            out.append(
                Finding(
                    "SEVERITY_DISAGREEMENT",
                    f"Reported severity {reported} differs from AI triage {proposed}; human review needed.",
                    {"reported": reported, "triage": proposed},
                    [f"incident:{inc.id}"],
                )
            )
        domains = {tri["domain"], inc.domain.value}
        if len(domains) == 2 and "BOTH" not in domains:
            out.append(
                Finding(
                    "DOMAIN_DISAGREEMENT",
                    f"The incident was reported as {inc.domain.value} but AI triage classed it as {tri['domain']}.",
                    {"reported": inc.domain.value, "triage": tri["domain"]},
                    [f"incident:{inc.id}"],
                )
            )
    risk = state.get("risk")
    if risk and ((risk["band"] == "CRITICAL" and reported != "CRITICAL") or _gap(risk["band"], reported) >= 2):
        out.append(
            Finding(
                "RISK_ABOVE_REPORTED",
                f"Risk matrix rates this {risk['band']} but the incident is marked {reported}.",
                {"reported": reported, "risk_band": risk["band"], "risk_score": risk["score"]},
                [f"incident:{inc.id}"],
            )
        )
    safety, quality = state.get("safety"), state.get("quality")
    if safety and quality:
        diffs = {k: (safety[k], quality[k]) for k in ("likelihood", "consequence") if abs(safety[k] - quality[k]) >= 2}
        if diffs:
            parts = ", ".join(f"{k} {a} (safety) vs {b} (quality)" for k, (a, b) in diffs.items())
            out.append(
                Finding(
                    "AGENT_DISAGREEMENT",
                    f"Safety and quality investigations disagree on {parts}; the risk matrix used the higher values.",
                    {
                        "safety": {k: safety[k] for k in ("likelihood", "consequence")},
                        "quality": {k: quality[k] for k in ("likelihood", "consequence")},
                    },
                    [],
                )
            )
    return out


def source_findings(db: Session, inc: Incident, state: dict) -> list[Finding]:
    """Cited documents that give different values for the same requirement (same unit, overlapping wording)."""
    cited = sorted(set(_CHUNK_REF.findall(json.dumps(state, default=str))))
    if len(cited) < 2:
        return []
    rows = db.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.id.in_(cited),
            Document.organization_id == inc.organization_id,
            or_(Document.project_id.is_(None), Document.project_id == inc.project_id),
        )
    ).all()
    measured = []
    for chunk, doc in rows:
        for m in _SENTENCE.finditer(" ".join(chunk.text.split())):
            sentence = m.group(0)
            for value, unit in _MEASURE.findall(sentence):
                norm = _UNIT.get(unit.lower(), unit.lower())
                measured.append((float(value), norm, _terms(sentence), chunk, doc))
    out: list[Finding] = []
    seen: set[tuple] = set()
    for (v1, u1, t1, c1, d1), (v2, u2, t2, c2, d2) in itertools.combinations(measured, 2):
        if u1 != u2 or v1 == v2 or d1.id == d2.id or len(t1 & t2) < 3:
            continue
        key = tuple(sorted([(c1.id, v1), (c2.id, v2)]))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Finding(
                "SOURCE_CONFLICT",
                f"'{d1.title}' (version {d1.version}) gives {v1:g} {u1} but '{d2.title}' (version {d2.version}) "
                f"gives {v2:g} {u2} for the same requirement.",
                {
                    "a": {"document": d1.title, "version": d1.version, "value": v1, "unit": u1},
                    "b": {"document": d2.title, "version": d2.version, "value": v2, "unit": u2},
                },
                [f"chunk:{c1.id}", f"chunk:{c2.id}"],
            )
        )
    return out


def vision_findings(db: Session, inc: Incident) -> list[Finding]:
    """Analyses of the same photo and task that disagree, or reviewers who disagree about the same label."""
    rows = db.execute(
        select(VisionObservation, VisionAnalysis)
        .join(VisionAnalysis, VisionAnalysis.id == VisionObservation.analysis_id)
        .where(VisionObservation.incident_id == inc.id, VisionAnalysis.status == "COMPLETED")
    ).all()
    analyses = db.scalars(
        select(VisionAnalysis).where(VisionAnalysis.incident_id == inc.id, VisionAnalysis.status == "COMPLETED")
    ).all()
    groups: dict[tuple[str, str], list[VisionAnalysis]] = {}
    for a in analyses:
        groups.setdefault((a.evidence_id, a.task.value), []).append(a)
    out: list[Finding] = []
    for (evidence_id, task), group in groups.items():
        if len(group) < 2:
            continue
        ids = {a.id for a in group}
        obs = [(o, a) for o, a in rows if a.id in ids]
        for label in sorted({o.label for o, _ in obs}):
            positive = [
                (o, a)
                for o, a in obs
                if o.label == label
                and o.review_status != ObservationReview.REJECTED
                and (o.above_threshold or o.review_status == ObservationReview.CONFIRMED)
            ]
            seen_by = {a.id for _, a in positive}
            missed_by = [a for a in group if a.id not in seen_by]
            if positive and missed_by:
                out.append(
                    Finding(
                        "VISION_DISAGREEMENT",
                        f"Vision analyses of the same photo disagree about '{label}': reported by "
                        f"{len(seen_by)} analysis(es), not by {len(missed_by)}.",
                        {
                            "evidence_id": evidence_id,
                            "task": task,
                            "label": label,
                            "reported_by": sorted(f"{a.analyzer}/{a.model_version}:{a.id}" for _, a in positive),
                            "not_reported_by": sorted(f"{a.analyzer}/{a.model_version}:{a.id}" for a in missed_by),
                        },
                        [f"evidence:{evidence_id}"],
                    )
                )
            decisions = {o.review_status for o, _ in obs if o.label == label} - {ObservationReview.UNREVIEWED}
            if decisions == {ObservationReview.CONFIRMED, ObservationReview.REJECTED}:
                out.append(
                    Finding(
                        "VISION_REVIEW_DISAGREEMENT",
                        f"Reviewers confirmed and rejected '{label}' on the same photo.",
                        {"evidence_id": evidence_id, "task": task, "label": label},
                        [f"evidence:{evidence_id}"],
                    )
                )
    return out


def record(db: Session, inc: Incident, workflow_id: str, findings: list[Finding], actor_id: str) -> list:
    """Store findings as OPEN conflicts. Still-open conflicts from earlier workflows become SUPERSEDED."""
    for old in db.scalars(
        select(AgentConflict).where(
            AgentConflict.incident_id == inc.id,
            AgentConflict.status == "OPEN",
            AgentConflict.workflow_id != workflow_id,
        )
    ):
        old.status = "SUPERSEDED"
        old.resolution = f"Superseded by investigation {workflow_id}, which re-checked this incident."
    rows = []
    for f in findings:
        row = AgentConflict(
            organization_id=inc.organization_id,
            incident_id=inc.id,
            workflow_id=workflow_id,
            kind=f.kind,
            summary=f.summary[:500],
            details=f.details,
            refs=f.refs,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    if rows:
        audit.record(
            db,
            organization_id=inc.organization_id,
            actor_id=actor_id,
            actor_type="AGENT",
            action="conflict.detected",
            entity_type="incident",
            entity_id=inc.id,
            details={"workflow_id": workflow_id, "conflicts": [{"id": r.id, "kind": r.kind} for r in rows]},
        )
    return rows


def resolve(db: Session, row: AgentConflict, inc: Incident, resolution: str, user_id: str) -> AgentConflict:
    if row.status != "OPEN":
        raise Conflict(f"Conflict is {row.status}; only OPEN conflicts can be resolved", "INVALID_STATE")
    row.status, row.resolution, row.resolved_by, row.resolved_at = "RESOLVED", resolution, user_id, utcnow()
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=user_id,
        action="conflict.resolve",
        entity_type="agent_conflict",
        entity_id=row.id,
        details={"incident_id": inc.id, "kind": row.kind, "resolution": resolution},
    )
    return row


def open_count(db: Session, incident_id: str) -> int:
    return len(
        db.scalars(
            select(AgentConflict.id).where(AgentConflict.incident_id == incident_id, AgentConflict.status == "OPEN")
        ).all()
    )


def uncertainty(state: dict, stages: dict) -> dict:
    """Confidence, review reasons and unresolved questions across the agents, in one structure."""
    agents = {name: state[name] for name in AGENT_NAMES if name in state}
    confidences = {name: out.get("confidence") for name, out in agents.items()}
    return {
        "min_confidence": min(confidences.values()) if confidences else None,
        "confidence_by_agent": confidences,
        "low_confidence_agents": sorted(n for n, c in confidences.items() if c is not None and c < 0.5),
        "agents_needing_review": [
            {"agent": name, "reasons": rec.get("review_reasons", [])}
            for name, rec in stages.items()
            if rec.get("needs_human_review")
        ],
        "failed_stages": sorted(n for n, rec in stages.items() if rec.get("status") in ("FAILED", "ERROR")),
        "unresolved_questions": [
            {"agent": name, "question": q} for name, out in agents.items() for q in out.get("open_questions", [])
        ][:50],
    }
