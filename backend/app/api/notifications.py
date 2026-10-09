from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import ok
from app.core.db import get_db
from app.core.errors import Conflict, NotFound
from app.core.security import Permission, Principal, current_principal
from app.models import DeliveryStatus, Notification, NotificationDelivery, utcnow
from app.services import audit
from app.services import notifications as service

router = APIRouter(tags=["notifications"])


def _notification(n: Notification) -> dict:
    return {
        "id": n.id,
        "organization_id": n.organization_id,
        "project_id": n.project_id,
        "incident_id": n.incident_id,
        "kind": n.kind,
        "priority": n.priority,
        "title": n.title,
        "body": n.body,
        "entity_type": n.entity_type,
        "entity_id": n.entity_id,
        "created_at": n.created_at,
        "read_at": n.read_at,
    }


def _delivery(d: NotificationDelivery, n: Notification) -> dict:
    return {
        "id": d.id,
        "notification_id": n.id,
        "kind": n.kind,
        "title": n.title,
        "recipient_id": n.recipient_id,
        "channel": d.channel,
        "status": d.status,
        "attempts": d.attempts,
        "last_error": d.last_error,
        "next_attempt_at": d.next_attempt_at,
        "sent_at": d.sent_at,
        "created_at": d.created_at,
    }


@router.get("/notifications")
def my_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """The caller's in-app notifications, newest first, with the unread count."""
    stmt = select(Notification).where(Notification.recipient_id == p.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(Notification.created_at.desc(), Notification.id).limit(limit)).all()
    unread = db.scalar(select(func.count()).where(Notification.recipient_id == p.id, Notification.read_at.is_(None)))
    return ok({"unread": unread, "items": [_notification(n) for n in rows]})


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_id != p.id:
        raise NotFound("Notification not found")
    n.read_at = n.read_at or utcnow()
    db.commit()
    return ok(_notification(n))


@router.post("/notifications/read-all")
def mark_all_read(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    result = db.execute(
        update(Notification)
        .where(Notification.recipient_id == p.id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.commit()
    return ok({"marked": result.rowcount})  # type: ignore[attr-defined]


@router.post("/notifications/run")
def run_jobs(organization_id: str = Query(), p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Run the escalation rules and send due deliveries for one organization (normally a scheduled job)."""
    p.require_org_wide(Permission.MANAGE_PROJECTS, organization_id)
    escalation = service.escalate(db, organization_id=organization_id)
    dispatched = service.dispatch(db, organization_id=organization_id)
    result = {"escalation": escalation.__dict__, "dispatch": dispatched.__dict__}
    audit.record(
        db,
        organization_id=organization_id,
        actor_id=p.id,
        action="notification.run",
        entity_type="organization",
        entity_id=organization_id,
        details=result,
    )
    db.commit()
    return ok(result)


@router.get("/notifications/deliveries")
def list_deliveries(
    organization_id: str = Query(),
    status: DeliveryStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """External delivery outbox for administrators, including FAILED (dead-letter) deliveries."""
    p.require_org_wide(Permission.VIEW_AUDIT, organization_id)
    stmt = (
        select(NotificationDelivery, Notification)
        .join(Notification, Notification.id == NotificationDelivery.notification_id)
        .where(Notification.organization_id == organization_id)
    )
    if status:
        stmt = stmt.where(NotificationDelivery.status == status)
    rows = db.execute(stmt.order_by(NotificationDelivery.created_at.desc()).limit(limit)).all()
    return ok([_delivery(d, n) for d, n in rows])


@router.post("/notifications/deliveries/{delivery_id}/retry")
def retry_delivery(delivery_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    delivery = db.get(NotificationDelivery, delivery_id)
    n = db.get(Notification, delivery.notification_id) if delivery else None
    if delivery is None or n is None:
        raise NotFound("Delivery not found")
    p.require_org_wide(Permission.MANAGE_PROJECTS, n.organization_id)
    if delivery.status not in (DeliveryStatus.FAILED, DeliveryStatus.SKIPPED):
        raise Conflict(f"Delivery is {delivery.status.value}; only FAILED or SKIPPED can be retried", "INVALID_STATE")
    delivery.status, delivery.attempts, delivery.next_attempt_at = DeliveryStatus.PENDING, 0, None
    audit.record(
        db,
        organization_id=n.organization_id,
        actor_id=p.id,
        action="notification.retry",
        entity_type="notification_delivery",
        entity_id=delivery.id,
        details={"notification_id": n.id, "channel": delivery.channel},
    )
    db.commit()
    return ok(_delivery(delivery, n))
