from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import load_capa, load_incident, ok
from app.api.schemas import ApproveIn, CapaIn, ProgressIn, ReviewIn, VerifyIn
from app.core.db import get_db
from app.core.errors import AppError, Conflict
from app.core.security import Permission, Principal, current_principal
from app.models import ApprovalStatus, CapaAction, Evidence, IncidentStatus
from app.services import audit, capa, lifecycle

router = APIRouter(tags=["capa"])


@router.post("/incidents/{incident_id}/capa", status_code=201)
def propose(incident_id: str, body: CapaIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """A human-authored action. It still goes through review like AI proposals do."""
    inc = load_incident(db, p, incident_id, Permission.PROPOSE_CAPA)
    if inc.status == IncidentStatus.CLOSED:
        raise Conflict("Incident is closed", "INVALID_STATE")
    action = CapaAction(
        incident_id=inc.id,
        approval_status=ApprovalStatus.PENDING_REVIEW,
        ai_generated=False,
        **body.model_dump(),
    )
    db.add(action)
    db.flush()
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=p.id,
        action="capa.propose",
        entity_type="capa",
        entity_id=action.id,
        details={"incident_id": inc.id, "title": action.title},
    )
    if inc.status == IncidentStatus.PENDING_VERIFICATION:
        lifecycle.transition(db, inc, IncidentStatus.ACTION_IN_PROGRESS, actor_id=p.id, note="New action proposed")
    db.commit()
    return ok(ser.capa(action))


@router.post("/capa/{capa_id}/review")
def review(capa_id: str, body: ReviewIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    action, inc = load_capa(db, p, capa_id)
    capa.review(db, p, inc, action, body.decision, body.reason, body.changes)
    db.commit()
    return ok({"action": ser.capa(action), "incident_status": inc.status})


@router.post("/capa/{capa_id}/approve")
def approve(capa_id: str, body: ApproveIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Shortcut for review with decision APPROVE (docs/API.md)."""
    action, inc = load_capa(db, p, capa_id)
    capa.review(db, p, inc, action, "APPROVE", body.reason, None)
    db.commit()
    return ok({"action": ser.capa(action), "incident_status": inc.status})


@router.patch("/capa/{capa_id}/progress")
def progress(capa_id: str, body: ProgressIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    action, inc = load_capa(db, p, capa_id)
    capa.update_progress(db, p, inc, action, body.status(), body.assignee_id, body.note)
    db.commit()
    return ok({"action": ser.capa(action), "incident_status": inc.status})


@router.post("/capa/{capa_id}/verify")
def verify(capa_id: str, body: VerifyIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    action, inc = load_capa(db, p, capa_id)
    if body.evidence_id:
        ev = db.get(Evidence, body.evidence_id)
        if ev is None or ev.incident_id != inc.id:
            raise AppError("evidence_id does not belong to this incident")
    rec = capa.verify(db, p, inc, action, body.effective, body.notes, body.evidence_id)
    db.commit()
    return ok({"verification": ser.verification(rec), "action": ser.capa(action), "incident_status": inc.status})
