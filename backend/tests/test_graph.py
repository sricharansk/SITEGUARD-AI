"""Knowledge graph (Playbook Prompt 28).

Gate: graph relationships trace back to relational records. Covers idempotent sync, every relationship type,
provenance back to PostgreSQL rows, deletion propagation, tenant and project isolation, both endpoints, the Neo4j
adapter's Cypher (fake driver) and, when SITEGUARD_TEST_NEO4J_URI is set, a real Neo4j server.
"""

import os
import re
import secrets
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import (
    AgentRun,
    ApprovalEvent,
    CapaAction,
    Document,
    DocumentChunk,
    Evidence,
    Incident,
    Membership,
    Organization,
    Project,
    Role,
    Site,
    User,
    VerificationRecord,
)
from app.services import graph
from tests.conftest import PASSWORD, auth
from tests.test_api import PNG, _new_incident

MODELS = {
    "organizations": Organization,
    "projects": Project,
    "sites": Site,
    "users": User,
    "memberships": Membership,
    "incidents": Incident,
    "evidence": Evidence,
    "documents": Document,
    "agent_runs": AgentRun,
    "capa_actions": CapaAction,
    "approval_events": ApprovalEvent,
    "verification_records": VerificationRecord,
}
REVIEW_VALUES = {"UNREVIEWED", "HUMAN_APPROVED", "HUMAN_MODIFIED", "HUMAN_REJECTED", "SUPERSEDED"}


def _user(db, email: str, memberships: list[tuple[str, str | None, Role]]) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, full_name=email.split("@")[0], password_hash=hash_password(PASSWORD))
        db.add(user)
        db.flush()
        for org_id, project_id, role in memberships:
            db.add(Membership(user_id=user.id, organization_id=org_id, project_id=project_id, role=role))
        db.commit()
    return user


@pytest.fixture(scope="module")
def scenario(client, project_id, org_id) -> dict:
    """One incident driven through every recorded step the graph projects, plus project-scoped records."""
    project = client.get(f"/projects/{project_id}", headers=auth(client, "hse")).json()["data"]
    site_id = project["sites"][0]["id"]
    inc = _new_incident(client, project_id, site_id=site_id, location="Level 4 east edge, bay 7")
    iid = inc["id"]
    site, hse, safety = auth(client, "site"), auth(client, "hse"), auth(client, "safety")
    r = client.post(
        f"/incidents/{iid}/evidence",
        headers=site,
        files={"file": ("scene.png", PNG, "image/png")},
        data={"description": "Scaffold tower with no guardrail"},
    )
    assert r.status_code == 201, r.text
    evidence_id = r.json()["data"]["id"]
    res = client.post(f"/incidents/{iid}/investigate", headers=safety).json()["data"]
    first, second, *rest = res["proposed_actions"]
    site_user = client.get("/me", headers=site).json()["data"]["id"]
    review = {"decision": "MODIFY", "reason": "Assign to site", "changes": {"assignee_id": site_user}}
    assert client.post(f"/capa/{first['id']}/review", headers=hse, json=review).status_code == 200
    reject = {"decision": "REJECT", "reason": "Duplicate of the first action"}
    assert client.post(f"/capa/{second['id']}/review", headers=hse, json=reject).status_code == 200
    for a in rest:
        assert client.post(f"/capa/{a['id']}/approve", headers=hse, json={"reason": "Proportionate"}).status_code == 200
    r = client.patch(f"/capa/{first['id']}/progress", json={"work_status": "COMPLETED"}, headers=site)
    assert r.status_code == 200, r.text
    verify = {"effective": False, "notes": "Guardrail still missing on bay 7", "evidence_id": evidence_id}
    assert client.post(f"/capa/{first['id']}/verify", headers=hse, json=verify).status_code == 200
    doc = {
        "organization_id": org_id,
        "project_id": project_id,
        "title": "Tower A edge protection plan",
        "text": "# Edge protection\n\nEdges on Tower A keep a guardrail, mid rail and toe board at all times.",
        "doc_type": "PLAN",
        "source": "test",
    }
    r = client.post("/documents", json=doc, headers=auth(client, "qa"))
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        scoped = _user(db, "graph-scoped@demo.siteguard.local", [(org_id, project_id, Role.PROJECT_MANAGER)])
    return {
        "incident_id": iid,
        "evidence_id": evidence_id,
        "assigned": first["id"],
        "rejected": second["id"],
        "document_id": r.json()["data"]["id"],
        "site_id": site_id,
        "scoped_user_id": scoped.id,
    }


@pytest.fixture
def memory_store(monkeypatch):
    graph.close_store()
    monkeypatch.setattr(get_settings(), "graph_backend", "memory")
    yield graph.get_store()
    graph.close_store()


def _by_type(projection: graph.Projection) -> dict[str, list[graph.Rel]]:
    out: dict[str, list[graph.Rel]] = {}
    for r in projection.rels:
        out.setdefault(r.type, []).append(r)
    return out


def test_sync_is_idempotent(db, org_id, scenario):
    store = graph.InMemoryGraphStore()
    first = graph.sync(db, store, org_id)
    assert first.nodes_created == first.nodes > 50 and first.relationships_created == first.relationships > 100
    before = store.snapshot(org_id)
    again = graph.sync(db, store, org_id)
    assert (again.nodes, again.relationships) == (first.nodes, first.relationships)
    assert again.nodes_created == again.nodes_deleted == again.relationships_created == again.relationships_deleted == 0
    assert store.snapshot(org_id) == before
    assert graph.build_projection(db, org_id) == graph.build_projection(db, org_id)  # deterministic ids and values


def test_every_entity_and_relationship_type_is_built(db, org_id, scenario):
    projection = graph.build_projection(db, org_id)
    assert {n.label for n in projection.nodes} == set(graph.NODE_LABELS)
    rels = _by_type(projection)
    assert set(rels) == set(graph.REL_SCHEMA)
    for r in projection.rels:
        assert (r.start_label, r.end_label) in graph.REL_SCHEMA[r.type]
    iid, ev = scenario["incident_id"], scenario["evidence_id"]
    assert any(r.start_id == iid and r.end_id == ev for r in rels["HAS_EVIDENCE"])
    assert any(r.start_id == iid and r.end_id == scenario["site_id"] for r in rels["AT_SITE"])
    assert any(r.start_id == iid and r.end_id == f"{iid}:location" for r in rels["AT_LOCATION"])
    assert any(r.start_id == scenario["assigned"] and r.end_id == ev for r in rels["VERIFIED_WITH"])
    assert any(r.start_id == scenario["document_id"] for r in rels["FOR_PROJECT"])
    scoped = graph.person_id(org_id, scenario["scoped_user_id"])
    assert any(
        r.start_id == scoped and r.end_label == "Project" and r.props["role"] == "PROJECT_MANAGER"
        for r in rels["MEMBER_OF"]
    )
    cited = {(r.start_label, r.end_label) for r in rels["CITES"]}
    assert {("Investigation", "Evidence"), ("Investigation", "Document"), ("Action", "Evidence")} <= cited
    decisions = {r.start_id: r.props["decision"] for r in rels["REVIEWED_BY"]}
    assert decisions[scenario["assigned"]] == "MODIFY" and decisions[scenario["rejected"]] == "REJECT"
    actions = {n.id: n.props for n in projection.nodes if n.label == "Action"}
    assert actions[scenario["assigned"]]["review_status"] == "HUMAN_MODIFIED"
    assert actions[scenario["rejected"]]["review_status"] == "HUMAN_REJECTED"
    location = next(n for n in projection.nodes if n.id == f"{iid}:location")
    assert location.props["name"] == "Level 4 east edge, bay 7" and location.props["source_field"] == "location"


def _resolve(row, path: str):
    """Value at a column or JSON path such as `output.findings[2].source_ref`."""
    value = row
    for part in path.split("."):
        name, *indexes = re.findall(r"[^\[\]]+", part)
        value = value[name] if isinstance(value, dict) else getattr(value, name)
        for index in indexes:
            value = value[int(index)]
    return value


def _relational_id(node: graph.Node) -> str:
    """The primary key a node stands for (People and Locations carry it as source_id)."""
    return node.props["source_id"] if node.label in ("Person", "Location") else node.id


def test_graph_relationships_trace_back_to_relational_records(db, org_id, scenario):
    """The Prompt 28 gate: every node and relationship points at the PostgreSQL row (and field) it came from."""
    projection = graph.build_projection(db, org_id)
    nodes = {(n.label, n.id): n for n in projection.nodes}
    incident_ids = set(db.scalars(select(Incident.id).where(Incident.organization_id == org_id)))

    def row_of(item) -> object:
        row = db.get(MODELS[item.props["source_table"]], item.props["source_id"])
        assert row is not None, item.props
        return row

    def assert_ai(props: dict) -> None:
        assert props["review_status"] in REVIEW_VALUES
        run = db.get(AgentRun, props["agent_run_id"])
        assert run is not None and run.incident_id in incident_ids

    for n in projection.nodes:
        row = row_of(n)
        assert n.props["organization_id"] == org_id
        if n.props.get("ai_derived"):
            assert_ai(n.props)
        else:
            assert "agent_run_id" not in n.props
        field = n.props.get("source_field")
        if n.label == "Person":
            assert n.id == graph.person_id(org_id, row.id) and n.props["name"] == row.full_name
        elif n.label == "Hazard":
            assert n.props["name"] == _resolve(row, field).strip()
        elif n.label == "Cause":
            assert n.props["name"] == _resolve(row, field)["statement"].strip()
        elif n.label == "Requirement":
            finding = _resolve(row, field)
            assert n.props["name"] == finding["requirement"] and n.props["status"] == finding["status"]
        elif n.label == "Location":
            assert n.props["name"] == _resolve(row, field).strip()
        elif n.label == "Action":
            assert n.props["review_status"] == graph.REVIEW_STATUS[row.approval_status]
            assert n.props["ai_derived"] == row.ai_generated
            if row.ai_generated:
                assert n.props["agent_run_id"] == row.source_run_id
        if n.label not in ("Organization", "Person", "Project", "Site", "Document"):
            assert n.props["incident_id"] in incident_ids

    for r in projection.rels:
        start, end = nodes[(r.start_label, r.start_id)], nodes[(r.end_label, r.end_id)]
        ends = {_relational_id(start), _relational_id(end)}
        row = row_of(r)
        assert r.props["organization_id"] == org_id
        if r.props.get("ai_derived"):
            assert_ai(r.props)
        field = r.props.get("source_field")
        if r.type == "CITES":
            refs = _resolve(row, field)
            assert r.props["ref"] in refs
            kind, _, rid = r.props["ref"].partition(":")
            if kind == "chunk":
                assert db.get(DocumentChunk, rid).document_id == end.id
            else:
                assert rid == end.id
        elif r.type == "FROM_DOCUMENT":
            assert _resolve(row, field) == f"chunk:{r.props['chunk_id']}"
            assert db.get(DocumentChunk, r.props["chunk_id"]).document_id == end.id
        elif r.type in ("IDENTIFIED_HAZARD", "IDENTIFIED_CAUSE", "HAS_REQUIREMENT"):
            assert end.props["source_field"] == field and end.props["agent_run_id"] == row.id
        elif r.type == "ADDRESSES":
            assert graph._key(_resolve(row, field)) == end.props["key"]
            assert end.props["workflow_id"] == db.get(AgentRun, row.source_run_id).workflow_id
        elif r.type == "AT_LOCATION":
            assert end.props["source_id"] == row.id == start.id
        elif r.type == "MEMBER_OF":
            assert start.props["source_id"] == row.user_id and end.id == (row.project_id or row.organization_id)
        elif r.type in ("REVIEWED_BY", "VERIFIED_BY"):
            assert start.id == row.capa_id
            assert end.props["source_id"] == (row.reviewer_id if r.type == "REVIEWED_BY" else row.verifier_id)
        elif r.type == "VERIFIED_WITH":
            assert start.id == row.capa_id and end.id == _resolve(row, field) == row.evidence_id
        else:  # a foreign-key column of the source row links the two records
            assert field and _resolve(row, field) in ends, (r.type, field)
            assert row.id in ends


def test_records_deleted_in_postgres_disappear_on_next_sync(client, db, org_id, project_id, scenario):
    inc = _new_incident(client, project_id, title="Unsecured ladder at stair core")
    r = client.post(
        f"/incidents/{inc['id']}/evidence", headers=auth(client, "site"), files={"file": ("l.png", PNG, "image/png")}
    )
    evidence_id = r.json()["data"]["id"]
    run_id = client.post(f"/incidents/{inc['id']}/triage", headers=auth(client, "safety")).json()["data"]["id"]
    member = _user(db, "graph-temp@demo.siteguard.local", [(org_id, None, Role.VIEWER)])
    store = graph.InMemoryGraphStore()
    graph.sync(db, store, org_id)
    nodes, rels = store.snapshot(org_id)
    hazards = {k for k, p in nodes.items() if k[0] == "Hazard" and p["agent_run_id"] == run_id}
    assert ("Evidence", evidence_id) in nodes and ("Investigation", run_id) in nodes and hazards
    assert ("Person", graph.person_id(org_id, member.id)) in nodes

    db.delete(db.get(Evidence, evidence_id))
    db.delete(db.get(AgentRun, run_id))
    for m in db.scalars(select(Membership).where(Membership.user_id == member.id)):
        db.delete(m)
    db.delete(db.get(User, member.id))
    db.commit()
    result = graph.sync(db, store, org_id)
    nodes, rels = store.snapshot(org_id)
    gone = {("Evidence", evidence_id), ("Investigation", run_id), ("Person", graph.person_id(org_id, member.id))}
    assert not (gone | hazards) & set(nodes)
    dangling = [r for r in rels.values() if {r.start_id, r.end_id} & {k[1] for k in gone | hazards}]
    assert dangling == []
    assert result.nodes_deleted == len(gone | hazards) and result.relationships_deleted >= 2 + len(hazards)
    assert graph.sync(db, store, org_id).nodes_deleted == 0  # and the next run is a no-op again


def test_tenant_isolation_in_the_store(db, org_id, scenario):
    other_org = db.scalar(select(Organization.id).where(Organization.name == "Other Builders Ltd"))
    both = _user(db, "graph-both@demo.siteguard.local", [(org_id, None, Role.VIEWER), (other_org, None, Role.VIEWER)])
    store = graph.InMemoryGraphStore()
    graph.sync(db, store, org_id)
    graph.sync(db, store, other_org)
    demo_nodes, demo_rels = store.snapshot(org_id)
    other_nodes, other_rels = store.snapshot(other_org)
    assert all(p["organization_id"] == org_id for p in demo_nodes.values())
    assert all(r.props["organization_id"] == org_id for r in demo_rels.values())
    # A person who works for both organizations is a separate node in each.
    assert ("Person", graph.person_id(org_id, both.id)) in demo_nodes
    assert ("Person", graph.person_id(other_org, both.id)) in other_nodes
    # Rebuilding or purging one organization never touches the other.
    graph.sync(db, store, other_org)
    store.sync_organization(graph.Projection(other_org))
    assert store.snapshot(other_org) == ({}, {}) and store.snapshot(org_id) == (demo_nodes, demo_rels)
    sub = store.incident_subgraph(org_id, scenario["incident_id"], {r for r in db.scalars(select(Project.id))})
    assert sub.nodes and all(n.props["organization_id"] == org_id for n in sub.nodes)

    # The store refuses a projection that would take over another organization's node, and changes nothing.
    stolen = graph.Node(
        "Incident", scenario["incident_id"], {"id": scenario["incident_id"], "organization_id": other_org}
    )
    with pytest.raises(ValueError):
        store.sync_organization(graph.Projection(other_org, [stolen]))
    assert store.snapshot(org_id) == (demo_nodes, demo_rels)


def test_projection_boundary_checks():
    org = "org-1"
    good = graph.Node("Hazard", "h1", {"id": "h1", "organization_id": org})
    bad_label = graph.Node("Hazard) DETACH DELETE n //", "x", {"id": "x", "organization_id": org})
    foreign = graph.Node("Hazard", "h2", {"id": "h2", "organization_id": "org-2"})
    dangling = graph.Rel("CITES", "c1", "Hazard", "h1", "Evidence", "e1", {"id": "c1", "organization_id": org})
    wrong_pair = graph.Rel("CITES", "c2", "Hazard", "h1", "Hazard", "h1", {"id": "c2", "organization_id": org})
    for projection in (
        graph.Projection(org, [bad_label]),
        graph.Projection(org, [foreign]),
        graph.Projection(org, [good], [dangling]),
        graph.Projection(org, [good], [wrong_pair]),
    ):
        with pytest.raises(ValueError):
            graph.validate_projection(projection)
    with pytest.raises(TypeError):
        graph.clean({"nested": {"a": 1}})  # Neo4j properties are primitives or lists of primitives


def test_incident_graph_endpoint(client, org_id, project_id, scenario, memory_store):
    iid = scenario["incident_id"]
    site = auth(client, "site")
    r = client.get(f"/incidents/{iid}/graph", headers=site)
    assert r.status_code == 200 and r.json()["data"]["synced"] is False and r.json()["data"]["nodes"] == []

    r = client.post("/graph/sync", params={"organization_id": org_id}, headers=auth(client, "admin"))
    assert r.status_code == 200, r.text
    result = r.json()["data"]
    assert result["backend"] == "memory" and result["nodes_created"] == result["nodes"] > 0
    audit = client.get("/audit", params={"entity_id": org_id}, headers=auth(client, "auditor")).json()["data"]
    assert any(e["action"] == "graph.sync" and e["details"]["nodes"] == result["nodes"] for e in audit)

    data = client.get(f"/incidents/{iid}/graph", headers=site).json()["data"]
    assert data["synced"] is True and data["incident_id"] == iid and "not legal" in data["note"]
    labels = {n["label"] for n in data["nodes"]}
    assert {"Incident", "Project", "Site", "Location", "Person", "Evidence", "Investigation", "Hazard"} <= labels
    assert {"RCA", "Cause", "Requirement", "Document", "Action"} <= labels
    ids = {n["id"] for n in data["nodes"]}
    for n in data["nodes"]:
        prov = n["provenance"]
        assert prov["organization_id"] == org_id and prov["source_table"] in MODELS and prov["source_id"]
        assert prov["project_id"] in (None, project_id)
    for e in data["edges"]:
        assert e["source"] in ids and e["target"] in ids and e["provenance"]["source_id"]
    hazard = next(n for n in data["nodes"] if n["label"] == "Hazard")
    assert hazard["provenance"]["ai_derived"] is True and hazard["provenance"]["review_status"] == "UNREVIEWED"
    assert hazard["provenance"]["agent_run_id"] == hazard["provenance"]["source_id"]

    facts = client.get(f"/incidents/{iid}/graph", params={"include_ai": "false"}, headers=site).json()["data"]
    assert facts["nodes"] and not any(n["provenance"]["ai_derived"] for n in facts["nodes"])
    assert not any(e["provenance"]["ai_derived"] for e in facts["edges"])
    assert {"Incident", "Evidence", "Person"} <= {n["label"] for n in facts["nodes"]}

    # Validation
    r = client.get(f"/incidents/{iid}/graph", params={"include_ai": "maybe"}, headers=site)
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_REQUEST"
    assert client.post("/graph/sync", headers=auth(client, "admin")).status_code == 400
    assert (
        client.post("/graph/sync", params={"organization_id": "x" * 37}, headers=auth(client, "admin")).status_code
        == 400
    )

    # Authorization and tenant isolation
    assert client.get(f"/incidents/{iid}/graph").status_code == 401
    assert client.get(f"/incidents/{iid}/graph", headers=auth(client, "other")).status_code == 404
    assert client.get("/incidents/does-not-exist/graph", headers=site).status_code == 404
    assert (
        client.post("/graph/sync", params={"organization_id": org_id}, headers=auth(client, "other")).status_code == 404
    )
    r = client.post("/graph/sync", params={"organization_id": org_id}, headers=auth(client, "hse"))
    assert r.status_code == 403  # HSE managers lack MANAGE_PROJECTS
    r = client.post("/graph/sync", params={"organization_id": org_id}, headers=auth(client, "graph-scoped"))
    assert r.status_code == 403  # a project-limited role cannot rebuild the whole organization


def test_endpoints_when_the_graph_is_disabled(client, org_id, scenario, monkeypatch):
    graph.close_store()
    monkeypatch.setattr(get_settings(), "graph_backend", "disabled")
    iid = scenario["incident_id"]
    r = client.get(f"/incidents/{iid}/graph", headers=auth(client, "site"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "GRAPH_DISABLED"
    r = client.post("/graph/sync", params={"organization_id": org_id}, headers=auth(client, "admin"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "GRAPH_DISABLED"
    # Authorization still comes first: an outsider learns nothing about the incident or the setting.
    assert client.get(f"/incidents/{iid}/graph", headers=auth(client, "other")).status_code == 404


def test_neighbourhood_is_limited_to_the_organization_and_visible_projects(db, org_id, project_id, scenario):
    """Defence in depth: even a bad projection or store answer cannot show another project's or tenant's records."""
    inc = db.get(Incident, scenario["incident_id"])
    projection = graph.build_projection(db, org_id)
    hidden = graph.Node("Document", "hidden-doc", {"id": "hidden-doc", "organization_id": org_id, "project_id": "p2"})
    link = graph.Rel(
        "CITES",
        "leak",
        "Investigation",
        next(n.id for n in projection.nodes if n.label == "Investigation" and n.props["incident_id"] == inc.id),
        "Document",
        "hidden-doc",
        {"id": "leak", "organization_id": org_id, "project_id": project_id},
    )
    store = graph.InMemoryGraphStore()
    store.sync_organization(graph.Projection(org_id, projection.nodes + [hidden], projection.rels + [link]))
    data = graph.incident_graph(store, inc, {project_id})
    assert "hidden-doc" not in {n["id"] for n in data["nodes"]} and "leak" not in {e["id"] for e in data["edges"]}

    class LeakyStore:
        backend = "fake"

        def incident_subgraph(self, organization_id, incident_id, project_ids):
            sub = store.incident_subgraph(organization_id, incident_id, project_ids)
            foreign = graph.Node(
                "Person", "x", {"id": "x", "organization_id": "another-org", "incident_id": incident_id}
            )
            return graph.Subgraph(sub.nodes + [foreign], sub.rels)

    data = graph.incident_graph(LeakyStore(), inc, {project_id})  # type: ignore[arg-type]
    assert data["nodes"] and {n["provenance"]["organization_id"] for n in data["nodes"]} == {org_id}


# --- Neo4j adapter with a fake driver -------------------------------------------------------------------------------


class FakeResult:
    def __init__(self, query: str, params: dict, rows: list[dict], written: int | None = None):
        n = len(params.get("rows", []))
        self._rows = rows
        self._written = n if written is None else written
        created = n if query.startswith("UNWIND") else 0
        self._counters = SimpleNamespace(
            nodes_created=created if "MERGE (n:" in query else 0,
            relationships_created=created if "MERGE (a)-[r:" in query else 0,
            nodes_deleted=0,
            relationships_deleted=0,
        )

    def single(self):
        return {"written": self._written}

    def consume(self):
        return SimpleNamespace(counters=self._counters)

    def data(self):
        return self._rows


class FakeDriver:
    """Records every Cypher statement and its parameters; returns canned rows for reads."""

    def __init__(self, rows: list[dict] | None = None, written: int | None = None, error: Exception | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.rows, self.written, self.error, self.closed = rows or [], written, error, False

    def session(self):
        return self

    def __enter__(self):
        if self.error:
            raise self.error
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query: str, parameters: dict | None = None):
        self.calls.append((query, parameters or {}))
        return FakeResult(query, parameters or {}, self.rows, self.written)

    def execute_write(self, fn):
        return fn(self)

    def execute_read(self, fn):
        return fn(self)

    def close(self):
        self.closed = True


def test_neo4j_adapter_sends_fixed_parameterized_cypher(db, org_id, scenario):
    projection = graph.build_projection(db, org_id)
    driver = FakeDriver()
    store = graph.Neo4jGraphStore(driver)
    result = store.sync_organization(projection)
    assert result.nodes_created == len(projection.nodes) and result.relationships_created == len(projection.rels)

    fixed = set(graph._CONSTRAINTS + graph._INDEXES + (graph._DELETE_STALE_RELS,))
    fixed |= (
        set(graph._UPSERT_NODES.values()) | set(graph._UPSERT_RELS.values()) | set(graph._DELETE_STALE_NODES.values())
    )
    queries = [q for q, _ in driver.calls]
    assert set(queries) <= fixed  # every statement is fixed text from the schema allowlist
    record_values = {n.id for n in projection.nodes} | {str(n.props.get("name")) for n in projection.nodes}
    assert not any(v in q for q in queries for v in record_values if len(v) > 3)  # no data in query text
    for label in graph.NODE_LABELS:
        assert (
            f"CREATE CONSTRAINT sg_{label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE" in queries
        )
        assert f"MERGE (n:{label} {{id: row.id}})" in graph._UPSERT_NODES[label]
    assert all("MERGE (a)-[r:" in q and "{id: row.id}" in q for q in graph._UPSERT_RELS.values())

    written = {}
    for q, params in driver.calls:
        if q.startswith("UNWIND"):
            assert params["organization_id"] == org_id
            for row in params["rows"]:
                written[row["id"]] = row["props"]
        elif "DELETE" in q:
            assert params["organization_id"] == org_id and isinstance(params["keep"], list)
    assert written == {n.id: n.props for n in projection.nodes} | {r.id: r.props for r in projection.rels}

    # A second sync sends the same statements: the schema is created once, everything else is MERGE.
    driver.calls.clear()
    store.sync_organization(projection)
    assert not any(q.startswith("CREATE") for q, _ in driver.calls)

    # A node id owned by another organization is not overwritten: the transaction is refused.
    with pytest.raises(ValueError):
        graph.Neo4jGraphStore(FakeDriver(written=0)).sync_organization(projection)
    # A label outside the allowlist never reaches the driver.
    rogue = FakeDriver()
    with pytest.raises(ValueError):
        graph.Neo4jGraphStore(rogue).sync_organization(
            graph.Projection(
                org_id, [graph.Node("X`) DETACH DELETE n //", "1", {"id": "1", "organization_id": org_id})]
            )
        )
    assert rogue.calls == []


def test_neo4j_adapter_reads_and_maps_driver_errors(org_id):
    from neo4j.exceptions import ServiceUnavailable

    inc = {"id": "i1", "organization_id": org_id, "project_id": "p1", "incident_id": "i1", "name": "Fall"}
    person = {"id": "pe1", "organization_id": org_id, "name": "Sid"}
    rel = {"id": "REPORTED_BY:i1->pe1", "organization_id": org_id, "project_id": "p1", "source_table": "incidents"}
    rows = [
        {
            "n_props": inc,
            "n_labels": ["SgEntity", "Incident"],
            "r_type": "REPORTED_BY",
            "r_props": rel,
            "r_start": "i1",
            "r_end": "pe1",
            "m_props": person,
            "m_labels": ["Person", "SgEntity"],
        }
    ]
    driver = FakeDriver(rows=rows)
    sub = graph.Neo4jGraphStore(driver).incident_subgraph(org_id, "i1", {"p1"})
    assert [(n.label, n.id) for n in sub.nodes] == [("Incident", "i1"), ("Person", "pe1")]
    assert [(r.type, r.start_label, r.end_label) for r in sub.rels] == [("REPORTED_BY", "Incident", "Person")]
    query, params = driver.calls[-1]
    assert query == graph._INCIDENT_SUBGRAPH
    assert params == {"organization_id": org_id, "incident_id": "i1", "project_ids": ["p1"]}

    down = graph.Neo4jGraphStore(FakeDriver(error=ServiceUnavailable("connection refused")))
    with pytest.raises(graph.GraphUnavailable) as err:
        down.incident_subgraph(org_id, "i1", {"p1"})
    assert err.value.status_code == 503 and err.value.code == "GRAPH_UNAVAILABLE"

    from app.core.config import Settings

    malformed = Settings(_env_file=None, graph_backend="neo4j", neo4j_uri="bolt://[bad", neo4j_password="p" * 12)
    with pytest.raises(graph.GraphUnavailable):
        graph.Neo4jGraphStore.connect(malformed)


# --- Job and settings -----------------------------------------------------------------------------------------------


def test_graph_sync_job(db, org_id, scenario, memory_store):
    from app import jobs

    gone = graph.Projection(
        "deleted-org",
        [graph.Node("Organization", "deleted-org", {"id": "deleted-org", "organization_id": "deleted-org"})],
    )
    memory_store.sync_organization(gone)
    out = jobs.graph_sync()["graph"]
    assert out[org_id]["nodes"] > 0 and out[org_id]["nodes_created"] == out[org_id]["nodes"]
    assert out["deleted-org"]["nodes_deleted"] == 1 and "deleted-org" not in memory_store.organization_ids()
    assert jobs.graph_sync()["graph"][org_id]["nodes_created"] == 0


def test_graph_sync_job_refuses_when_disabled(monkeypatch):
    from app import jobs

    graph.close_store()
    monkeypatch.setattr(get_settings(), "graph_backend", "disabled")
    with pytest.raises(graph.GraphDisabled):
        jobs.graph_sync()
    with pytest.raises(SystemExit) as exc:
        jobs.main(["graph-sync"])
    assert "disabled" in str(exc.value.code)


def test_neo4j_settings_refused_when_unsafe():
    from app.core.config import Settings
    from app.main import validate_settings

    def settings(**kw) -> Settings:
        return Settings(_env_file=None, graph_backend="neo4j", **kw)

    with pytest.raises(RuntimeError):
        validate_settings(settings(neo4j_uri="http://neo4j:7474", neo4j_password="local-pass"))
    with pytest.raises(RuntimeError):
        validate_settings(settings(neo4j_uri="bolt://neo4j:7687"))  # no password
    deployed = {
        "env": "production",
        "jwt_secret": secrets.token_urlsafe(48),
        "database_url": "postgresql+psycopg://siteguard:pw@db.internal:5432/siteguard",
        "cors_origins": "https://siteguard.example",
        "public_web_url": "https://siteguard.example",
        "neo4j_password": "p" * 12,
    }
    with pytest.raises(RuntimeError, match="verified TLS"):
        validate_settings(settings(neo4j_uri="bolt://neo4j:7687", **deployed))
    validate_settings(settings(neo4j_uri="bolt://neo4j:7687", neo4j_password="local-pass"))
    validate_settings(settings(neo4j_uri="neo4j+s://graph.example", **deployed))
    assert "p" * 12 not in repr(settings(neo4j_password="p" * 12))  # SecretStr never prints the password


# --- Real Neo4j (CI `neo4j` job) ------------------------------------------------------------------------------------

NEO4J_URI = os.environ.get("SITEGUARD_TEST_NEO4J_URI")


@pytest.mark.skipif(not NEO4J_URI, reason="set SITEGUARD_TEST_NEO4J_URI to run the Neo4j integration test")
def test_neo4j_integration(db, org_id, scenario):
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        NEO4J_URI or "",
        auth=(
            os.environ.get("SITEGUARD_TEST_NEO4J_USER", "neo4j"),
            os.environ.get("SITEGUARD_TEST_NEO4J_PASSWORD", ""),
        ),
    )
    for attempt in range(30):  # a freshly started server can accept connections before Bolt auth is ready
        try:
            driver.verify_connectivity()
            break
        except Exception:
            if attempt == 29:
                raise
            time.sleep(2)
    store = graph.Neo4jGraphStore(driver)
    other_org = db.scalar(select(Organization.id).where(Organization.name == "Other Builders Ltd"))
    try:
        for org in (org_id, other_org):
            store.sync_organization(graph.Projection(org))  # start from an empty graph for both tenants
        projection = graph.build_projection(db, org_id)
        first = store.sync_organization(projection)
        assert (first.nodes_created, first.relationships_created) == (len(projection.nodes), len(projection.rels))
        again = store.sync_organization(projection)
        assert (
            again.nodes_created
            == again.nodes_deleted
            == again.relationships_created
            == again.relationships_deleted
            == 0
        )

        def dump(org: str) -> tuple[dict, dict]:
            nodes = driver.execute_query(
                "MATCH (n:SgEntity {organization_id: $org}) RETURN labels(n) AS labels, properties(n) AS props", org=org
            ).records
            rels = driver.execute_query(
                "MATCH (a:SgEntity {organization_id: $org})-[r]->(b) RETURN type(r) AS type, a.id AS a, b.id AS b, "
                "properties(r) AS props",
                org=org,
            ).records
            return (
                {(graph._label_of(r["labels"]), r["props"]["id"]): r["props"] for r in nodes},
                {r["props"]["id"]: (r["type"], r["a"], r["b"], r["props"]) for r in rels},
            )

        nodes, rels = dump(org_id)
        assert nodes == {(n.label, n.id): n.props for n in projection.nodes}  # values round-trip exactly
        assert rels == {r.id: (r.type, r.start_id, r.end_id, r.props) for r in projection.rels}

        # Same neighbourhood as the in-memory store for the same projection.
        memory = graph.InMemoryGraphStore()
        memory.sync_organization(projection)
        inc = db.get(Incident, scenario["incident_id"])
        visible = {inc.project_id}
        assert graph.incident_graph(store, inc, visible) | {"backend": "x"} == graph.incident_graph(
            memory, inc, visible
        ) | {"backend": "x"}

        # Records missing from the next projection disappear with their relationships.
        dropped = next(n for n in projection.nodes if n.label == "Hazard")
        smaller = graph.Projection(
            org_id,
            [n for n in projection.nodes if n is not dropped],
            [r for r in projection.rels if dropped.id not in (r.start_id, r.end_id)],
        )
        result = store.sync_organization(smaller)
        assert result.nodes_deleted == 1 and result.relationships_deleted >= 1
        assert ("Hazard", dropped.id) not in dump(org_id)[0]

        # Tenants stay apart: syncing and purging the other organization leaves this one untouched.
        before = dump(org_id)
        store.sync_organization(graph.build_projection(db, other_org))
        other_nodes = dump(other_org)[0]
        assert other_nodes and not set(other_nodes) & set(before[0])
        store.sync_organization(graph.Projection(other_org))
        assert dump(other_org) == ({}, {}) and dump(org_id) == before
        assert other_org not in store.organization_ids() and org_id in store.organization_ids()
    finally:
        for org in (org_id, other_org):
            store.sync_organization(graph.Projection(org))
        store.close()
