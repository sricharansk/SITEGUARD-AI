"""Incident state machine. CLOSED is only reachable through services.capa.close_incident."""

from sqlalchemy.orm import Session

from app.core.errors import Conflict
from app.models import Incident, IncidentEvent, IncidentStatus, utcnow
from app.services import audit

S = IncidentStatus

TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    S.REPORTED: {S.TRIAGED, S.UNDER_INVESTIGATION},
    S.TRIAGED: {S.UNDER_INVESTIGATION},
    S.UNDER_INVESTIGATION: {S.PENDING_APPROVAL},
    S.PENDING_APPROVAL: {S.ACTION_IN_PROGRESS, S.UNDER_INVESTIGATION},
    S.ACTION_IN_PROGRESS: {S.PENDING_VERIFICATION, S.UNDER_INVESTIGATION},
    S.PENDING_VERIFICATION: {S.CLOSED, S.ACTION_IN_PROGRESS},
    S.CLOSED: {S.UNDER_INVESTIGATION},  # reopen
}


def can_transition(current: IncidentStatus, target: IncidentStatus) -> bool:
    return target in TRANSITIONS.get(current, set())


def transition(
    db: Session,
    incident: Incident,
    target: IncidentStatus,
    *,
    actor_id: str | None,
    note: str | None = None,
    actor_type: str = "USER",
) -> None:
    current = IncidentStatus(incident.status)
    if not can_transition(current, target):
        raise Conflict(f"Invalid transition {current.value} -> {target.value}", "INVALID_TRANSITION")
    incident.status = target
    incident.closed_at = utcnow() if target == S.CLOSED else None
    db.add(
        IncidentEvent(
            incident_id=incident.id,
            actor_id=actor_id,
            from_status=current.value,
            to_status=target.value,
            note=note,
        )
    )
    audit.record(
        db,
        organization_id=incident.organization_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action="incident.transition",
        entity_type="incident",
        entity_id=incident.id,
        details={"from": current.value, "to": target.value, "note": note},
    )


def advance_to(
    db: Session,
    incident: Incident,
    target: IncidentStatus,
    *,
    actor_id: str | None,
    note: str,
    actor_type: str = "USER",
) -> None:
    """Walk the shortest forward path to target (used by the orchestrator: REPORTED -> ... -> PENDING_APPROVAL)."""
    order = [S.REPORTED, S.TRIAGED, S.UNDER_INVESTIGATION, S.PENDING_APPROVAL]
    current = IncidentStatus(incident.status)
    if current == target:
        return
    if current in order and target in order and order.index(current) < order.index(target):
        for step in order[order.index(current) + 1 : order.index(target) + 1]:
            transition(db, incident, step, actor_id=actor_id, note=note, actor_type=actor_type)
        return
    transition(db, incident, target, actor_id=actor_id, note=note, actor_type=actor_type)
