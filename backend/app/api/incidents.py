from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import load_incident, load_project, ok
from app.api.schemas import CloseIn, IncidentIn, IncidentPatch, RiskIn, TransitionIn
from app.core.db import get_db
from app.core.errors import AppError, Conflict, NotFound
from app.core.security import Permission, Principal, current_principal
from app.models import (
    AgentRun,
    ApprovalEvent,
    CapaAction,
    Domain,
    Evidence,
    Incident,
    IncidentEvent,
    IncidentStatus,
    RiskAssessment,
    Severity,
    Site,
    VerificationRecord,
)
from app.services import audit, capa, evidence, incidents, lifecycle, risk

router = APIRouter(tags=["incidents"])


@router.get("/projects/{project_id}/incidents")
def list_incidents(
    project_id: str,
    status: IncidentStatus | None = None,
    severity: Severity | None = None,
    domain: Domain | None = None,
    q: str | None = Query(default=None, max_length=200),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    load_project(db, p, project_id)
    stmt = select(Incident).where(Incident.project_id == project_id)
    if status:
        stmt = stmt.where(Incident.status == status)
    if severity:
        stmt = stmt.where(Incident.severity == severity)
    if domain:
        stmt = stmt.where(Incident.domain == domain)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Incident.title.ilike(like), Incident.description.ilike(like), Incident.reference.ilike(like))
        )
    rows = db.scalars(stmt.order_by(desc(Incident.reported_at)))
    return ok([ser.incident(i) for i in rows])


@router.post("/projects/{project_id}/incidents", status_code=201)
def create_incident(
    project_id: str,
    body: IncidentIn,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    project = load_project(db, p, project_id, Permission.CREATE_INCIDENT)
    if body.site_id:
        site = db.get(Site, body.site_id)
        if site is None or site.project_id != project.id:
            raise AppError("site_id does not belong to this project")
    inc = incidents.create(
        db,
        organization_id=project.organization_id,
        project_id=project.id,
        reporter_id=p.id,
        data=body.model_dump(),
    )
    db.commit()
    return ok(ser.incident(inc))


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """The incident workspace: incident, history, evidence, agent runs, risk, actions, approvals, verifications."""
    inc = load_incident(db, p, incident_id)
    events = db.scalars(
        select(IncidentEvent).where(IncidentEvent.incident_id == inc.id).order_by(IncidentEvent.created_at)
    )
    ev = db.scalars(select(Evidence).where(Evidence.incident_id == inc.id).order_by(Evidence.created_at))
    runs = list(db.scalars(select(AgentRun).where(AgentRun.incident_id == inc.id).order_by(AgentRun.started_at)))
    latest_wf = runs[-1].workflow_id if runs else None
    risk_row = db.scalar(
        select(RiskAssessment)
        .where(RiskAssessment.incident_id == inc.id)
        .order_by(desc(RiskAssessment.created_at))
        .limit(1)
    )
    actions = list(
        db.scalars(select(CapaAction).where(CapaAction.incident_id == inc.id).order_by(CapaAction.created_at))
    )
    ids = [a.id for a in actions]
    approvals: list[ApprovalEvent] = (
        list(db.scalars(select(ApprovalEvent).where(ApprovalEvent.capa_id.in_(ids)))) if ids else []
    )
    verifs: list[VerificationRecord] = (
        list(db.scalars(select(VerificationRecord).where(VerificationRecord.capa_id.in_(ids)))) if ids else []
    )
    return ok(
        {
            "incident": ser.incident(inc),
            "history": [ser.event(e) for e in events],
            "evidence": [ser.evidence(e) for e in ev],
            "agent_runs": [ser.run(r) for r in runs if r.workflow_id == latest_wf],
            "risk": ser.risk(risk_row),
            "capa": [ser.capa(a) for a in actions],
            "approvals": [ser.approval(a) for a in approvals],
            "verifications": [ser.verification(v) for v in verifs],
            "close_blockers": capa.close_blockers(db, inc),
            "permissions": sorted(p.permissions(inc.organization_id, inc.project_id)),
        }
    )


@router.patch("/incidents/{incident_id}")
def update_incident(
    incident_id: str,
    body: IncidentPatch,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    inc = load_incident(db, p, incident_id, Permission.EDIT_INCIDENT)
    if inc.status == IncidentStatus.CLOSED:
        raise Conflict("Closed incidents cannot be edited; reopen first", "INVALID_STATE")
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(inc, k) for k in changes}
    for k, v in changes.items():
        setattr(inc, k, v)
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=p.id,
        action="incident.update",
        entity_type="incident",
        entity_id=inc.id,
        details={
            "before": {k: str(v) for k, v in before.items()},
            "after": {k: str(v) for k, v in changes.items()},
        },
    )
    db.commit()
    return ok(ser.incident(inc))


@router.post("/incidents/{incident_id}/transition")
def transition_incident(
    incident_id: str,
    body: TransitionIn,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Manual workflow (works when AI is unavailable). Closing uses /close, which checks verification."""
    inc = load_incident(db, p, incident_id, Permission.EDIT_INCIDENT)
    if body.to_status == IncidentStatus.CLOSED:
        raise AppError("Use POST /incidents/{id}/close to close an incident")
    if inc.status == IncidentStatus.CLOSED:
        p.require(Permission.CLOSE_INCIDENT, inc.organization_id, inc.project_id)  # reopening
    lifecycle.transition(db, inc, body.to_status, actor_id=p.id, note=body.note)
    db.commit()
    return ok(ser.incident(inc))


@router.post("/incidents/{incident_id}/close")
def close(incident_id: str, body: CloseIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    inc = load_incident(db, p, incident_id)
    capa.close_incident(db, p, inc, body.note)
    db.commit()
    return ok(ser.incident(inc))


@router.post("/incidents/{incident_id}/evidence", status_code=201)
async def upload_evidence(
    incident_id: str,
    file: UploadFile = File(...),
    description: str | None = Form(default=None, max_length=2000),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    inc = load_incident(db, p, incident_id, Permission.EDIT_INCIDENT)
    content = await file.read()
    name, content_type = evidence.validate(file.filename or "", file.content_type, content)
    key, digest = evidence.store(inc.organization_id, inc.id, content)
    row = Evidence(
        incident_id=inc.id,
        filename=name,
        content_type=content_type,
        size_bytes=len(content),
        sha256=digest,
        storage_key=key,
        description=description,
        uploaded_by=p.id,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=p.id,
        action="evidence.upload",
        entity_type="evidence",
        entity_id=row.id,
        details={"incident_id": inc.id, "sha256": digest, "size": len(content), "filename": name},
    )
    db.commit()
    return ok(ser.evidence(row))


@router.get("/evidence/{evidence_id}/download")
def download_evidence(evidence_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    row = db.get(Evidence, evidence_id)
    if row is None:
        raise NotFound("Evidence not found")
    load_incident(db, p, row.incident_id)
    path = evidence.path_for(row.storage_key)
    if not path.exists():
        raise NotFound("Evidence file missing from storage")
    return FileResponse(path, media_type=row.content_type, filename=row.filename)


@router.get("/risk/matrix")
def risk_matrix():
    return ok(
        {
            "version": risk.MATRIX_VERSION,
            "likelihood": risk.LIKELIHOOD,
            "consequence": risk.CONSEQUENCE,
            "bands": risk.matrix(),
        }
    )


@router.post("/incidents/{incident_id}/risk", status_code=201)
def assess_risk(
    incident_id: str, body: RiskIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)
):
    """Human risk assessment. Supersedes the AI-suggested inputs; the score still comes from the matrix."""
    inc = load_incident(db, p, incident_id, Permission.RUN_AGENTS)
    r = risk.assess(body.likelihood, body.consequence)
    row = RiskAssessment(
        incident_id=inc.id,
        matrix_version=r.matrix_version,
        likelihood=r.likelihood,
        consequence=r.consequence,
        score=r.score,
        band=r.band,
        rationale=f"{r.rationale} Assessor note: {body.rationale}",
        inputs_source="HUMAN",
        assessed_by=p.id,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=p.id,
        action="risk.assess",
        entity_type="incident",
        entity_id=inc.id,
        details={"score": r.score, "band": r.band},
    )
    db.commit()
    return ok(ser.risk(row))
