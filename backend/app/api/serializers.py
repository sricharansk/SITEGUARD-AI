from app.models import (
    AgentRun,
    ApprovalEvent,
    AuditEvent,
    CapaAction,
    Evidence,
    Incident,
    IncidentEvent,
    Project,
    RiskAssessment,
    VerificationRecord,
    VisionAnalysis,
    VisionCalibration,
    VisionObservation,
)
from app.services.vision import BY_LABEL, DISCLAIMER


def project(p: Project) -> dict:
    return {
        "id": p.id,
        "organization_id": p.organization_id,
        "code": p.code,
        "name": p.name,
        "client": p.client,
        "location": p.location,
        "sites": [{"id": s.id, "name": s.name} for s in p.sites],
    }


def incident(i: Incident) -> dict:
    return {
        "id": i.id,
        "reference": i.reference,
        "organization_id": i.organization_id,
        "project_id": i.project_id,
        "site_id": i.site_id,
        "title": i.title,
        "description": i.description,
        "category": i.category,
        "domain": i.domain,
        "severity": i.severity,
        "status": i.status,
        "occurred_at": i.occurred_at,
        "reported_at": i.reported_at,
        "location": i.location,
        "activity": i.activity,
        "people_involved": i.people_involved,
        "immediate_actions": i.immediate_actions,
        "reporter_id": i.reporter_id,
        "closed_at": i.closed_at,
        "is_synthetic": i.is_synthetic,
        "updated_at": i.updated_at,
    }


def event(e: IncidentEvent) -> dict:
    return {
        "id": e.id,
        "from_status": e.from_status,
        "to_status": e.to_status,
        "actor_id": e.actor_id,
        "note": e.note,
        "created_at": e.created_at,
    }


def evidence(e: Evidence) -> dict:
    return {
        "id": e.id,
        "filename": e.filename,
        "content_type": e.content_type,
        "size_bytes": e.size_bytes,
        "sha256": e.sha256,
        "description": e.description,
        "uploaded_by": e.uploaded_by,
        "created_at": e.created_at,
    }


def run(r: AgentRun) -> dict:
    return {
        "id": r.id,
        "workflow_id": r.workflow_id,
        "agent": r.agent,
        "provider": r.provider,
        "status": r.status,
        "output": r.output,
        "trace": r.trace,
        "error": r.error,
        "needs_human_review": r.needs_human_review,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
    }


def risk(r: RiskAssessment | None) -> dict | None:
    if r is None:
        return None
    return {
        "id": r.id,
        "matrix_version": r.matrix_version,
        "likelihood": r.likelihood,
        "consequence": r.consequence,
        "score": r.score,
        "band": r.band,
        "rationale": r.rationale,
        "inputs_source": r.inputs_source,
        "assessed_by": r.assessed_by,
        "created_at": r.created_at,
    }


def capa(a: CapaAction) -> dict:
    return {
        "id": a.id,
        "incident_id": a.incident_id,
        "action_type": a.action_type,
        "title": a.title,
        "description": a.description,
        "owner_role": a.owner_role,
        "assignee_id": a.assignee_id,
        "due_date": a.due_date,
        "verification_criteria": a.verification_criteria,
        "critical": a.critical,
        "approval_status": a.approval_status,
        "work_status": a.work_status,
        "ai_generated": a.ai_generated,
        "original_ai_output": a.original_ai_output,
        "source_run_id": a.source_run_id,
        "evidence_refs": a.evidence_refs,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def approval(e: ApprovalEvent) -> dict:
    return {
        "id": e.id,
        "capa_id": e.capa_id,
        "reviewer_id": e.reviewer_id,
        "decision": e.decision,
        "reason": e.reason,
        "before": e.before,
        "after": e.after,
        "created_at": e.created_at,
    }


def verification(v: VerificationRecord) -> dict:
    return {
        "id": v.id,
        "capa_id": v.capa_id,
        "verifier_id": v.verifier_id,
        "effective": v.effective,
        "notes": v.notes,
        "evidence_id": v.evidence_id,
        "created_at": v.created_at,
    }


def audit_event(a: AuditEvent) -> dict:
    return {
        "id": a.id,
        "actor_id": a.actor_id,
        "actor_type": a.actor_type,
        "action": a.action,
        "entity_type": a.entity_type,
        "entity_id": a.entity_id,
        "details": a.details,
        "correlation_id": a.correlation_id,
        "created_at": a.created_at,
    }


def vision_observation(o: VisionObservation) -> dict:
    cls = BY_LABEL.get(o.label)
    return {
        "id": o.id,
        "ref": f"vision:{o.id}",
        "kind": "OBSERVATION",
        "analysis_id": o.analysis_id,
        "evidence_id": o.evidence_id,
        "category": o.category,
        "label": o.label,
        "name": cls.name if cls else o.label,
        "maps_to": cls.maps_to if cls else None,
        "confidence": o.confidence,
        "threshold": o.threshold,
        "above_threshold": o.above_threshold,
        "box": o.box,
        "polygon": o.polygon,
        "note": o.note,
        "review_status": o.review_status,
        "reviewed_by": o.reviewed_by,
        "reviewed_at": o.reviewed_at,
        "review_note": o.review_note,
    }


def vision_analysis(a: VisionAnalysis) -> dict:
    return {
        "id": a.id,
        "incident_id": a.incident_id,
        "evidence_id": a.evidence_id,
        "evidence_sha256": a.evidence_sha256,
        "task": a.task,
        "analyzer": a.analyzer,
        "model": a.model,
        "model_version": a.model_version,
        "taxonomy_version": a.taxonomy_version,
        "status": a.status,
        "error": a.error,
        "preprocessing": a.preprocessing,
        "image_quality": a.image_quality,
        "thresholds": a.thresholds,
        "limitations": a.limitations,
        "duration_ms": a.duration_ms,
        "requested_by": a.requested_by,
        "created_at": a.created_at,
        "disclaimer": DISCLAIMER,
        "observations": [vision_observation(o) for o in a.observations],
    }


def calibration(c: VisionCalibration) -> dict:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "site_id": c.site_id,
        "label": c.label,
        "threshold": c.threshold,
        "reason": c.reason,
        "updated_by": c.updated_by,
        "updated_at": c.updated_at,
    }
