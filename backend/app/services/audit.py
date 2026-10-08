from contextvars import ContextVar

from sqlalchemy.orm import Session

from app.models import AuditEvent

current_correlation_id: ContextVar[str | None] = ContextVar("current_correlation_id", default=None)


def record(
    db: Session,
    *,
    organization_id: str,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict | None = None,
    actor_type: str = "USER",
) -> AuditEvent:
    """Append an audit event. Callers commit as part of their own transaction."""
    event = AuditEvent(
        organization_id=organization_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
        correlation_id=current_correlation_id.get(),
    )
    db.add(event)
    return event
