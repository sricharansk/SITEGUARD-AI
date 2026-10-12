"""Email delivery outbox: queued with each notification, retried with backoff, dead-lettered, retried by admins."""

from datetime import date, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.models import ApprovalStatus, CapaAction, DeliveryStatus, Notification, NotificationDelivery, utcnow
from app.services import delivery
from tests.conftest import auth
from tests.test_notifications import _approved_action


class RecordingEmail:
    name = "recording"

    def __init__(self, fail: bool = False):
        self.fail, self.sent = fail, []

    def send(self, to: str, subject: str, body: str) -> None:
        if self.fail:
            raise ConnectionError("smtp unreachable")
        self.sent.append((to, subject, body))


class DisabledEmail:
    name = "disabled"


def _assignment_delivery(client, project_id, db) -> tuple[NotificationDelivery, Notification]:
    _, action, _ = _approved_action(client, project_id, date.today() + timedelta(days=5))
    n = db.scalars(select(Notification).where(Notification.capa_id == action["id"])).one()
    return n.deliveries[0], n


def test_each_notification_is_queued_and_sent_with_a_link(client, project_id, org_id, db):
    d, n = _assignment_delivery(client, project_id, db)
    assert d.channel == "EMAIL" and d.status == DeliveryStatus.PENDING and d.attempts == 0
    email = RecordingEmail()
    report = delivery.dispatch(db, organization_id=org_id, adapter=email, limit=1000)
    db.commit()
    db.refresh(d)
    assert d.status == DeliveryStatus.SENT and d.sent_at and d.attempts == 1
    to, subject, body = next(m for m in email.sent if n.message in m[2])
    assert to == "site@demo.siteguard.local" and subject == "[Site Guard AI] Capa Assigned"
    assert f"{get_settings().public_web_url}/incident/?id={n.incident_id}" in body and "decision support" in body
    assert report.sent >= 1
    # Already sent: a second run does not send it again.
    again = RecordingEmail()
    delivery.dispatch(db, organization_id=org_id, adapter=again, limit=1000)
    assert not [m for m in again.sent if n.message in m[2]]


def test_failures_back_off_then_dead_letter_without_touching_the_workflow(client, project_id, org_id, db):
    d, n = _assignment_delivery(client, project_id, db)
    now = utcnow()
    broken = RecordingEmail(fail=True)
    delivery.dispatch(db, organization_id=org_id, adapter=broken, now=now, limit=1000)
    assert d.status == DeliveryStatus.PENDING and d.attempts == 1 and "smtp unreachable" in d.last_error
    assert d.next_attempt_at == now + timedelta(minutes=1)
    # Not due yet: nothing happens.
    delivery.dispatch(db, organization_id=org_id, adapter=broken, now=now + timedelta(seconds=30), limit=1000)
    assert d.attempts == 1
    for step in (2, 30):  # due again after each backoff
        delivery.dispatch(db, organization_id=org_id, adapter=broken, now=now + timedelta(minutes=step), limit=1000)
    assert d.attempts == get_settings().notification_max_attempts and d.status == DeliveryStatus.FAILED
    db.commit()
    # The workflow is unaffected: the action is still approved and assigned.
    capa = db.get(CapaAction, n.capa_id)
    assert capa.approval_status == ApprovalStatus.MODIFIED and capa.assignee_id == n.recipient_id

    # Dead letters are listed for administrators and can be put back in the queue.
    params = {"organization_id": org_id, "status": "FAILED"}
    outbox = client.get("/notifications/deliveries", params=params, headers=auth(client, "auditor")).json()["data"]
    row = next(r for r in outbox if r["id"] == d.id)
    assert row["recipient"] == "Sid Site (Site Engineer)" and "@" not in str(row)
    retry = client.post(f"/notifications/deliveries/{d.id}/retry", headers=auth(client, "admin"))
    assert retry.status_code == 200 and retry.json()["data"]["status"] == "PENDING"
    assert client.post(f"/notifications/deliveries/{d.id}/retry", headers=auth(client, "admin")).status_code == 409
    db.expire_all()
    delivery.dispatch(db, organization_id=org_id, adapter=RecordingEmail(), limit=1000)
    db.commit()
    assert db.get(NotificationDelivery, d.id).status == DeliveryStatus.SENT


def test_disabled_delivery_is_skipped_not_sent_later(client, project_id, org_id, db):
    d, _ = _assignment_delivery(client, project_id, db)
    report = delivery.dispatch(db, organization_id=org_id, adapter=DisabledEmail(), limit=1000)
    assert d.status == DeliveryStatus.SKIPPED and d.attempts == 0 and report.skipped >= 1
    later = RecordingEmail()
    delivery.dispatch(db, organization_id=org_id, adapter=later, limit=1000)
    assert d.status == DeliveryStatus.SKIPPED
    db.commit()


def test_outbox_endpoints_are_admin_only_and_tenant_scoped(client, project_id, org_id, db):
    d, _ = _assignment_delivery(client, project_id, db)
    db.commit()
    params = {"organization_id": org_id}
    assert client.get("/notifications/deliveries", params=params, headers=auth(client, "site")).status_code == 403
    assert client.get("/notifications/deliveries", params=params, headers=auth(client, "other")).status_code == 404
    assert client.get("/notifications/deliveries", params=params, headers=auth(client, "hse")).status_code == 200
    assert client.post(f"/notifications/deliveries/{d.id}/retry", headers=auth(client, "other")).status_code == 404
    assert client.post(f"/notifications/deliveries/{d.id}/retry", headers=auth(client, "hse")).status_code == 403
    pending = client.post(f"/notifications/deliveries/{d.id}/retry", headers=auth(client, "admin"))
    assert pending.status_code == 409
    assert client.post("/notifications/deliver", params=params, headers=auth(client, "hse")).status_code == 403
    run = client.post("/notifications/deliver", params=params, headers=auth(client, "admin"))
    # The test settings use the disabled adapter, so due deliveries are skipped, and the run is audited.
    assert run.status_code == 200 and run.json()["data"]["skipped"] >= 1
    audit = client.get("/audit", params={"entity_id": org_id}, headers=auth(client, "auditor")).json()["data"]
    assert any(e["action"] == "notification.deliver" for e in audit)


def test_smtp_adapter_uses_starttls_and_login(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, msg):
            calls.append(("send", msg["To"], msg["Subject"]))

    s = get_settings()
    monkeypatch.setattr(delivery.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(s, "smtp_username", "mailer")
    monkeypatch.setattr(s, "smtp_password", type(s.smtp_password)("not-a-real-password"))
    delivery.SmtpEmail().send("pm@demo.siteguard.local", "[Site Guard AI] Test", "body")
    assert [c[0] for c in calls] == ["connect", "starttls", "login", "send"]
    assert calls[2] == ("login", "mailer", "not-a-real-password")


def test_delivery_job_runs_after_escalation(client):
    from app import jobs

    out = jobs.deliver_notifications()
    assert set(out["delivery"]) == {"sent", "retrying", "failed", "skipped"}
