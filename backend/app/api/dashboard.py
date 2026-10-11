from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import ok
from app.core.db import get_db
from app.core.errors import NotFound
from app.core.security import Permission, Principal, current_principal
from app.models import AuditEvent
from app.services import analytics

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(
    project_id: str | None = Query(default=None, description="One readable project; default: every readable project"),
    date_from: date | None = Query(default=None, description="First day (UTC) the incidents occurred, inclusive"),
    date_to: date | None = Query(default=None, description="Last day (UTC) the incidents occurred, inclusive"),
    interval: Literal["month", "week"] = Query(default="month", description="Trend bucket size"),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Safety and quality metrics for the incidents that occurred in the range (docs/API.md "Dashboard metrics")."""
    visible = p.visible_project_filter(db)
    if project_id:
        if project_id not in visible:
            raise NotFound("Project not found")
        visible = [project_id]
    filters = analytics.Filters(project_ids=visible, date_from=date_from, date_to=date_to, interval=interval)
    data = analytics.dashboard(db, filters, project_id=project_id)
    data["overdue_actions"] = [ser.capa(a) for a in data["overdue_actions"]]
    data["recent"] = [ser.incident(i) for i in data["recent"]]
    return ok(data)


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
