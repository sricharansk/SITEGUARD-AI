"""Notifications and escalation (Playbook Prompt 24, docs/AGENTS.md#notifications).

Workflow events reach this module through `audit.record`, so every audited change can notify people without each
route remembering to. Notifications are an outbox:

- The in-app notification row is written in the same transaction as the workflow change. Building it never breaks
  that change: any error is logged and the workflow commits without the notification.
- External delivery (email) is a separate `NotificationDelivery` row sent later by `dispatch`, with bounded retries
  and backoff; after the last attempt it is FAILED (dead letter) and can be retried by an administrator. External
  delivery is disabled unless an adapter is configured, and real SMTP is refused in local and test environments.
- Escalations (`escalate`) are time-based rules run by a scheduled job. Every notification has a `dedupe_key`, so
  running the job again does not notify twice.
"""

import logging
import smtplib
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import ROLE_PERMISSIONS, Permission
from app.models import (
    ApprovalStatus,
    AuditEvent,
    CapaAction,
    DeliveryStatus,
    Incident,
    IncidentStatus,
    Membership,
    Notification,
    NotificationDelivery,
    Severity,
    User,
    WorkStatus,
    utcnow,
)

log = logging.getLogger("siteguard.notifications")

OPEN_WORK = (WorkStatus.NOT_STARTED, WorkStatus.IN_PROGRESS, WorkStatus.VERIFICATION_FAILED)
ACTIVE = (ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED)


@dataclass
class Draft:
    kind: str
    priority: str  # INFO | HIGH | CRITICAL
    title: str
    body: str
    recipients: set[str]
    dedupe: str
    entity_type: str
    entity_id: str
    incident: Incident | None = None


# --- recipients ---------------------------------------------------------------------------------------------------


def holders(db: Session, organization_id: str, project_id: str | None, perm: Permission) -> set[str]:
    """Active users whose role on this project (or organization-wide) grants `perm`."""
    roles = [r for r, perms in ROLE_PERMISSIONS.items() if perm in perms]
    stmt = (
        select(Membership.user_id)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == organization_id, Membership.role.in_(roles), User.is_active.is_(True))
    )
    if project_id:
        stmt = stmt.where(or_(Membership.project_id.is_(None), Membership.project_id == project_id))
    else:
        stmt = stmt.where(Membership.project_id.is_(None))
    return set(db.scalars(stmt))


def _active_user(db: Session, user_id: str | None) -> set[str]:
    user = db.get(User, user_id) if user_id else None
    return {user.id} if user is not None and user.is_active else set()


# --- event mapping ------------------------------------------------------------------------------------------------


def _label(inc: Incident) -> str:
    return f"{inc.reference} {inc.title}"


def drafts_for_event(db: Session, ev: AuditEvent) -> list[Draft]:
    """Map one audited workflow event to the notifications it causes. Pure reads; adds nothing."""
    action, d = ev.action, ev.details or {}
    out: list[Draft] = []
    if action == "incident.create":
        inc = db.get(Incident, ev.entity_id)
        if inc is not None and inc.severity in (Severity.HIGH, Severity.CRITICAL):
            perm = Permission.APPROVE_CRITICAL if inc.severity == Severity.CRITICAL else Permission.APPROVE_CAPA
            out.append(
                Draft(
                    "INCIDENT_REPORTED",
                    "CRITICAL" if inc.severity == Severity.CRITICAL else "HIGH",
                    f"{inc.severity.value} incident reported: {_label(inc)}",
                    f"Reported at {inc.location or 'an unrecorded location'}. Review it and the immediate actions.",
                    holders(db, inc.organization_id, inc.project_id, perm) - {ev.actor_id or ""},
                    f"event:{ev.id}",
                    "incident",
                    inc.id,
                    inc,
                )
            )
    elif action == "incident.transition" and d.get("to") == IncidentStatus.PENDING_APPROVAL.value:
        inc = db.get(Incident, ev.entity_id)
        if inc is not None:
            out.append(
                Draft(
                    "REVIEW_REQUIRED",
                    "HIGH" if inc.severity in (Severity.HIGH, Severity.CRITICAL) else "INFO",
                    f"Proposed actions need review: {_label(inc)}",
                    "The investigation proposed corrective and preventive actions. Approve, modify or reject each one.",
                    holders(db, inc.organization_id, inc.project_id, Permission.APPROVE_CAPA),
                    f"event:{ev.id}",
                    "incident",
                    inc.id,
                    inc,
                )
            )
    elif action.startswith("capa."):
        capa = db.get(CapaAction, ev.entity_id)
        inc = db.get(Incident, capa.incident_id) if capa is not None else None
        if capa is None or inc is None:
            return out
        org, proj = inc.organization_id, inc.project_id
        if action == "capa.propose":
            perm = Permission.APPROVE_CRITICAL if capa.critical else Permission.APPROVE_CAPA
            recipients = holders(db, org, proj, perm) - {ev.actor_id or ""}
            out.append(_capa(ev, capa, inc, "REVIEW_REQUIRED", "Action needs review", recipients))
        elif action in ("capa.approve", "capa.modify"):
            out.append(
                _capa(ev, capa, inc, "CAPA_ASSIGNED", "Action approved and assigned to you", _assignee(db, capa))
            )
        elif action == "capa.progress" and d.get("to") == WorkStatus.COMPLETED.value:
            verifiers = holders(db, org, proj, Permission.VERIFY_CAPA) - {capa.assignee_id or "", ev.actor_id or ""}
            out.append(_capa(ev, capa, inc, "VERIFICATION_REQUIRED", "Action completed; verify it", verifiers))
        elif action == "capa.verify" and d.get("effective") is False:
            out.append(_capa(ev, capa, inc, "VERIFICATION_FAILED", "Action failed verification", _assignee(db, capa)))
    elif action.startswith("agent.") and action.endswith(".failed"):
        inc = db.get(Incident, ev.entity_id)
        if inc is not None:
            out.append(
                Draft(
                    "AGENT_FAILED",
                    "INFO",
                    f"An AI step failed on {_label(inc)}",
                    "The incident is unchanged. Continue manually or run the investigation again.",
                    _active_user(db, ev.actor_id),
                    f"event:{ev.id}",
                    "incident",
                    inc.id,
                    inc,
                )
            )
    return [o for o in out if o.recipients]


def _assignee(db: Session, capa: CapaAction) -> set[str]:
    return _active_user(db, capa.assignee_id)


def _capa(ev: AuditEvent, capa: CapaAction, inc: Incident, kind: str, what: str, recipients: set[str]) -> Draft:
    due = f" Due {capa.due_date.isoformat()}." if capa.due_date else ""
    priority = "CRITICAL" if capa.critical else "INFO"
    return Draft(
        kind,
        priority,
        f"{what}: {capa.title}",
        f"Incident {_label(inc)}.{due}",
        recipients,
        f"event:{ev.id}",
        "capa",
        capa.id,
        inc,
    )


def _add(db: Session, draft: Draft, organization_id: str, project_id: str | None) -> list[Notification]:
    keys = {f"{draft.dedupe}:{uid}": uid for uid in sorted(draft.recipients)}
    existing = set(db.scalars(select(Notification.dedupe_key).where(Notification.dedupe_key.in_(keys))))
    added: list[Notification] = []
    for key, uid in keys.items():
        if key in existing:
            continue
        n = Notification(
            organization_id=organization_id,
            project_id=project_id,
            recipient_id=uid,
            kind=draft.kind,
            priority=draft.priority,
            title=draft.title[:300],
            body=draft.body,
            entity_type=draft.entity_type,
            entity_id=draft.entity_id,
            incident_id=draft.incident.id if draft.incident else None,
            dedupe_key=key,
        )
        n.deliveries.append(NotificationDelivery(channel="EMAIL", status=DeliveryStatus.PENDING))
        db.add(n)
        added.append(n)
    return added


def on_audit_event(db: Session, ev: AuditEvent) -> None:
    """Called for every audit event. Never raises: a notification problem must not undo the workflow change."""
    if ev.action.startswith("notification."):
        return
    try:
        with db.no_autoflush:
            drafts = drafts_for_event(db, ev)
            for draft in drafts:
                inc = draft.incident
                _add(db, draft, ev.organization_id, inc.project_id if inc else None)
    except Exception:
        log.exception("notification mapping failed", extra={"extra_fields": {"action": ev.action}})


# --- escalation ---------------------------------------------------------------------------------------------------


@dataclass
class EscalationReport:
    created: int = 0
    rules: dict[str, int] = field(default_factory=dict)

    def count(self, rule: str, added: Iterable[Notification]) -> None:
        n = len(list(added))
        self.created += n
        self.rules[rule] = self.rules.get(rule, 0) + n


def escalate(db: Session, *, organization_id: str, now: datetime | None = None) -> EscalationReport:
    """Time-based rules. Idempotent: each rule notifies a person once per object (and per due date for CAPA)."""
    s = get_settings()
    now = now or utcnow()
    today: date = now.date()
    report = EscalationReport()
    overdue = db.execute(
        select(CapaAction, Incident)
        .join(Incident, Incident.id == CapaAction.incident_id)
        .where(
            Incident.organization_id == organization_id,
            Incident.status != IncidentStatus.CLOSED,
            CapaAction.approval_status.in_(ACTIVE),
            CapaAction.work_status.in_(OPEN_WORK),
            CapaAction.due_date.is_not(None),
            CapaAction.due_date < today,
        )
    ).all()
    for capa, inc in overdue:
        assert capa.due_date is not None
        late = (today - capa.due_date).days
        owners = _assignee(db, capa) or holders(db, inc.organization_id, inc.project_id, Permission.APPROVE_CAPA)
        draft = Draft(
            "CAPA_OVERDUE",
            "CRITICAL" if capa.critical else "HIGH",
            f"Action overdue by {late} day(s): {capa.title}",
            f"Incident {_label(inc)}. Due {capa.due_date.isoformat()}.",
            owners,
            f"capa-overdue:{capa.id}:{capa.due_date.isoformat()}",
            "capa",
            capa.id,
            inc,
        )
        report.count("capa_overdue", _add(db, draft, inc.organization_id, inc.project_id))
        if late >= s.escalation_overdue_days:
            draft = Draft(
                "CAPA_OVERDUE_ESCALATED",
                "CRITICAL",
                f"Escalation: action overdue by {late} days: {capa.title}",
                f"Incident {_label(inc)}. Due {capa.due_date.isoformat()}. Assigned person has been reminded.",
                holders(db, inc.organization_id, inc.project_id, Permission.APPROVE_CRITICAL),
                f"capa-escalated:{capa.id}:{capa.due_date.isoformat()}",
                "capa",
                capa.id,
                inc,
            )
            report.count("capa_overdue_escalated", _add(db, draft, inc.organization_id, inc.project_id))

    cutoff = now - timedelta(hours=s.escalation_unreviewed_hours)
    stale = db.scalars(
        select(Incident).where(
            Incident.organization_id == organization_id,
            Incident.severity.in_([Severity.HIGH, Severity.CRITICAL]),
            Incident.status.in_([IncidentStatus.REPORTED, IncidentStatus.TRIAGED]),
            Incident.reported_at < cutoff,
        )
    ).all()
    for inc in stale:
        draft = Draft(
            "INCIDENT_UNREVIEWED",
            "CRITICAL",
            f"Escalation: {inc.severity.value} incident not investigated: {_label(inc)}",
            f"Reported more than {s.escalation_unreviewed_hours} hours ago and still {inc.status.value}.",
            holders(db, inc.organization_id, inc.project_id, Permission.APPROVE_CRITICAL),
            f"incident-unreviewed:{inc.id}",
            "incident",
            inc.id,
            inc,
        )
        report.count("incident_unreviewed", _add(db, draft, inc.organization_id, inc.project_id))

    review_cutoff = now - timedelta(hours=s.escalation_review_hours)
    waiting = db.execute(
        select(CapaAction, Incident)
        .join(Incident, Incident.id == CapaAction.incident_id)
        .where(
            Incident.organization_id == organization_id,
            CapaAction.critical.is_(True),
            CapaAction.approval_status == ApprovalStatus.PENDING_REVIEW,
            CapaAction.created_at < review_cutoff,
        )
    ).all()
    for capa, inc in waiting:
        draft = Draft(
            "REVIEW_OVERDUE",
            "CRITICAL",
            f"Escalation: critical action awaiting review: {capa.title}",
            f"Incident {_label(inc)}. Waiting more than {s.escalation_review_hours} hours for a decision.",
            holders(db, inc.organization_id, inc.project_id, Permission.APPROVE_CRITICAL),
            f"review-overdue:{capa.id}",
            "capa",
            capa.id,
            inc,
        )
        report.count("review_overdue", _add(db, draft, inc.organization_id, inc.project_id))
    db.flush()
    return report


# --- external delivery --------------------------------------------------------------------------------------------


class EmailAdapter(Protocol):
    name: str

    def send(self, to: str, subject: str, body: str) -> None: ...


class DisabledEmail:
    name = "disabled"

    def send(self, to: str, subject: str, body: str) -> None:  # pragma: no cover - never called
        raise RuntimeError("external delivery is disabled")


class LogEmail:
    """Development adapter: records that an email would be sent, without the body."""

    name = "log"

    def send(self, to: str, subject: str, body: str) -> None:
        log.info("email (log adapter)", extra={"extra_fields": {"to_domain": to.split("@")[-1], "subject": subject}})


class SmtpEmail:
    name = "smtp"

    def send(self, to: str, subject: str, body: str) -> None:
        s = get_settings()
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
        msg.set_content(body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password.get_secret_value())
            smtp.send_message(msg)


def get_email_adapter() -> EmailAdapter:
    adapters: dict[str, type[EmailAdapter]] = {"disabled": DisabledEmail, "log": LogEmail, "smtp": SmtpEmail}
    return adapters[get_settings().notification_email_adapter]()


@dataclass
class DispatchReport:
    sent: int = 0
    retrying: int = 0
    failed: int = 0
    skipped: int = 0


def backoff(attempts: int) -> timedelta:
    return timedelta(minutes=5 ** (attempts - 1))  # 1, 5, 25 minutes


def _email_text(n: Notification) -> str:
    link = f"{get_settings().public_web_url.rstrip('/')}/incidents/{n.incident_id}" if n.incident_id else ""
    return f"{n.title}\n\n{n.body}\n\n{link}\n\nSite Guard AI - decision support; check before acting.".strip()


def dispatch(
    db: Session,
    *,
    organization_id: str | None = None,
    adapter: EmailAdapter | None = None,
    now: datetime | None = None,
    limit: int = 200,
) -> DispatchReport:
    """Send due external deliveries. A failure only changes the delivery row, never the workflow."""
    adapter = adapter or get_email_adapter()
    now = now or utcnow()
    max_attempts = get_settings().notification_max_attempts
    stmt = (
        select(NotificationDelivery, Notification, User)
        .join(Notification, Notification.id == NotificationDelivery.notification_id)
        .join(User, User.id == Notification.recipient_id)
        .where(
            NotificationDelivery.status == DeliveryStatus.PENDING,
            or_(NotificationDelivery.next_attempt_at.is_(None), NotificationDelivery.next_attempt_at <= now),
        )
        .order_by(NotificationDelivery.created_at)
        .limit(limit)
    )
    if organization_id:
        stmt = stmt.where(Notification.organization_id == organization_id)
    report = DispatchReport()
    for delivery, n, user in db.execute(stmt).all():
        if adapter.name == "disabled":
            delivery.status, delivery.last_error = DeliveryStatus.SKIPPED, "external delivery disabled"
            report.skipped += 1
            continue
        delivery.attempts += 1
        try:
            adapter.send(user.email, f"[Site Guard AI] {n.title}", _email_text(n))
        except Exception as exc:
            delivery.last_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            if delivery.attempts >= max_attempts:
                delivery.status = DeliveryStatus.FAILED
                report.failed += 1
                log.error("notification delivery failed", extra={"extra_fields": {"delivery_id": delivery.id}})
            else:
                delivery.next_attempt_at = now + backoff(delivery.attempts)
                report.retrying += 1
            continue
        delivery.status, delivery.sent_at, delivery.last_error = DeliveryStatus.SENT, now, None
        report.sent += 1
    db.flush()
    return report
