"""In-app notifications and escalation of overdue CAPA actions (docs/API.md#notifications).

Each notification is also queued for email in the same transaction (services/delivery.py).

Escalation ladder for an approved action that is past its due date and not completed:
level 1 on the first overdue day notifies the assignee and everyone holding the owner role;
level 2 after ESCALATE_TO_MANAGEMENT_DAYS notifies the project manager and HSE manager.
Each level is sent once per action, so the job is safe to run repeatedly (for example daily).
"""

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    ApprovalStatus,
    CapaAction,
    Incident,
    Membership,
    Notification,
    Role,
    WorkStatus,
)
from app.services import audit, delivery

ESCALATE_TO_MANAGEMENT_DAYS = 7
ACTIVE = (ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED)


def users_with_roles(db: Session, inc: Incident, roles: set[str]) -> set[str]:
    """Users holding any of the roles for the incident's project (org-wide or project memberships)."""
    rows = db.scalars(
        select(Membership).where(
            Membership.organization_id == inc.organization_id,
            or_(Membership.project_id.is_(None), Membership.project_id == inc.project_id),
        )
    )
    return {m.user_id for m in rows if m.role.value in roles}


def notify(
    db: Session,
    inc: Incident,
    recipients: set[str],
    kind: str,
    message: str,
    capa_id: str | None = None,
) -> list[Notification]:
    out = []
    for user_id in sorted(r for r in recipients if r):
        n = Notification(
            organization_id=inc.organization_id,
            recipient_id=user_id,
            kind=kind,
            message=message,
            incident_id=inc.id,
            capa_id=capa_id,
        )
        delivery.enqueue(n)
        db.add(n)
        out.append(n)
    return out


def review_required(db: Session, inc: Incident, count: int, critical: bool) -> None:
    roles = {Role.HSE_MANAGER.value} if critical else {Role.HSE_MANAGER.value, Role.PROJECT_MANAGER.value}
    notify(
        db,
        inc,
        users_with_roles(db, inc, roles),
        "REVIEW_REQUIRED",
        f"{inc.reference}: {count} AI-proposed action(s) need review"
        + (" by the HSE manager (high/critical risk)." if critical else "."),
    )


def action_assigned(db: Session, inc: Incident, action: CapaAction) -> None:
    if action.assignee_id:
        notify(
            db,
            inc,
            {action.assignee_id},
            "CAPA_ASSIGNED",
            f"{inc.reference}: you own '{action.title}'"
            + (f", due {action.due_date.isoformat()}." if action.due_date else "."),
            action.id,
        )


def verification_failed(db: Session, inc: Incident, action: CapaAction, notes: str) -> None:
    recipients = {action.assignee_id} if action.assignee_id else set()
    if action.owner_role:
        recipients |= users_with_roles(db, inc, {action.owner_role})
    notify(
        db,
        inc,
        recipients,
        "VERIFICATION_FAILED",
        f"{inc.reference}: '{action.title}' failed verification: {notes[:300]}",
        action.id,
    )


def escalate_overdue(
    db: Session,
    *,
    project_ids: list[str],
    actor_id: str | None,
    today: date | None = None,
) -> list[dict]:
    """Escalate overdue approved actions in the given projects. Returns one row per escalation sent."""
    today = today or date.today()
    if not project_ids:
        return []
    rows = db.execute(
        select(CapaAction, Incident)
        .join(Incident, CapaAction.incident_id == Incident.id)
        .where(
            Incident.project_id.in_(project_ids),
            CapaAction.approval_status.in_(ACTIVE),
            CapaAction.due_date.is_not(None),
            CapaAction.due_date < today,
            CapaAction.work_status.not_in([WorkStatus.COMPLETED, WorkStatus.VERIFIED]),
        )
    ).all()
    sent: list[dict] = []
    for action, inc in rows:
        assert action.due_date is not None
        days = (today - action.due_date).days
        level = 2 if days >= ESCALATE_TO_MANAGEMENT_DAYS else 1
        if action.escalation_level >= level:
            continue
        if level == 1:
            recipients = {action.assignee_id} if action.assignee_id else set()
            if action.owner_role:
                recipients |= users_with_roles(db, inc, {action.owner_role})
        else:
            recipients = users_with_roles(db, inc, {Role.PROJECT_MANAGER.value, Role.HSE_MANAGER.value})
        msg = f"{inc.reference}: '{action.title}' is {days} day(s) overdue (due {action.due_date.isoformat()})."
        if level == 2:
            msg += " Escalated to project management."
        notify(db, inc, recipients, "CAPA_OVERDUE", msg, action.id)
        action.escalation_level = level
        audit.record(
            db,
            organization_id=inc.organization_id,
            actor_id=actor_id,
            actor_type="USER" if actor_id else "SYSTEM",
            action="capa.escalate",
            entity_type="capa",
            entity_id=action.id,
            details={"incident_id": inc.id, "level": level, "days_overdue": days, "recipients": len(recipients)},
        )
        sent.append(
            {
                "capa_id": action.id,
                "incident_reference": inc.reference,
                "title": action.title,
                "days_overdue": days,
                "level": level,
                "recipients": len(recipients),
            }
        )
    db.flush()
    return sent
