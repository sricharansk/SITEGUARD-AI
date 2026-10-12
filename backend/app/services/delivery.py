"""Email delivery of notifications through an outbox (docs/API.md#notifications).

Every in-app notification gets one EMAIL row in `notification_deliveries`, written in the same transaction as the
workflow change that caused it. `dispatch` (the `deliver-notifications` job) sends due rows with the configured
adapter. A failure only changes the delivery row, never the workflow: the row is retried with backoff and, after
`SITEGUARD_NOTIFICATION_MAX_ATTEMPTS`, becomes FAILED (dead letter) until an administrator retries it. With the
`disabled` adapter rows become SKIPPED, so turning email on later does not flood people with old notifications.
"""

import logging
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DeliveryStatus, Notification, NotificationDelivery, User, utcnow

log = logging.getLogger("siteguard.delivery")
EMAIL = "EMAIL"
FOOTER = "Site Guard AI is decision support: check the record in Site Guard before acting."


class EmailAdapter(Protocol):
    name: str

    def send(self, to: str, subject: str, body: str) -> None: ...


class DisabledEmail:
    name = "disabled"

    def send(self, to: str, subject: str, body: str) -> None:  # pragma: no cover - dispatch never calls it
        raise RuntimeError("email delivery is disabled")


class LogEmail:
    """Development adapter: logs that an email would be sent, without the address or the content."""

    name = "log"

    def send(self, to: str, subject: str, body: str) -> None:
        log.info("email (log adapter)", extra={"extra_fields": {"to_domain": to.rsplit("@", 1)[-1]}})


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


def enqueue(notification: Notification) -> None:
    notification.deliveries.append(NotificationDelivery(channel=EMAIL, status=DeliveryStatus.PENDING))


def backoff(attempts: int) -> timedelta:
    return timedelta(minutes=5 ** (attempts - 1))  # 1, 5, 25 ... minutes


def subject(n: Notification) -> str:
    return f"[Site Guard AI] {n.kind.replace('_', ' ').title()}"


def body(n: Notification) -> str:
    base = get_settings().public_web_url.rstrip("/")
    link = f"{base}/incident/?id={n.incident_id}" if n.incident_id else f"{base}/"
    return f"{n.message}\n\nOpen in Site Guard: {link}\n\n{FOOTER}"


@dataclass
class DispatchReport:
    sent: int = 0
    retrying: int = 0
    failed: int = 0
    skipped: int = 0


def dispatch(
    db: Session,
    *,
    organization_id: str | None = None,
    adapter: EmailAdapter | None = None,
    now: datetime | None = None,
    limit: int = 200,
) -> DispatchReport:
    """Send due deliveries (optionally for one organization). Safe to run repeatedly."""
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
        .order_by(NotificationDelivery.created_at, NotificationDelivery.id)
        .limit(limit)
    )
    if organization_id:
        stmt = stmt.where(Notification.organization_id == organization_id)
    report = DispatchReport()
    for delivery, n, user in db.execute(stmt).all():
        if adapter.name == "disabled":
            delivery.status, delivery.last_error = DeliveryStatus.SKIPPED, "email delivery disabled"
            report.skipped += 1
            continue
        if not user.is_active:
            delivery.status, delivery.last_error = DeliveryStatus.SKIPPED, "recipient is inactive"
            report.skipped += 1
            continue
        delivery.attempts += 1
        try:
            adapter.send(user.email, subject(n), body(n))
        except Exception as exc:  # any adapter error is recorded on the row; the next run retries it
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
