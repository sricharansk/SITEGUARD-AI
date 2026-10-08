from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import ok
from app.core.db import get_db
from app.core.errors import NotFound
from app.core.security import Permission, Principal, current_principal
from app.models import AgentRun, ApprovalStatus, AuditEvent, CapaAction, Incident, IncidentStatus, WorkStatus

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(project_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    visible = p.visible_project_filter(db)
    if project_id:
        if project_id not in visible:
            raise NotFound("Project not found")
        visible = [project_id]
    incidents = list(db.scalars(select(Incident).where(Incident.project_id.in_(visible)))) if visible else []
    ids = [i.id for i in incidents]
    actions = list(db.scalars(select(CapaAction).where(CapaAction.incident_id.in_(ids)))) if ids else []
    runs = list(db.scalars(select(AgentRun).where(AgentRun.incident_id.in_(ids)))) if ids else []
    today = date.today()
    active_actions = [a for a in actions if a.approval_status in (ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED)]
    overdue = [
        a
        for a in active_actions
        if a.due_date and a.due_date < today and a.work_status not in (WorkStatus.COMPLETED, WorkStatus.VERIFIED)
    ]
    closed = [i for i in incidents if i.status == IncidentStatus.CLOSED and i.closed_at]
    days = [(i.closed_at - i.reported_at).total_seconds() / 86400 for i in closed]

    hazards: Counter[str] = Counter()
    for r in runs:
        if r.agent == "triage" and r.output:
            hazards.update(h for h in r.output.get("hazards", []) if not h.startswith("No known"))
    by_month: Counter[str] = Counter(i.occurred_at.strftime("%Y-%m") for i in incidents)
    open_critical = [i for i in incidents if i.severity.value == "CRITICAL" and i.status != IncidentStatus.CLOSED]

    return ok(
        {
            "totals": {
                "incidents": len(incidents),
                "open": sum(1 for i in incidents if i.status != IncidentStatus.CLOSED),
                "open_critical": len(open_critical),
                "awaiting_review": sum(1 for a in actions if a.approval_status == ApprovalStatus.PENDING_REVIEW),
                "actions_open": sum(1 for a in active_actions if a.work_status != WorkStatus.VERIFIED),
                "actions_overdue": len(overdue),
                "mean_days_to_close": round(sum(days) / len(days), 1) if days else None,
            },
            "by_status": Counter(i.status.value for i in incidents),
            "by_severity": Counter(i.severity.value for i in incidents),
            "by_domain": Counter(i.domain.value for i in incidents),
            "by_month": dict(sorted(by_month.items())),
            "top_hazards": hazards.most_common(8),
            "capa_by_status": Counter(a.approval_status.value for a in actions),
            "capa_work": Counter(a.work_status.value for a in active_actions),
            "agents": {
                "runs": len(runs),
                "succeeded": sum(1 for r in runs if r.status == "SUCCEEDED"),
                "failed": sum(1 for r in runs if r.status == "FAILED"),
                "flagged_for_review": sum(1 for r in runs if r.needs_human_review),
                "fallbacks": sum(1 for r in runs if "fallback" in r.provider),
                "providers": Counter(r.provider for r in runs),
            },
            "overdue_actions": [ser.capa(a) for a in overdue[:10]],
            "recent": [ser.incident(i) for i in sorted(incidents, key=lambda i: i.reported_at, reverse=True)[:8]],
        }
    )


@router.get("/audit")
def audit_log(
    organization_id: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    orgs = [o for o in p.org_ids() if p.can(Permission.VIEW_AUDIT, o)]
    if organization_id:
        p.require(Permission.VIEW_AUDIT, organization_id)
        orgs = [organization_id]
    if not orgs:
        p.require(Permission.VIEW_AUDIT, next(iter(p.org_ids()), ""))
    stmt = select(AuditEvent).where(AuditEvent.organization_id.in_(orgs))
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    rows = db.scalars(stmt.order_by(desc(AuditEvent.created_at)).limit(limit))
    return ok([ser.audit_event(a) for a in rows])
