from datetime import date, timedelta

from tests.conftest import auth
from tests.test_api import _new_incident


def _approved_action(client, project_id, due: date):
    inc = _new_incident(client, project_id)
    res = client.post(f"/incidents/{inc['id']}/investigate", headers=auth(client, "safety")).json()["data"]
    site_id = client.get("/me", headers=auth(client, "site")).json()["data"]["id"]
    first, *rest = res["proposed_actions"]
    r = client.post(
        f"/capa/{first['id']}/review",
        headers=auth(client, "hse"),
        json={
            "decision": "MODIFY",
            "reason": "Assign owner",
            "changes": {"assignee_id": site_id, "due_date": due.isoformat()},
        },
    )
    assert r.status_code == 200, r.text
    for a in rest:
        client.post(f"/capa/{a['id']}/review", headers=auth(client, "hse"), json={"decision": "REJECT", "reason": "x"})
    return inc, first, site_id


def test_review_and_assignment_notifications(client, project_id):
    inc, action, _ = _approved_action(client, project_id, date.today() + timedelta(days=5))
    hse = client.get("/notifications", headers=auth(client, "hse")).json()["data"]
    assert any(n["kind"] == "REVIEW_REQUIRED" and n["incident_id"] == inc["id"] for n in hse)
    site = client.get("/notifications", params={"unread_only": True}, headers=auth(client, "site")).json()["data"]
    mine = [n for n in site if n["capa_id"] == action["id"]]
    assert mine and mine[0]["kind"] == "CAPA_ASSIGNED"
    r = client.post(f"/notifications/{mine[0]['id']}/read", headers=auth(client, "site"))
    assert r.status_code == 200 and r.json()["data"]["read_at"]
    # Someone else's notification is not visible.
    assert client.post(f"/notifications/{mine[0]['id']}/read", headers=auth(client, "pm")).status_code == 404


def test_overdue_escalation_ladder_is_idempotent(client, project_id, db):
    from app.services import notifications

    due = date.today() - timedelta(days=1)
    inc, action, site_id = _approved_action(client, project_id, due)
    first = notifications.escalate_overdue(db, project_ids=[project_id], actor_id=None)
    mine = [e for e in first if e["capa_id"] == action["id"]]
    assert mine and mine[0]["level"] == 1
    again = notifications.escalate_overdue(db, project_ids=[project_id], actor_id=None)
    assert not [e for e in again if e["capa_id"] == action["id"]]
    later = notifications.escalate_overdue(db, project_ids=[project_id], actor_id=None, today=due + timedelta(days=8))
    lvl2 = [e for e in later if e["capa_id"] == action["id"]]
    assert lvl2 and lvl2[0]["level"] == 2 and lvl2[0]["recipients"] >= 2
    db.commit()
    pm = client.get("/notifications", headers=auth(client, "pm")).json()["data"]
    assert any(n["kind"] == "CAPA_OVERDUE" and n["capa_id"] == action["id"] for n in pm)


def test_escalation_endpoint_permissions(client, project_id):
    assert client.post("/capa/escalate-overdue", json={}, headers=auth(client, "site")).status_code == 403
    assert (
        client.post(
            "/capa/escalate-overdue", json={"project_id": project_id}, headers=auth(client, "other")
        ).status_code
        == 404
    )
    r = client.post("/capa/escalate-overdue", json={"project_id": project_id}, headers=auth(client, "pm"))
    assert r.status_code == 200 and "escalations" in r.json()["data"]


def test_failed_verification_notifies_assignee(client, project_id):
    inc, action, site_id = _approved_action(client, project_id, date.today() + timedelta(days=3))
    site = auth(client, "site")
    client.patch(f"/capa/{action['id']}/progress", headers=site, json={"work_status": "COMPLETED"})
    r = client.post(
        f"/capa/{action['id']}/verify", headers=auth(client, "safety"), json={"effective": False, "notes": "Gap left"}
    )
    assert r.status_code == 200
    notes = client.get("/notifications", headers=site).json()["data"]
    assert any(n["kind"] == "VERIFICATION_FAILED" and n["capa_id"] == action["id"] for n in notes)
