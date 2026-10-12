from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import orchestrator
from app.agents.registry import AGENTS
from app.api import serializers as ser
from app.api.deps import load_incident, ok
from app.core.db import get_db
from app.core.security import Permission, Principal, current_principal
from app.models import AgentRun

router = APIRouter(tags=["agents"])


@router.get("/agents")
def list_agents():
    return ok(
        [
            {
                "name": s.name,
                "description": s.description,
                "tools": sorted(s.tools),
                "max_tool_calls": s.max_tool_calls,
                "output_schema": s.output_model.model_json_schema(),
            }
            for s in AGENTS.values()
        ]
    )


@router.post("/incidents/{incident_id}/triage")
def triage(incident_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    inc = load_incident(db, p, incident_id, Permission.RUN_AGENTS)
    run = orchestrator.run_triage(db, inc, p.id)
    db.commit()
    return ok(ser.run(run))


@router.post("/incidents/{incident_id}/investigate")
def investigate(
    incident_id: str,
    pause_after: list[str] = Query(default=[], max_length=8),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Run the full bounded workflow, checkpointed after every stage. Ends with proposed actions in PENDING_REVIEW
    for a human, or earlier when `pause_after` names a stage to stop at for human review."""
    inc = load_incident(db, p, incident_id, Permission.RUN_AGENTS)
    result = orchestrator.run_investigation(db, inc, p.id, pause_after=pause_after, checkpoint=db.commit)
    db.commit()
    db.refresh(inc)
    return ok(investigation_payload(inc, result))


def investigation_payload(inc, result: dict) -> dict:
    return {
        "workflow_id": result["workflow_id"],
        "workflow": ser.workflow(result["workflow"]),
        "incident_status": inc.status,
        "runs": [ser.run(r) for r in result["runs"]],
        "risk": ser.risk(result["risk"]),
        "proposed_actions": [ser.capa(a) for a in result["capa"]],
        "conflicts": [ser.conflict(c) for c in result["conflicts"]],
        "flags": result["flags"],
    }


@router.get("/incidents/{incident_id}/agent-runs")
def agent_runs(incident_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    inc = load_incident(db, p, incident_id)
    rows = db.scalars(select(AgentRun).where(AgentRun.incident_id == inc.id).order_by(AgentRun.started_at))
    return ok([ser.run(r) for r in rows])
