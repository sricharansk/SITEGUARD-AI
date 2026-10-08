from datetime import UTC, datetime

from tests.conftest import auth

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _new_incident(client, project_id, who="site", **over):
    body = {
        "title": "Worker fell from mobile scaffold tower",
        "description": "A worker fell from height off a mobile scaffold tower with no guardrail and was not wearing a "
        "harness. He was taken to hospital with a suspected fracture.",
        "domain": "SAFETY",
        "severity": "HIGH",
        "occurred_at": datetime.now(UTC).isoformat(),
        "location": "Level 2 corridor",
        "activity": "Ceiling installation",
        "people_involved": 1,
        "immediate_actions": "First aid, ambulance called, tower quarantined.",
    }
    body.update(over)
    r = client.post(f"/projects/{project_id}/incidents", json=body, headers=auth(client, who))
    assert r.status_code == 201, r.text
    return r.json()["data"]


def test_health_and_error_envelope(client):
    assert client.get("/health").json()["data"]["status"] == "ok"
    r = client.get("/projects")
    assert r.status_code == 401
    body = r.json()
    assert body["data"] is None and body["error"]["code"] == "UNAUTHENTICATED"
    assert body["error"]["correlation_id"] == r.headers["X-Correlation-ID"]


def test_bad_login(client):
    r = client.post("/auth/login", json={"email": "hse@demo.siteguard.local", "password": "wrong"})
    assert r.status_code == 401


def test_validation_error_envelope(client, project_id):
    r = client.post(f"/projects/{project_id}/incidents", json={"title": "x"}, headers=auth(client, "site"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"


def test_tenant_isolation(client, project_id):
    inc = _new_incident(client, project_id)
    other = auth(client, "other")
    assert client.get(f"/incidents/{inc['id']}", headers=other).status_code == 404
    assert client.get(f"/projects/{project_id}/incidents", headers=other).status_code == 404
    assert client.post(f"/incidents/{inc['id']}/investigate", headers=other).status_code == 404
    assert all(p["code"] != "RMT-01" for p in client.get("/projects", headers=other).json()["data"])


def test_rbac(client, project_id):
    body = {
        "title": "Viewer attempt",
        "description": "This should not be allowed for read-only roles.",
        "domain": "SAFETY",
        "severity": "LOW",
        "occurred_at": datetime.now(UTC).isoformat(),
    }
    r = client.post(f"/projects/{project_id}/incidents", json=body, headers=auth(client, "auditor"))
    assert r.status_code == 403
    inc = _new_incident(client, project_id)
    assert client.post(f"/incidents/{inc['id']}/investigate", headers=auth(client, "site")).status_code == 403
    assert client.get("/audit", headers=auth(client, "site")).status_code == 403
    assert client.get("/audit", headers=auth(client, "auditor")).status_code == 200


def test_evidence_validation(client, project_id):
    inc = _new_incident(client, project_id)
    h = auth(client, "site")
    bad = client.post(
        f"/incidents/{inc['id']}/evidence", headers=h, files={"file": ("photo.png", b"not really a png", "image/png")}
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "UNSUPPORTED_FILE"
    exe = client.post(
        f"/incidents/{inc['id']}/evidence",
        headers=h,
        files={"file": ("tool.exe", b"MZ....", "application/octet-stream")},
    )
    assert exe.status_code == 400
    ok = client.post(
        f"/incidents/{inc['id']}/evidence",
        headers=h,
        files={"file": ("../../etc/scene photo.png", PNG, "image/png")},
        data={"description": "Scaffold tower with missing guardrail"},
    )
    assert ok.status_code == 201
    ev = ok.json()["data"]
    assert ev["filename"] == "scene_photo.png" and len(ev["sha256"]) == 64
    dl = client.get(f"/evidence/{ev['id']}/download", headers=h)
    assert dl.status_code == 200 and dl.content == PNG


def test_invalid_manual_transition_rejected(client, project_id):
    inc = _new_incident(client, project_id)
    h = auth(client, "pm")
    r = client.post(
        f"/incidents/{inc['id']}/transition", json={"to_status": "ACTION_IN_PROGRESS", "note": "skip"}, headers=h
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_TRANSITION"
    r = client.post(f"/incidents/{inc['id']}/transition", json={"to_status": "CLOSED", "note": "close"}, headers=h)
    assert r.status_code == 400


def test_end_to_end_incident_to_verified_closure(client, project_id):
    inc = _new_incident(client, project_id)
    iid = inc["id"]
    hse, pm, site, safety = (auth(client, w) for w in ("hse", "pm", "site", "safety"))
    client.post(
        f"/incidents/{iid}/evidence",
        headers=site,
        files={"file": ("scene.png", PNG, "image/png")},
        data={"description": "No guardrail on the tower platform"},
    )

    # AI investigation: ends at PENDING_APPROVAL with proposals awaiting review.
    r = client.post(f"/incidents/{iid}/investigate", headers=safety)
    assert r.status_code == 200, r.text
    res = r.json()["data"]
    assert res["incident_status"] == "PENDING_APPROVAL"
    assert [x["agent"] for x in res["runs"]] == ["triage", "safety", "rca", "compliance", "capa"]
    assert all(x["status"] == "SUCCEEDED" for x in res["runs"])
    assert res["risk"]["band"] in ("HIGH", "CRITICAL") and res["risk"]["inputs_source"] == "AI_SUGGESTED"
    actions = res["proposed_actions"]
    assert actions and all(a["approval_status"] == "PENDING_REVIEW" and a["ai_generated"] for a in actions)
    assert all(a["critical"] for a in actions)  # HIGH risk -> HSE manager must approve
    triage_refs = res["runs"][0]["output"]["evidence_refs"]
    assert any(ref.startswith("evidence:") for ref in triage_refs)
    assert any(ref.startswith("chunk:") for ref in triage_refs)

    # Closing now is blocked, and AI output is not an approved action.
    blocked = client.post(f"/incidents/{iid}/close", json={"note": "done"}, headers=hse)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "CLOSE_BLOCKED"

    # Critical actions: project manager may not approve, HSE manager may. Every decision needs a reason.
    a0, a1, *rest = actions
    assert (
        client.post(f"/capa/{a0['id']}/review", json={"decision": "APPROVE", "reason": "ok"}, headers=pm).status_code
        == 403
    )
    r = client.post(
        f"/capa/{a0['id']}/review",
        headers=hse,
        json={
            "decision": "MODIFY",
            "reason": "Name the owner and tighten the date",
            "changes": {"assignee_id": None, "due_date": "2026-12-01"},
        },
    )
    assert r.status_code == 200 and r.json()["data"]["action"]["approval_status"] == "MODIFIED"
    assert r.json()["data"]["action"]["original_ai_output"]["title"] == a0["title"]
    r = client.post(f"/capa/{a1['id']}/review", headers=hse, json={"decision": "APPROVE", "reason": "Proportionate"})
    assert r.status_code == 200
    for a in rest:
        r = client.post(f"/capa/{a['id']}/review", headers=hse, json={"decision": "REJECT", "reason": "Duplicate"})
        assert r.status_code == 200
    assert r.json()["data"]["incident_status"] == "ACTION_IN_PROGRESS"
    # A decided action cannot be decided again.
    again = client.post(f"/capa/{a1['id']}/review", headers=hse, json={"decision": "REJECT", "reason": "x"})
    assert again.status_code == 409

    # Rejected actions cannot be worked on.
    if rest:
        r = client.patch(f"/capa/{rest[0]['id']}/progress", json={"work_status": "COMPLETED"}, headers=site)
        assert r.status_code == 409

    # Site engineer does the work; they cannot verify their own action.
    site_id = client.get("/me", headers=site).json()["data"]["id"]
    for a in (a0, a1):
        r = client.patch(
            f"/capa/{a['id']}/progress",
            headers=site,
            json={"work_status": "COMPLETED", "assignee_id": site_id, "note": "Guardrail fitted"},
        )
        assert r.status_code == 200, r.text
    assert r.json()["data"]["incident_status"] == "PENDING_VERIFICATION"
    assert (
        client.post(f"/capa/{a0['id']}/verify", json={"effective": True, "notes": "mine"}, headers=site).status_code
        == 403
    )

    # A failed verification sends the incident back to work.
    r = client.post(
        f"/capa/{a0['id']}/verify",
        headers=safety,
        json={"effective": False, "notes": "Toe board still missing on one side"},
    )
    assert r.json()["data"]["incident_status"] == "ACTION_IN_PROGRESS"
    client.patch(f"/capa/{a0['id']}/progress", json={"work_status": "COMPLETED"}, headers=site)
    for a in (a0, a1):
        r = client.post(f"/capa/{a['id']}/verify", json={"effective": True, "notes": "Checked on site"}, headers=safety)
        assert r.status_code == 200, r.text

    r = client.post(f"/incidents/{iid}/close", json={"note": "Verified and lessons shared"}, headers=pm)
    assert r.status_code == 200 and r.json()["data"]["status"] == "CLOSED"

    ws = client.get(f"/incidents/{iid}", headers=hse).json()["data"]
    assert [h["to_status"] for h in ws["history"]][-1] == "CLOSED"
    assert len(ws["approvals"]) == len(actions) and len(ws["verifications"]) == 3
    audit = client.get("/audit", params={"entity_id": iid}, headers=auth(client, "auditor")).json()["data"]
    actions_logged = {e["action"] for e in audit}
    assert {"incident.create", "agent.triage.succeeded", "incident.transition"} <= actions_logged
    assert all(e["correlation_id"] for e in audit)


def test_critical_incident_needs_hse_manager_to_close(client, project_id, db):
    from app.models import Incident, IncidentStatus

    inc = _new_incident(client, project_id, severity="CRITICAL")
    row = db.get(Incident, inc["id"])
    row.status = IncidentStatus.PENDING_VERIFICATION
    db.commit()
    r = client.post(f"/incidents/{inc['id']}/close", json={"note": "x"}, headers=auth(client, "pm"))
    assert r.status_code == 403


def test_agent_failure_keeps_incident_and_manual_flow(client, project_id, monkeypatch):
    from app.agents import registry

    inc = _new_incident(client, project_id)

    def boom(pack):
        raise RuntimeError("rules engine crashed")

    monkeypatch.setattr(registry.AGENTS["rca"], "rules", boom)
    r = client.post(f"/incidents/{inc['id']}/investigate", headers=auth(client, "safety"))
    assert r.status_code == 200
    runs = {x["agent"]: x for x in r.json()["data"]["runs"]}
    assert runs["rca"]["status"] == "FAILED" and runs["capa"]["status"] == "SUCCEEDED"
    # Humans can still add their own action.
    r = client.post(
        f"/incidents/{inc['id']}/capa",
        headers=auth(client, "safety"),
        json={
            "action_type": "CORRECTIVE",
            "title": "Manual action",
            "description": "Fix it now",
            "verification_criteria": "Inspected",
        },
    )
    assert r.status_code == 201 and r.json()["data"]["approval_status"] == "PENDING_REVIEW"


def test_dashboard_and_search(client, project_id):
    d = client.get("/dashboard", params={"project_id": project_id}, headers=auth(client, "pm")).json()["data"]
    assert d["totals"]["incidents"] >= 9
    assert d["by_status"].get("CLOSED", 0) >= 4
    assert d["top_hazards"]
    assert d["agents"]["runs"] > 0
    hits = client.get(
        "/search", params={"q": "guardrail toe board edge", "project_id": project_id}, headers=auth(client, "pm")
    ).json()["data"]
    assert hits and "Height" in hits[0]["document_title"]
    agents = client.get("/agents").json()["data"]
    assert {a["name"] for a in agents} == {"triage", "safety", "quality", "rca", "compliance", "capa"}
