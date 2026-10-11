"""Prompt 48 end-to-end acceptance: one representative incident through the whole controlled lifecycle.

project -> people -> incident -> evidence -> document ingestion -> retrieval -> triage -> investigation -> risk -> RCA
-> compliance -> CAPA -> approval -> task -> verification -> closure -> dashboard / report / audit, with the
authorization and approval checks that must hold at each step. Uses the seeded synthetic organization and the
offline rules provider; no live model is called.
"""

import hashlib
import json
from datetime import UTC, datetime

from tests.conftest import auth
from tests.fixtures import images

PROCEDURE = """# Mobile scaffold towers

Mobile scaffold tower guardrails must be fitted on every open side of the working platform before use.

Mobile scaffold towers must be inspected and tagged by a competent person before first use and every 7 days.

Workers on a mobile scaffold tower platform without guardrails must not start work until the guardrail is fitted.
"""


def _ok(r, status=200):
    assert r.status_code == status, r.text
    body = r.json()
    assert body["error"] is None
    return body["data"]


def test_representative_incident_completes_the_controlled_lifecycle(client, org_id):
    admin, hse, pm, safety, site, auditor, other = (
        auth(client, w) for w in ("admin", "hse", "pm", "safety", "site", "auditor", "other")
    )
    stamp = datetime.now(UTC).strftime("%H%M%S%f")

    # 1. Project with sites; only MANAGE_PROJECTS may create it.
    body = {"organization_id": org_id, "code": f"ACC-{stamp}", "name": "Acceptance tower fit-out", "sites": ["Core"]}
    assert client.post("/projects", json=body, headers=site).status_code == 403
    project = _ok(client.post("/projects", json=body, headers=admin), 201)
    pid = project["id"]
    assert client.get(f"/projects/{pid}", headers=other).status_code == 404  # another tenant cannot see it

    # 2. People: the organization's members get their roles on the new project.
    members = {m["email"]: m for m in _ok(client.get(f"/projects/{pid}/members", headers=pm))}
    assert {"site@demo.siteguard.local", "safety@demo.siteguard.local", "hse@demo.siteguard.local"} <= set(members)

    # 3. Incident reported from site.
    inc = _ok(
        client.post(
            f"/projects/{pid}/incidents",
            headers=site,
            json={
                "title": "Worker fell from mobile scaffold tower without guardrail",
                "description": "A worker fell from a mobile scaffold tower platform with no guardrail on the open "
                "side. The tower was not tagged as inspected and he was not wearing a harness.",
                "domain": "SAFETY",
                "severity": "HIGH",
                "occurred_at": datetime.now(UTC).isoformat(),
                "location": "Core, level 3",
                "activity": "Ceiling installation",
                "people_involved": 1,
                "immediate_actions": "First aid given, tower quarantined, area barricaded.",
            },
        ),
        201,
    )
    iid = inc["id"]
    assert inc["status"] == "REPORTED"
    assert client.post(f"/incidents/{iid}/investigate", headers=auth(client, "auditor")).status_code == 403

    # 4. Evidence: hashed on upload; vision analysis is an observation with its versions and limitations.
    photo = images.site_photo()
    ev = _ok(
        client.post(
            f"/incidents/{iid}/evidence",
            headers=site,
            files={"file": ("tower.jpg", photo, "image/jpeg")},
            data={"description": "Tower platform with the open side unguarded"},
        ),
        201,
    )
    assert ev["sha256"] == hashlib.sha256(photo).hexdigest()
    analysis = _ok(client.post(f"/evidence/{ev['id']}/vision", json={"task": "PPE_HAZARD"}, headers=safety), 201)
    assert analysis["evidence_sha256"] == ev["sha256"] and analysis["taxonomy_version"] and analysis["disclaimer"]
    assert analysis["status"] == "COMPLETED" and analysis["limitations"]

    # 5. Document ingestion into the project, then retrieval with provenance.
    doc = _ok(
        client.post(
            "/documents",
            headers=hse,
            json={
                "organization_id": org_id,
                "project_id": pid,
                "title": f"Tower Scaffold Procedure {stamp}",
                "text": PROCEDURE,
                "doc_type": "PROCEDURE",
                "source": "acceptance-fixture",
                "domain": "SAFETY",
                "version": "2",
            },
        ),
        201,
    )
    hits = _ok(client.get("/search", params={"q": "mobile scaffold tower guardrail", "project_id": pid}, headers=site))
    mine = [h for h in hits if h["document_id"] == doc["id"]]
    assert mine and mine[0]["version"] == "2" and mine[0]["ref"].startswith("chunk:")
    answer = _ok(
        client.post(
            "/knowledge/answer",
            headers=site,
            json={"project_id": pid, "question": "When must mobile scaffold tower guardrails be fitted?"},
        )
    )
    assert answer["status"] == "ANSWERED" and doc["id"] in {c["document_id"] for c in answer["citations"]}

    # 6. Triage, then the investigation paused for review after triage and resumed.
    started = _ok(client.post(f"/incidents/{iid}/investigate", params={"pause_after": "triage"}, headers=safety))
    wf = started["workflow"]
    assert wf["status"] == "PAUSED" and wf["stages"]["triage"]["status"] == "SUCCEEDED"
    res = _ok(client.post(f"/workflows/{wf['id']}/resume", headers=safety))
    assert res["workflow"]["status"] == "COMPLETED" and res["incident_status"] == "PENDING_APPROVAL"
    runs = {r["agent"]: r for r in res["runs"]}
    assert {"triage", "safety", "rca", "compliance", "capa"} <= set(runs)
    assert all(r["status"] == "SUCCEEDED" for r in runs.values())

    # 7. Risk (deterministic), RCA and compliance with cited, in-scope sources.
    assert res["risk"]["band"] in ("HIGH", "CRITICAL") and res["risk"]["matrix_version"]
    assert runs["rca"]["output"]["whys"] and runs["rca"]["output"]["root_causes"]
    compliance = runs["compliance"]["output"]
    assert compliance["disclaimer"] and "certif" not in json.dumps(compliance["findings"]).lower()
    cited = json.dumps([runs[a]["output"] for a in runs])
    assert f"evidence:{ev['id']}" in cited
    assert any(c in cited for c in (f"chunk:{h['ref'].split(':', 1)[1]}" for h in mine))

    # 8. CAPA proposals wait for people; nothing closes on its own.
    actions = res["proposed_actions"]
    assert actions and all(a["approval_status"] == "PENDING_REVIEW" and a["ai_generated"] for a in actions)
    blocked = client.post(f"/incidents/{iid}/close", json={"note": "early"}, headers=hse)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "CLOSE_BLOCKED"

    # 9. Approval: critical actions need the HSE manager; every decision has a reason.
    keep, *drop = actions
    assert (
        client.post(f"/capa/{keep['id']}/review", json={"decision": "APPROVE", "reason": "ok"}, headers=pm).status_code
        == 403
    )
    _ok(client.post(f"/capa/{keep['id']}/review", json={"decision": "APPROVE", "reason": "Proportionate"}, headers=hse))
    for a in drop:
        _ok(client.post(f"/capa/{a['id']}/review", json={"decision": "REJECT", "reason": "Covered"}, headers=hse))

    # 10. Task done by the site engineer, verified by someone else.
    site_id = _ok(client.get("/me", headers=site))["id"]
    _ok(
        client.patch(
            f"/capa/{keep['id']}/progress",
            json={"work_status": "COMPLETED", "assignee_id": site_id, "note": "Guardrails fitted, tower tagged"},
            headers=site,
        )
    )
    assert (
        client.post(f"/capa/{keep['id']}/verify", json={"effective": True, "notes": "mine"}, headers=site).status_code
        == 403
    )
    verified = _ok(
        client.post(f"/capa/{keep['id']}/verify", json={"effective": True, "notes": "Checked on site"}, headers=safety)
    )
    assert verified["incident_status"] == "PENDING_VERIFICATION"

    # 11. Closure: every recorded conflict needs a human decision first; HIGH risk closure by an authorised role.
    for c in _ok(client.get(f"/incidents/{iid}/conflicts", headers=pm)):
        if c["status"] == "OPEN":
            _ok(client.post(f"/conflicts/{c['id']}/resolve", json={"resolution": "Reviewed on site"}, headers=pm))
    closed = _ok(client.post(f"/incidents/{iid}/close", json={"note": "Verified; lessons shared"}, headers=pm))
    assert closed["status"] == "CLOSED"

    # 12. Dashboard, report and audit reflect what happened.
    dash = _ok(client.get("/dashboard", params={"project_id": pid}, headers=pm))
    assert dash["totals"]["incidents"] == 1 and dash["totals"]["closed"] == 1
    report = client.get(f"/incidents/{iid}/report", headers=auditor)
    assert report.status_code == 200
    assert report.headers["X-Report-SHA256"] == hashlib.sha256(report.content).hexdigest()
    text = report.text
    assert inc["reference"] in text and "AI-GENERATED" in text and doc["title"] in text
    assert client.get(f"/incidents/{iid}/report", headers=other).status_code == 404

    audit = _ok(client.get("/audit", params={"entity_id": iid}, headers=auditor))
    logged = {e["action"] for e in audit}
    assert {"incident.create", "incident.transition", "agent.triage.succeeded", "report.generate"} <= logged
    closes = [e for e in audit if e["action"] == "incident.transition" and (e["details"] or {}).get("to") == "CLOSED"]
    assert closes and closes[-1]["actor_id"] == _ok(client.get("/me", headers=pm))["id"]
    assert all(e["correlation_id"] for e in audit)
    ws = _ok(client.get(f"/incidents/{iid}", headers=auditor))
    assert [h["to_status"] for h in ws["history"]][-1] == "CLOSED"
    assert ws["evidence"][0]["sha256"] == ev["sha256"]  # provenance kept to the end
    assert all(c["status"] != "OPEN" for c in ws["conflicts"])
