from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import ok
from app.api.schemas import EscalateIn
from app.core.db import get_db
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.security import Permission, Principal, current_principal
from app.models import DeliveryStatus, Notification, NotificationDelivery, Project, User, utcnow
from app.services import audit, delivery, notifications

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


def _delivery(d: NotificationDelivery, n: Notification, recipient: str) -> dict:
    return {
        "id": d.id,
        "notification_id": n.id,
        "channel": d.channel,
        "status": d.status,
        "attempts": d.attempts,
        "last_error": d.last_error,
        "next_attempt_at": d.next_attempt_at,
        "sent_at": d.sent_at,
        "created_at": d.created_at,
        "kind": n.kind,
        "recipient": recipient,  # name only: the outbox view does not list email addresses
        "incident_id": n.incident_id,
    }


@router.get("/notifications/deliveries")
def list_deliveries(
    organization_id: str = Query(),
    status: DeliveryStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Email outbox for one organization, including FAILED (dead-letter) deliveries."""
    p.require_org_wide(Permission.VIEW_AUDIT, organization_id)
    stmt = (
        select(NotificationDelivery, Notification, User.full_name)
        .join(Notification, Notification.id == NotificationDelivery.notification_id)
        .join(User, User.id == Notification.recipient_id)
        .where(Notification.organization_id == organization_id)
    )
    if status:
        stmt = stmt.where(NotificationDelivery.status == status)
    rows = db.execute(stmt.order_by(desc(NotificationDelivery.created_at), NotificationDelivery.id).limit(limit))
    return ok([_delivery(d, n, name) for d, n, name in rows])


@router.post("/notifications/deliver")
def deliver(organization_id: str = Query(), p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Send due email deliveries for one organization now (normally the `deliver-notifications` job)."""
    p.require_org_wide(Permission.MANAGE_PROJECTS, organization_id)
    report = delivery.dispatch(db, organization_id=organization_id)
    audit.record(
        db,
        organization_id=organization_id,
        actor_id=p.id,
        action="notification.deliver",
        entity_type="organization",
        entity_id=organization_id,
        details=report.__dict__,
    )
    db.commit()
    return ok(report.__dict__)


@router.post("/notifications/deliveries/{delivery_id}/retry")
def retry_delivery(delivery_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Put a FAILED or SKIPPED delivery back in the queue; the next delivery run sends it."""
    d = db.get(NotificationDelivery, delivery_id)
    n = db.get(Notification, d.notification_id) if d else None
    if d is None or n is None or n.organization_id not in p.org_ids():
        raise NotFound("Delivery not found")
    p.require_org_wide(Permission.MANAGE_PROJECTS, n.organization_id)
    if d.status not in (DeliveryStatus.FAILED, DeliveryStatus.SKIPPED):
        raise Conflict(f"Delivery is {d.status.value}; only FAILED or SKIPPED deliveries can be retried")
    d.status, d.attempts, d.next_attempt_at = DeliveryStatus.PENDING, 0, None
    audit.record(
        db,
        organization_id=n.organization_id,
        actor_id=p.id,
        action="notification.retry",
        entity_type="notification_delivery",
        entity_id=d.id,
        details={"notification_id": n.id, "channel": d.channel},
    )
    db.commit()
    recipient = db.get(User, n.recipient_id)
    return ok(_delivery(d, n, recipient.full_name if recipient else ""))
