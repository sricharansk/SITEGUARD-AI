"""Investigation workflows and the conflicts they record (docs/API.md#workflows)."""

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.agents import orchestrator
from app.api import serializers as ser
from app.api.agents import investigation_payload
from app.api.deps import load_incident, ok
from app.api.schemas import CancelIn, ResolveConflictIn, ResumeIn
from app.core.db import get_db
from app.core.errors import NotFound
from app.core.security import Permission, Principal, current_principal
from app.models import AgentConflict, Incident, WorkflowRun
from app.services import conflicts

router = APIRouter(tags=["workflows"])


def _load(db: Session, p: Principal, workflow_id: str, perm: Permission) -> tuple[WorkflowRun, Incident]:
    wf = db.get(WorkflowRun, workflow_id)
    if wf is None:
        raise NotFound("Workflow not found")
    return wf, load_incident(db, p, wf.incident_id, perm)


@router.get("/incidents/{incident_id}/workflows")
def list_workflows(incident_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    inc = load_incident(db, p, incident_id)
    rows = db.scalars(
        select(WorkflowRun).where(WorkflowRun.incident_id == inc.id).order_by(desc(WorkflowRun.created_at))
    )
    return ok([ser.workflow(w) for w in rows])


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    wf, inc = _load(db, p, workflow_id, Permission.READ)
    return ok(investigation_payload(inc, orchestrator.investigation_result(db, wf)))


@router.post("/workflows/{workflow_id}/pause")
def pause(workflow_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Ask a RUNNING workflow to stop before its next stage."""
    wf, inc = _load(db, p, workflow_id, Permission.RUN_AGENTS)
    orchestrator.request_pause(db, wf, inc, p.id)
    db.commit()
    return ok(ser.workflow(wf))


@router.post("/workflows/{workflow_id}/resume")
def resume(
    workflow_id: str,
    body: ResumeIn | None = None,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Continue a PAUSED or FAILED workflow (or a RUNNING one whose process stopped) from its next stage."""
    wf, inc = _load(db, p, workflow_id, Permission.RUN_AGENTS)
    wf = orchestrator.resume(db, wf, inc, p.id, pause_after=body.pause_after if body else None, checkpoint=db.commit)
    db.commit()
    db.refresh(inc)
    return ok(investigation_payload(inc, orchestrator.investigation_result(db, wf)))


@router.post("/workflows/{workflow_id}/cancel")
def cancel(workflow_id: str, body: CancelIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    wf, inc = _load(db, p, workflow_id, Permission.RUN_AGENTS)
    orchestrator.cancel(db, wf, inc, p.id, body.reason)
    db.commit()
    return ok(ser.workflow(wf))


@router.get("/incidents/{incident_id}/conflicts")
def list_conflicts(incident_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    inc = load_incident(db, p, incident_id)
    rows = db.scalars(
        select(AgentConflict).where(AgentConflict.incident_id == inc.id).order_by(desc(AgentConflict.created_at))
    )
    return ok([ser.conflict(c) for c in rows])


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: str,
    body: ResolveConflictIn,
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """A reviewer records the decision on a disagreement. Both sides stay on record."""
    row = db.get(AgentConflict, conflict_id)
    if row is None:
        raise NotFound("Conflict not found")
    inc = load_incident(db, p, row.incident_id, Permission.APPROVE_CAPA)
    conflicts.resolve(db, row, inc, body.resolution, p.id)
    db.commit()
    return ok(ser.conflict(row))
