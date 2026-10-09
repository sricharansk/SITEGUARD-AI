"""Notifications and escalation (Prompt 24): event mapping, retries, duplicate prevention, failure isolation."""

from datetime import date, timedelta

from sqlalchemy import select

from app.models import (
    CapaAction,
    DeliveryStatus,
    Incident,
    Notification,
    NotificationDelivery,
    User,
    utcnow,
)
from app.services import notifications
from tests.conftest import auth
from tests.test_api import _new_incident


def _mine(client, who: str, **params) -> list[dict]:
    r = client.get("/notifications", params=params, headers=auth(client, who))
    assert r.status_code == 200, r.text
    return r.json()["data"]["items"]


def _kinds_for(client, who: str, entity_id: str) -> set[str]:
    return {n["kind"] for n in _mine(client, who, limit=200) if n["entity_id"] == entity_id}


def _uid(client, who: str) -> str:
    return client.get("/me", headers=auth(client, who)).json()["data"]["id"]


def test_critical_incident_notifies_critical_approvers_only(client, project_id):
    inc = _new_incident(client, project_id, severity="CRITICAL", title="Crane load dropped near workers")
    assert "INCIDENT_REPORTED" in _kinds_for(client, "hse", inc["id"])
    note = next(n for n in _mine(client, "hse") if n["entity_id"] == inc["id"])
    assert note["priority"] == "CRITICAL" and inc["reference"] in note["title"] and note["read_at"] is None
    assert not _kinds_for(client, "pm", inc["id"])  # project managers cannot approve critical work
    assert not _kinds_for(client, "site", inc["id"])  # the reporter is not notified of their own report
    assert not _kinds_for(client, "other", inc["id"])  # never across tenants
    low = _new_incident(client, project_id, severity="LOW", title="Minor housekeeping issue")
    assert not _kinds_for(client, "hse", low["id"])


def test_workflow_events_map_to_notifications(client, project_id):
    inc = _new_incident(client, project_id)
    iid = inc["id"]
    hse, site, safety = auth(client, "hse"), auth(client, "site"), auth(client, "safety")
    res = client.post(f"/incidents/{iid}/investigate", headers=safety).json()["data"]
    assert "REVIEW_REQUIRED" in _kinds_for(client, "pm", iid) and "REVIEW_REQUIRED" in _kinds_for(client, "hse", iid)
    first, *rest = res["proposed_actions"]
    site_id = _uid(client, "site")
    r = client.post(
        f"/capa/{first['id']}/review",
        headers=hse,
        json={"decision": "MODIFY", "reason": "Assign to site", "changes": {"assignee_id": site_id}},
    )
    assert r.status_code == 200
    assert "CAPA_ASSIGNED" in _kinds_for(client, "site", first["id"])
    for a in rest:
        client.post(f"/capa/{a['id']}/review", headers=hse, json={"decision": "REJECT", "reason": "Duplicate"})
    r = client.patch(f"/capa/{first['id']}/progress", json={"work_status": "COMPLETED"}, headers=site)
    assert r.status_code == 200
    assert "VERIFICATION_REQUIRED" in _kinds_for(client, "safety", first["id"])
    assert "VERIFICATION_REQUIRED" not in _kinds_for(client, "site", first["id"])  # assignees cannot verify
    r = client.post(
        f"/capa/{first['id']}/verify", json={"effective": False, "notes": "Guardrail missing on level 3"}, headers=hse
    )
    assert r.status_code == 200
    assert "VERIFICATION_FAILED" in _kinds_for(client, "site", first["id"])


def test_read_state_is_per_recipient(client, project_id):
    inc = _new_incident(client, project_id, severity="CRITICAL", title="Trench wall collapse")
    note = next(n for n in _mine(client, "hse") if n["entity_id"] == inc["id"])
    assert client.post(f"/notifications/{note['id']}/read", headers=auth(client, "other")).status_code == 404
    assert client.post(f"/notifications/{note['id']}/read", headers=auth(client, "pm")).status_code == 404
    r = client.post(f"/notifications/{note['id']}/read", headers=auth(client, "hse"))
    assert r.status_code == 200 and r.json()["data"]["read_at"]
    assert all(n["id"] != note["id"] for n in _mine(client, "hse", unread_only=True))
    assert client.post("/notifications/read-all", headers=auth(client, "hse")).status_code == 200
    data = client.get("/notifications", headers=auth(client, "hse")).json()["data"]
    assert data["unread"] == 0
    assert client.get("/notifications", params={"limit": 0}, headers=auth(client, "hse")).status_code == 400
    assert client.get("/notifications").status_code == 401


def test_notification_failure_does_not_lose_workflow_state(client, project_id, db, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("notification store unavailable")

    monkeypatch.setattr(notifications, "drafts_for_event", broken)
    inc = _new_incident(client, project_id, severity="CRITICAL", title="Scaffold collapse during strike")
    stored = db.get(Incident, inc["id"])
    assert stored is not None and stored.status.value == "REPORTED"
    assert not db.scalars(select(Notification).where(Notification.entity_id == inc["id"])).all()


class _Failing:
    name = "fake"

    def __init__(self):
        self.calls = 0

    def send(self, to, subject, body):
        self.calls += 1
        raise ConnectionError("smtp down")


class _Recording:
    name = "fake"

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send(self, to, subject, body):
        self.sent.append((to, subject))


def test_dispatch_retries_with_backoff_then_dead_letters(client, project_id, db):
    inc = _new_incident(client, project_id, severity="CRITICAL", title="Live cable struck by excavator")
    org = inc["organization_id"]
    delivery = db.scalars(
        select(NotificationDelivery).join(Notification).where(Notification.entity_id == inc["id"])
    ).one()
    other_pending = {
        d.id
        for d in db.scalars(select(NotificationDelivery).where(NotificationDelivery.status == DeliveryStatus.PENDING))
    } - {delivery.id}
    for d in other_pending:  # keep this test about one delivery
        db.get(NotificationDelivery, d).status = DeliveryStatus.SKIPPED
    db.commit()
    now = utcnow()
    adapter = _Failing()
    first = notifications.dispatch(db, organization_id=org, adapter=adapter, now=now)
    assert first.retrying == 1 and delivery.attempts == 1 and delivery.status == DeliveryStatus.PENDING
    assert notifications.dispatch(db, organization_id=org, adapter=adapter, now=now).retrying == 0  # not due yet
    notifications.dispatch(db, organization_id=org, adapter=adapter, now=now + timedelta(minutes=2))
    last = notifications.dispatch(db, organization_id=org, adapter=adapter, now=now + timedelta(minutes=30))
    assert last.failed == 1 and delivery.status == DeliveryStatus.FAILED and adapter.calls == 3
    assert "smtp down" in (delivery.last_error or "")
    db.commit()
    assert db.get(Incident, inc["id"]).status.value == "REPORTED"  # workflow state untouched

    failed = client.get(
        "/notifications/deliveries",
        params={"organization_id": org, "status": "FAILED"},
        headers=auth(client, "auditor"),
    ).json()["data"]
    assert any(f["id"] == delivery.id for f in failed)
    assert (
        client.post(f"/notifications/deliveries/{delivery.id}/retry", headers=auth(client, "site")).status_code == 403
    )
    r = client.post(f"/notifications/deliveries/{delivery.id}/retry", headers=auth(client, "admin"))
    assert r.status_code == 200 and r.json()["data"]["status"] == "PENDING"
    again = client.post(f"/notifications/deliveries/{delivery.id}/retry", headers=auth(client, "admin"))
    assert again.status_code == 409
    db.expire_all()
    ok = _Recording()
    assert notifications.dispatch(db, organization_id=org, adapter=ok, now=now + timedelta(hours=1)).sent == 1
    assert notifications.dispatch(db, organization_id=org, adapter=ok, now=now + timedelta(hours=2)).sent == 0
    assert len(ok.sent) == 1 and ok.sent[0][0] == "hse@demo.siteguard.local"
    db.commit()


def test_external_delivery_is_disabled_by_default(client, project_id, db):
    inc = _new_incident(client, project_id, severity="CRITICAL", title="Formwork failure on deck pour")
    report = notifications.dispatch(db, organization_id=inc["organization_id"])
    assert report.skipped >= 1 and report.sent == 0
    delivery = db.scalars(
        select(NotificationDelivery).join(Notification).where(Notification.entity_id == inc["id"])
    ).one()
    assert delivery.status == DeliveryStatus.SKIPPED and delivery.last_error == "external delivery disabled"
    db.commit()


def test_escalation_rules_are_idempotent(client, project_id, db):
    inc = _new_incident(client, project_id, severity="HIGH", title="Unguarded slab edge on level 5")
    site_id = _uid(client, "site")
    capa = client.post(
        f"/incidents/{inc['id']}/capa",
        json={
            "action_type": "CORRECTIVE",
            "title": "Install edge protection on level 5",
            "description": "Guardrails and toe boards on every open edge.",
            "assignee_id": site_id,
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
            "verification_criteria": "Walkdown confirms edge protection",
        },
        headers=auth(client, "safety"),
    ).json()["data"]
    r = client.post(f"/capa/{capa['id']}/approve", json={"reason": "Needed"}, headers=auth(client, "hse"))
    assert r.status_code == 200, r.text
    org = inc["organization_id"]
    now = utcnow()

    def kinds(entity_id: str, user_email: str) -> list[str]:
        user = db.scalars(select(User).where(User.email == user_email)).one()
        return [
            n.kind
            for n in db.scalars(
                select(Notification).where(Notification.entity_id == entity_id, Notification.recipient_id == user.id)
            )
        ]

    first = notifications.escalate(db, organization_id=org, now=now)
    assert first.rules.get("capa_overdue", 0) >= 1
    assert kinds(capa["id"], "site@demo.siteguard.local").count("CAPA_OVERDUE") == 1
    again = notifications.escalate(db, organization_id=org, now=now)
    assert kinds(capa["id"], "site@demo.siteguard.local").count("CAPA_OVERDUE") == 1
    assert again.rules.get("capa_overdue", 0) == 0

    later = notifications.escalate(db, organization_id=org, now=now + timedelta(days=10))
    assert later.rules.get("capa_overdue_escalated", 0) >= 1
    assert "CAPA_OVERDUE_ESCALATED" in kinds(capa["id"], "hse@demo.siteguard.local")
    assert "INCIDENT_UNREVIEWED" in kinds(inc["id"], "hse@demo.siteguard.local")
    notifications.escalate(db, organization_id=org, now=now + timedelta(days=11))
    assert kinds(inc["id"], "hse@demo.siteguard.local").count("INCIDENT_UNREVIEWED") == 1
    assert db.get(CapaAction, capa["id"]).work_status.value == "NOT_STARTED"  # escalation never changes work
    db.commit()


def test_run_endpoint_contract(client, org_id):
    r = client.post("/notifications/run", params={"organization_id": org_id}, headers=auth(client, "admin"))
    assert r.status_code == 200 and set(r.json()["data"]) == {"escalation", "dispatch"}
    assert client.post("/notifications/run", headers=auth(client, "admin")).status_code == 400
    assert (
        client.post("/notifications/run", params={"organization_id": org_id}, headers=auth(client, "site")).status_code
        == 403
    )
    assert (
        client.post("/notifications/run", params={"organization_id": org_id}, headers=auth(client, "other")).status_code
        == 404
    )
    assert (
        client.get(
            "/notifications/deliveries", params={"organization_id": org_id}, headers=auth(client, "site")
        ).status_code
        == 403
    )
    assert client.post("/notifications/deliveries/nope/retry", headers=auth(client, "admin")).status_code == 404


def test_real_email_is_refused_in_local_and_test():
    import pytest

    from app.core.config import Settings
    from app.main import validate_settings

    for env in ("local", "test"):
        with pytest.raises(RuntimeError):
            validate_settings(Settings(_env_file=None, env=env, notification_email_adapter="smtp"))
    validate_settings(Settings(_env_file=None, env="local", notification_email_adapter="log"))
    staging = Settings(_env_file=None, env="staging", jwt_secret="x" * 40, notification_email_adapter="smtp")
    validate_settings(staging)
    assert notifications.get_email_adapter().name == "disabled"  # the test suite's own settings
