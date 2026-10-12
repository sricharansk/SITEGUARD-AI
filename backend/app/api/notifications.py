from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import ok
from app.api.schemas import EscalateIn
from app.core.db import get_db
from app.core.errors import Forbidden, NotFound
from app.core.security import Permission, Principal, current_principal
from app.models import Notification, Project, utcnow
from app.services import notifications

router = APIRouter(tags=["notifications"])


def _n(n: Notification) -> dict:
    return {
        "id": n.id,
        "kind": n.kind,
        "message": n.message,
        "incident_id": n.incident_id,
        "capa_id": n.capa_id,
        "read_at": n.read_at,
        "created_at": n.created_at,
    }


@router.get("/notifications")
def my_notifications(
    unread_only: bool = False, p: Principal = Depends(current_principal), db: Session = Depends(get_db)
):
    stmt = select(Notification).where(Notification.recipient_id == p.id, Notification.organization_id.in_(p.org_ids()))
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(desc(Notification.created_at)).limit(100))
    return ok([_n(n) for n in rows])


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_id != p.id:
        raise NotFound("Notification not found")
    n.read_at = n.read_at or utcnow()
    db.commit()
    return ok(_n(n))


@router.post("/capa/escalate-overdue")
def escalate_overdue(body: EscalateIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Escalate overdue approved actions in the projects where the caller can approve actions."""
    allowed = []
    for pid in p.visible_project_filter(db):
        project = db.get(Project, pid)
        if project and p.can(Permission.APPROVE_CAPA, project.organization_id, project.id):
            allowed.append(pid)
    if body.project_id:
        if body.project_id not in p.visible_project_filter(db):
            raise NotFound("Project not found")
        if body.project_id not in allowed:
            raise Forbidden(f"Missing permission {Permission.APPROVE_CAPA.value}")
        allowed = [body.project_id]
    elif not allowed:
        raise Forbidden(f"Missing permission {Permission.APPROVE_CAPA.value}")
    sent = notifications.escalate_overdue(db, project_ids=allowed, actor_id=p.id)
    db.commit()
    return ok({"escalations": sent})
