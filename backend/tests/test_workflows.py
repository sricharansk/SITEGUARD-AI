"""Resumable orchestration, conflict and uncertainty handling, and resilience (Playbook Prompts 29, 30 and 37)."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.agents import orchestrator, registry
from app.agents.vision import Detection
from app.core.config import get_settings
from app.models import (
    AgentConflict,
    AgentRun,
    AuditEvent,
    CapaAction,
    Incident,
    Notification,
    WorkflowRun,
    WorkflowStatus,
    utcnow,
)
from tests.conftest import auth
from tests.fixtures import images
from tests.test_api import _new_incident
from tests.test_vision import FakeAnalyzer, _analyze, _upload


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_retry_backoff_seconds", 0)


def _investigate(client, iid, who="safety", **params):
    return client.post(f"/incidents/{iid}/investigate", params=params, headers=auth(client, who))


def _actions(db, iid, status="PENDING_REVIEW"):
    return db.scalar(select(func.count()).where(CapaAction.incident_id == iid, CapaAction.approval_status == status))


def _audit_actions(db, entity_id):
    return [e.action for e in db.scalars(select(AuditEvent).where(AuditEvent.entity_id == entity_id))]


# --- Prompt 29: checkpointed, resumable workflow ------------------------------------------------------------------


def test_happy_path_is_checkpointed_stage_by_stage(client, project_id, db):
    inc = _new_incident(client, project_id)
    r = _investigate(client, inc["id"])
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    wf = data["workflow"]
    assert wf["status"] == "COMPLETED" and wf["kind"] == "INVESTIGATION" and wf["current_stage"] is None
    stages = wf["stages"]
    assert list(stages) == list(orchestrator.STAGES)
    assert stages["quality"]["status"] == "SKIPPED"  # triage routed a safety incident to the safety agent only
    for name in ("triage", "safety", "risk", "rca", "compliance", "capa", "approval"):
        assert stages[name]["status"] == "SUCCEEDED", name
    assert stages["capa"]["actions"] == [a["id"] for a in data["proposed_actions"]]
    assert {run["workflow_id"] for run in data["runs"]} == {wf["id"]}
    u = wf["uncertainty"]
    assert set(u) >= {"min_confidence", "confidence_by_agent", "unresolved_questions", "agents_needing_review"}
    assert u["unresolved_questions"] and u["failed_stages"] == []
    assert data["incident_status"] == "PENDING_APPROVAL"
    assert {"workflow.start", "workflow.complete"} <= set(_audit_actions(db, wf["id"]))

    listed = client.get(f"/incidents/{inc['id']}/workflows", headers=auth(client, "auditor")).json()["data"]
    assert [w["id"] for w in listed] == [wf["id"]]
    detail = client.get(f"/workflows/{wf['id']}", headers=auth(client, "auditor")).json()["data"]
    assert [run["agent"] for run in detail["runs"]] == ["triage", "safety", "rca", "compliance", "capa"]
    ws = client.get(f"/incidents/{inc['id']}", headers=auth(client, "auditor")).json()["data"]
    assert ws["workflow"]["id"] == wf["id"] and "conflicts" in ws


def test_human_interrupt_then_resume_uses_the_corrected_record(client, project_id, db):
    inc = _new_incident(
        client,
        project_id,
        title="Worker hurt on site",
        description="A worker was hurt during the morning shift and taken to the first aid room.",
        severity="MEDIUM",
    )
    assert _investigate(client, inc["id"], pause_after="nonsense").status_code == 400
    r = _investigate(client, inc["id"], pause_after="triage")
    wf = r.json()["data"]["workflow"]
    assert wf["status"] == "PAUSED" and wf["current_stage"] == "triage"
    assert "after the triage stage" in wf["status_reason"]
    assert [run["agent"] for run in r.json()["data"]["runs"]] == ["triage"]
    assert r.json()["data"]["incident_status"] == "UNDER_INVESTIGATION"
    assert r.json()["data"]["proposed_actions"] == []

    # While it waits, nothing else can start an AI run on the incident.
    for path in ("investigate", "triage"):
        blocked = client.post(f"/incidents/{inc['id']}/{path}", headers=auth(client, "safety"))
        assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "WORKFLOW_ACTIVE"

    # The person corrects the record, then resumes; later stages read the corrected facts.
    r = client.patch(
        f"/incidents/{inc['id']}",
        json={"description": "A worker fell from height through an unprotected slab edge with no guardrail."},
        headers=auth(client, "safety"),
    )
    assert r.status_code == 200, r.text
    r = client.post(f"/workflows/{wf['id']}/resume", headers=auth(client, "safety"))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["workflow"]["status"] == "COMPLETED"
    agents = [run["agent"] for run in data["runs"]]
    assert agents.count("triage") == 1  # the finished stage is not redone
    safety = next(run for run in data["runs"] if run["agent"] == "safety")
    assert "Fall from height" in safety["output"]["hazards"]
    assert {"workflow.paused", "workflow.resume"} <= set(_audit_actions(db, wf["id"]))
    again = client.post(f"/workflows/{wf['id']}/resume", headers=auth(client, "safety"))
    assert again.status_code == 409


def test_pause_requested_during_a_stage_stops_before_the_next(client, project_id, db, monkeypatch):
    original = orchestrator._agent_stage

    def pausing(db_, wf, inc, name, *args):
        rec = original(db_, wf, inc, name, *args)
        if name == "safety":
            wf.pause_requested = True  # as if POST /workflows/{id}/pause arrived while safety was running
        return rec

    monkeypatch.setattr(orchestrator, "_agent_stage", pausing)
    inc = _new_incident(client, project_id)
    wf = _investigate(client, inc["id"]).json()["data"]["workflow"]
    assert wf["status"] == "PAUSED" and "before the quality stage" in wf["status_reason"]
    assert wf["stages"]["safety"]["status"] == "SUCCEEDED" and "rca" not in wf["stages"]
    r = client.post(f"/workflows/{wf['id']}/pause", headers=auth(client, "safety"))
    assert r.status_code == 409  # already paused


def test_cancel_keeps_results_and_allows_a_new_run(client, project_id, db):
    inc = _new_incident(client, project_id)
    wf = _investigate(client, inc["id"], pause_after="safety").json()["data"]["workflow"]
    url = f"/workflows/{wf['id']}/cancel"
    assert client.post(url, json={"reason": ""}, headers=auth(client, "safety")).status_code == 400
    assert client.post(url, json={"reason": "Wrong incident"}, headers=auth(client, "auditor")).status_code == 403
    assert client.post(url, json={"reason": "Wrong incident"}, headers=auth(client, "other")).status_code == 404
    r = client.post(url, json={"reason": "Investigating manually instead"}, headers=auth(client, "safety"))
    assert r.status_code == 200 and r.json()["data"]["status"] == "CANCELLED"
    kept = db.scalars(select(AgentRun.agent).where(AgentRun.workflow_id == wf["id"])).all()
    assert sorted(kept) == ["safety", "triage"]
    assert client.post(url, json={"reason": "again"}, headers=auth(client, "safety")).status_code == 409
    assert client.post(f"/workflows/{wf['id']}/resume", headers=auth(client, "safety")).status_code == 409
    assert _investigate(client, inc["id"]).json()["data"]["workflow"]["status"] == "COMPLETED"


def test_workflow_authorization_and_tenant_isolation(client, project_id):
    inc = _new_incident(client, project_id)
    wf = _investigate(client, inc["id"], pause_after="triage").json()["data"]["workflow"]
    other, auditor = auth(client, "other"), auth(client, "auditor")
    assert client.get(f"/workflows/{wf['id']}", headers=other).status_code == 404
    assert client.get(f"/incidents/{inc['id']}/workflows", headers=other).status_code == 404
    assert client.get(f"/incidents/{inc['id']}/conflicts", headers=other).status_code == 404
    assert client.post(f"/workflows/{wf['id']}/resume", headers=other).status_code == 404
    assert client.post(f"/workflows/{wf['id']}/resume", headers=auditor).status_code == 403
    assert client.post(f"/workflows/{wf['id']}/pause", headers=auditor).status_code == 403
    assert client.get("/workflows/nope", headers=auditor).status_code == 404
    r = client.post(f"/workflows/{wf['id']}/resume", json={"pause_after": ["bogus"]}, headers=auth(client, "safety"))
    assert r.status_code == 400


# --- Prompt 37: retries, failures as visible states, no duplicates -------------------------------------------------


def test_failing_agent_is_retried_with_a_bound(client, project_id, db, monkeypatch):
    real = registry.AGENTS["rca"].rules
    calls = {"n": 0}

    def flaky(pack):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return real(pack)

    monkeypatch.setattr(registry.AGENTS["rca"], "rules", flaky)
    inc = _new_incident(client, project_id)
    rca = _investigate(client, inc["id"]).json()["data"]["workflow"]["stages"]["rca"]
    assert rca["status"] == "SUCCEEDED" and rca["attempts"] == 2 and rca["errors"] == ["RuntimeError"]

    def broken(pack):
        raise RuntimeError("always")

    monkeypatch.setattr(registry.AGENTS["rca"], "rules", broken)
    inc = _new_incident(client, project_id)
    data = _investigate(client, inc["id"]).json()["data"]
    wf = data["workflow"]
    assert wf["stages"]["rca"]["status"] == "FAILED"
    assert wf["stages"]["rca"]["attempts"] == get_settings().agent_max_attempts
    assert wf["status"] == "COMPLETED" and wf["uncertainty"]["failed_stages"] == ["rca"]
    assert wf["stages"]["capa"]["status"] == "SUCCEEDED"  # one failed agent does not stop the others


def test_crash_after_capa_resumes_without_duplicate_actions(client, project_id, db, monkeypatch):
    original = orchestrator._approval_stage
    crashes = {"left": 1}

    def crash_once(*args):
        if crashes["left"]:
            crashes["left"] -= 1
            raise ConnectionError("database connection dropped")
        return original(*args)

    monkeypatch.setattr(orchestrator, "_approval_stage", crash_once)
    inc = _new_incident(client, project_id)
    r = _investigate(client, inc["id"])
    assert r.status_code == 200, r.text
    wf = r.json()["data"]["workflow"]
    assert wf["status"] == "FAILED" and wf["stages"]["approval"]["status"] == "ERROR"
    assert "ConnectionError" in wf["status_reason"]
    assert r.json()["data"]["incident_status"] == "UNDER_INVESTIGATION"
    proposed = _actions(db, inc["id"])
    assert proposed and proposed == len(wf["stages"]["capa"]["actions"])  # the finished stage was kept
    assert "workflow.failed" in _audit_actions(db, wf["id"])
    note = db.scalar(
        select(Notification).where(Notification.kind == "WORKFLOW_FAILED", Notification.incident_id == inc["id"])
    )
    assert note is not None

    r = client.post(f"/workflows/{wf['id']}/resume", headers=auth(client, "safety"))
    assert r.json()["data"]["workflow"]["status"] == "COMPLETED"
    assert r.json()["data"]["incident_status"] == "PENDING_APPROVAL"
    assert _actions(db, inc["id"]) == proposed  # no duplicate proposals
    runs = db.scalars(select(AgentRun.agent).where(AgentRun.workflow_id == wf["id"])).all()
    assert runs.count("capa") == 1


def test_crash_inside_capa_rolls_back_the_stage_then_creates_actions_once(client, project_id, db, monkeypatch):
    original = orchestrator._propose_actions
    crashes = {"left": 1}

    def crash_after_insert(*args):
        ids = original(*args)
        if crashes["left"]:
            crashes["left"] -= 1
            raise OSError("disk full")
        return ids

    monkeypatch.setattr(orchestrator, "_propose_actions", crash_after_insert)
    inc = _new_incident(client, project_id)
    wf = _investigate(client, inc["id"]).json()["data"]["workflow"]
    assert wf["status"] == "FAILED" and wf["stages"]["capa"]["status"] == "ERROR"
    assert _actions(db, inc["id"]) == 0  # the half-done stage left nothing behind
    r = client.post(f"/workflows/{wf['id']}/resume", headers=auth(client, "safety"))
    data = r.json()["data"]
    assert data["workflow"]["status"] == "COMPLETED"
    assert _actions(db, inc["id"]) == len(data["proposed_actions"]) > 0


def test_running_workflow_lease(client, project_id, db):
    inc = _new_incident(client, project_id)
    row = db.get(Incident, inc["id"])
    wf = WorkflowRun(
        organization_id=row.organization_id,
        incident_id=row.id,
        kind="INVESTIGATION",
        status=WorkflowStatus.RUNNING,
        provider="rules",
        stages={},
        state={},
        pause_after=[],
        started_by=row.reporter_id,
        lease_expires_at=utcnow() + timedelta(minutes=10),
    )
    db.add(wf)
    db.commit()
    # Another process holds the lease: no second run, no resume, no cancel.
    assert _investigate(client, row.id).json()["error"]["code"] == "WORKFLOW_ACTIVE"
    assert client.post(f"/workflows/{wf.id}/resume", headers=auth(client, "safety")).status_code == 409
    # The process died: once the lease expires the run can be resumed from where it stopped.
    wf.lease_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    r = client.post(f"/workflows/{wf.id}/resume", headers=auth(client, "safety"))
    assert r.status_code == 200 and r.json()["data"]["workflow"]["status"] == "COMPLETED"


# --- Prompt 30: conflicts are kept, visible and decided by people --------------------------------------------------


def test_disagreements_are_recorded_routed_and_block_closure(client, project_id, db):
    inc = _new_incident(
        client,
        project_id,
        severity="LOW",
        domain="QUALITY",
        title="Fatal fall from scaffold",
        description="A worker fell from height off the scaffold edge with no guardrail and died at the scene.",
    )
    data = _investigate(client, inc["id"]).json()["data"]
    kinds = {c["kind"] for c in data["conflicts"]}
    assert {"SEVERITY_DISAGREEMENT", "RISK_ABOVE_REPORTED", "DOMAIN_DISAGREEMENT"} <= kinds
    sev = next(c for c in data["conflicts"] if c["kind"] == "SEVERITY_DISAGREEMENT")
    assert sev["details"]["reported"] == "LOW" and sev["status"] == "OPEN"
    assert sev["summary"] in data["flags"]
    assert db.get(Incident, inc["id"]).severity.value == "LOW"  # the AI never overwrites the reported value
    routed = db.scalars(
        select(Notification.recipient_id).where(
            Notification.kind == "AI_CONFLICT", Notification.incident_id == inc["id"]
        )
    ).all()
    assert routed  # reviewers are told

    url = f"/conflicts/{sev['id']}/resolve"
    body = {"resolution": "Fatality confirmed; severity raised to CRITICAL by the HSE manager"}
    assert client.post(url, json={"resolution": ""}, headers=auth(client, "pm")).status_code == 400
    assert client.post(url, json=body, headers=auth(client, "site")).status_code == 403
    assert client.post(url, json=body, headers=auth(client, "other")).status_code == 404
    assert client.post("/conflicts/nope/resolve", json=body, headers=auth(client, "pm")).status_code == 404
    r = client.post(url, json=body, headers=auth(client, "hse"))
    assert r.status_code == 200 and r.json()["data"]["status"] == "RESOLVED" and r.json()["data"]["resolved_by"]
    assert client.post(url, json=body, headers=auth(client, "hse")).status_code == 409

    ws = client.get(f"/incidents/{inc['id']}", headers=auth(client, "auditor")).json()["data"]
    assert any("AI conflict(s) need a recorded human decision" in b for b in ws["close_blockers"])
    assert {c["id"] for c in ws["conflicts"]} == {c["id"] for c in data["conflicts"]}
    report = client.get(f"/incidents/{inc['id']}/report", headers=auth(client, "auditor")).text
    assert "Conflicts found by the investigation" in report
    assert (
        "| SEVERITY_DISAGREEMENT | " in report and "| RESOLVED | " in report and "severity raised to CRITICAL" in report
    )
    assert "| RISK_ABOVE_REPORTED | " in report and "| OPEN | " in report

    # A new investigation keeps the old records: open ones become SUPERSEDED, resolved ones stay resolved.
    first = {c["id"]: c["status"] for c in data["conflicts"]}
    rerun = _investigate(client, inc["id"]).json()["data"]
    statuses = {row.id: row.status for row in db.scalars(select(AgentConflict).where(AgentConflict.id.in_(first)))}
    assert statuses[sev["id"]] == "RESOLVED"
    assert all(statuses[i] == "SUPERSEDED" for i in first if i != sev["id"])
    assert rerun["conflicts"] and all(c["status"] == "OPEN" for c in rerun["conflicts"])


def test_safety_and_quality_disagreement_is_kept(client, project_id, monkeypatch):
    real = registry.AGENTS["quality"].rules

    def mild(pack):
        out = real(pack)
        out.likelihood, out.consequence = 1, 1
        return out

    monkeypatch.setattr(registry.AGENTS["quality"], "rules", mild)
    inc = _new_incident(
        client,
        project_id,
        domain="BOTH",
        title="Formwork collapse during pour",
        description="Formwork failed during the slab pour; honeycombing found and a worker fell from height.",
    )
    data = _investigate(client, inc["id"]).json()["data"]
    found = next(c for c in data["conflicts"] if c["kind"] == "AGENT_DISAGREEMENT")
    assert found["details"]["quality"]["consequence"] == 1 and found["details"]["safety"]["consequence"] >= 3
    assert data["risk"]["consequence"] == found["details"]["safety"]["consequence"]  # the higher value is used


def test_conflicting_documents_are_flagged_with_both_sources(client):
    other = auth(client, "other")
    project = client.get("/projects", headers=other).json()["data"][0]
    for title, height in (("Scaffold Edge Protection Standard", 950), ("Client Scaffold Rules", 1100)):
        r = client.post(
            "/documents",
            json={
                "organization_id": project["organization_id"],
                "project_id": project["id"],
                "title": title,
                "doc_type": "PROCEDURE",
                "source": f"fixture:{title}",
                "domain": "SAFETY",
                "text": f"# Edge protection\n\nScaffold guardrail top rail height must be at least {height} mm "
                "at every open scaffold edge.\n",
            },
            headers=other,
        )
        assert r.status_code in (200, 201), r.text
    inc = _new_incident(
        client,
        project["id"],
        who="other",
        title="Scaffold guardrail too low",
        description="Scaffold guardrail top rail height at the open scaffold edge was found too low during inspection.",
    )
    data = _investigate(client, inc["id"], who="other").json()["data"]
    found = [c for c in data["conflicts"] if c["kind"] == "SOURCE_CONFLICT"]
    assert found, data["conflicts"]
    values = {found[0]["details"]["a"]["value"], found[0]["details"]["b"]["value"]}
    assert values == {950.0, 1100.0}
    assert all(ref.startswith("chunk:") for ref in found[0]["refs"]) and len(found[0]["refs"]) == 2


def test_conflicting_vision_analyses_are_flagged(client, project_id, monkeypatch):
    from app.services import vision

    inc = _new_incident(client, project_id)
    ev = _upload(client, inc["id"], images.site_photo())
    monkeypatch.setattr(vision, "get_analyzer", lambda: FakeAnalyzer([Detection("no_hard_hat", 0.9)]))
    assert _analyze(client, ev["id"], who="hse").status_code == 201
    second = FakeAnalyzer([])
    second.model_version = "fixture-2"
    monkeypatch.setattr(vision, "get_analyzer", lambda: second)
    assert _analyze(client, ev["id"], who="hse").status_code == 201
    data = _investigate(client, inc["id"]).json()["data"]
    found = next(c for c in data["conflicts"] if c["kind"] == "VISION_DISAGREEMENT")
    assert found["details"]["label"] == "no_hard_hat" and found["details"]["evidence_id"] == ev["id"]
    assert len(found["details"]["reported_by"]) == 1 and len(found["details"]["not_reported_by"]) == 1
