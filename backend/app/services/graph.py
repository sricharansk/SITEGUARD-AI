"""Construction knowledge graph (Playbook Prompt 28): a derived projection of PostgreSQL.

PostgreSQL stays the system of record (DECISIONS 002). `build_projection` reads one organization's records and turns
them into nodes and relationships; a `GraphStore` (in memory, or Neo4j) receives the whole projection and makes that
organization's part of the graph equal to it. Re-running a sync therefore changes nothing, and records deleted in
PostgreSQL disappear from the graph on the next sync of their organization.

Every node and relationship carries `organization_id`, `project_id` (null for organization-level entities) and its
provenance: `source_table` and `source_id` (the row it came from), `source_field` (the column or JSON path, when it
came from one field), `ai_derived`, `agent_run_id` (the `agent_runs` row, for anything taken from AI output) and
`review_status` (`UNREVIEWED` for AI output nobody has reviewed, `HUMAN_APPROVED` / `HUMAN_MODIFIED` /
`HUMAN_REJECTED` / `SUPERSEDED` for CAPA actions). Nothing is generated at sync time: no model is called and every
value is copied from a stored record. docs/ARCHITECTURE.md#knowledge-graph lists every node and relationship.

Cypher sent to Neo4j is fixed text built at import time from the allowlisted labels and relationship types below;
record data only ever travels as query parameters.
"""

from __future__ import annotations

import enum
import logging
import threading
from collections.abc import Callable, Collection, Iterable
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models import (
    AgentRun,
    ApprovalEvent,
    ApprovalStatus,
    CapaAction,
    Document,
    DocumentChunk,
    Evidence,
    Incident,
    Membership,
    Organization,
    Project,
    Site,
    User,
    VerificationRecord,
)

log = logging.getLogger("siteguard.graph")

# --- Schema ---------------------------------------------------------------------------------------------------------

NODE_LABELS: tuple[str, ...] = (
    "Organization",
    "Project",
    "Site",
    "Location",
    "Person",
    "Incident",
    "Evidence",
    "Document",
    "Investigation",
    "Hazard",
    "RCA",
    "Cause",
    "Requirement",
    "Action",
)

# Relationship type -> allowed (start label, end label) pairs.
REL_SCHEMA: dict[str, tuple[tuple[str, str], ...]] = {
    "BELONGS_TO": (("Project", "Organization"), ("Document", "Organization")),
    "PART_OF": (("Site", "Project"),),
    "FOR_PROJECT": (("Document", "Project"),),
    "MEMBER_OF": (("Person", "Organization"), ("Person", "Project")),
    "IN_PROJECT": (("Incident", "Project"),),
    "AT_SITE": (("Incident", "Site"),),
    "AT_LOCATION": (("Incident", "Location"),),
    "REPORTED_BY": (("Incident", "Person"),),
    "HAS_EVIDENCE": (("Incident", "Evidence"),),
    "UPLOADED_BY": (("Evidence", "Person"),),
    "HAS_INVESTIGATION": (("Incident", "Investigation"),),
    "IDENTIFIED_HAZARD": (("Investigation", "Hazard"),),
    "HAS_RCA": (("Incident", "RCA"),),
    "IDENTIFIED_CAUSE": (("RCA", "Cause"),),
    "HAS_REQUIREMENT": (("Incident", "Requirement"),),
    "FROM_DOCUMENT": (("Requirement", "Document"),),
    "HAS_ACTION": (("Incident", "Action"),),
    "ADDRESSES": (("Action", "Hazard"), ("Action", "Cause")),
    "ASSIGNED_TO": (("Action", "Person"),),
    "REVIEWED_BY": (("Action", "Person"),),
    "VERIFIED_BY": (("Action", "Person"),),
    "VERIFIED_WITH": (("Action", "Evidence"),),
    "CITES": (
        ("Investigation", "Evidence"),
        ("Investigation", "Document"),
        ("RCA", "Evidence"),
        ("RCA", "Document"),
        ("Action", "Evidence"),
        ("Action", "Document"),
    ),
}

PROVENANCE_KEYS = (
    "organization_id",
    "project_id",
    "source_table",
    "source_id",
    "source_field",
    "ai_derived",
    "agent_run_id",
    "review_status",
)
UNREVIEWED = "UNREVIEWED"
REVIEW_STATUS = {
    ApprovalStatus.DRAFT: UNREVIEWED,
    ApprovalStatus.PENDING_REVIEW: UNREVIEWED,
    ApprovalStatus.APPROVED: "HUMAN_APPROVED",
    ApprovalStatus.MODIFIED: "HUMAN_MODIFIED",
    ApprovalStatus.REJECTED: "HUMAN_REJECTED",
    ApprovalStatus.SUPERSEDED: "SUPERSEDED",
}
INVESTIGATION_AGENTS = {"triage": "Triage", "safety": "Safety investigation", "quality": "Quality investigation"}
# Output fields that become their own nodes or relationships, and names the run's node sets itself: an output field
# is never copied over scope, provenance or run metadata.
_OUTPUT_AS_GRAPH = {"evidence_refs", "hazards", "root_causes", "findings", "disclaimer"}
_RESERVED = {"id", "name", "incident_id", "agent", "provider", "status", "workflow_id", "needs_human_review"}
_RESERVED |= {"started_at", "finished_at", *PROVENANCE_KEYS}
NOTE = (
    "Derived from Site Guard AI records at the last graph sync; PostgreSQL is the system of record. Items with "
    "ai_derived=true are model suggestions (review_status says whether a person reviewed them). Requirement statuses "
    "are possible gaps that need review by a competent person, not legal or regulatory compliance determinations."
)


class GraphDisabled(AppError):
    status_code = 409
    code = "GRAPH_DISABLED"

    def __init__(self) -> None:
        super().__init__("The knowledge graph is disabled on this server (SITEGUARD_GRAPH_BACKEND=disabled)")


class GraphUnavailable(AppError):
    status_code = 503
    code = "GRAPH_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("The knowledge graph store is unavailable; try again later")


# --- Projection -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    label: str
    id: str
    props: dict[str, Any]  # flat, Neo4j-compatible values; includes `id`, scope and provenance


@dataclass(frozen=True)
class Rel:
    type: str
    id: str
    start_label: str
    start_id: str
    end_label: str
    end_id: str
    props: dict[str, Any]


@dataclass
class Projection:
    organization_id: str
    nodes: list[Node] = field(default_factory=list)
    rels: list[Rel] = field(default_factory=list)


@dataclass
class Subgraph:
    nodes: list[Node] = field(default_factory=list)
    rels: list[Rel] = field(default_factory=list)


@dataclass
class SyncResult:
    organization_id: str
    backend: str
    nodes: int = 0
    relationships: int = 0
    nodes_created: int = 0
    nodes_deleted: int = 0
    relationships_created: int = 0
    relationships_deleted: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Source:
    """Where a node or relationship came from: one PostgreSQL row, optionally one field of it."""

    table: str
    id: str
    field: str | None = None
    ai_derived: bool = False
    agent_run_id: str | None = None
    review_status: str | None = None

    def at(self, field_name: str) -> Source:
        return replace(self, field=field_name)

    def props(self) -> dict[str, Any]:
        return {
            "source_table": self.table,
            "source_id": self.id,
            "source_field": self.field,
            "ai_derived": self.ai_derived,
            "agent_run_id": self.agent_run_id,
            "review_status": self.review_status,
        }


def _ai_source(run: AgentRun, field_name: str) -> Source:
    return Source("agent_runs", run.id, field_name, True, run.id, UNREVIEWED)


def _value(v: Any) -> Any:
    if isinstance(v, enum.Enum):
        return v.value
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, str | bool | int | float):
        return v
    raise TypeError(f"Graph property values must be primitives, got {type(v).__name__}")


def clean(props: dict[str, Any]) -> dict[str, Any]:
    """Neo4j-compatible copy: nulls dropped (Neo4j does not store them), lists of primitives kept."""
    out: dict[str, Any] = {}
    for key, v in props.items():
        if v is None:
            continue
        out[key] = [_value(i) for i in v if i is not None] if isinstance(v, list | tuple) else _value(v)
    return out


def _key(text: str) -> str:
    return " ".join(text.lower().split())


def person_id(organization_id: str, user_id: str) -> str:
    """People are scoped per organization: a user who works for two organizations is two separate nodes."""
    return f"{organization_id}:{user_id}"


NodeKey = tuple[str, str]  # (label, id)


class _Builder:
    def __init__(self, organization_id: str):
        self.org = organization_id
        self.nodes: dict[NodeKey, Node] = {}
        self.rels: dict[str, Rel] = {}

    def node(
        self,
        label: str,
        node_id: str,
        src: Source,
        *,
        project_id: str | None = None,
        incident_id: str | None = None,
        **props: Any,
    ) -> NodeKey:
        key = (label, node_id)
        if key not in self.nodes:
            scope = {"id": node_id, "incident_id": incident_id, "organization_id": self.org, "project_id": project_id}
            self.nodes[key] = Node(label, node_id, clean({**props, **scope, **src.props()}))
        return key

    def rel(
        self,
        rel_type: str,
        start: NodeKey,
        end: NodeKey | None,
        src: Source,
        *,
        project_id: str | None = None,
        discriminator: str | None = None,
        **props: Any,
    ) -> None:
        if end is None or start not in self.nodes or end not in self.nodes:
            return  # never a dangling relationship: both ends must be records of this organization
        rel_id = f"{rel_type}:{start[1]}->{end[1]}" + (f"#{discriminator}" if discriminator else "")
        if rel_id not in self.rels:
            scope = {"id": rel_id, "organization_id": self.org, "project_id": project_id}
            props = clean({**props, **scope, **src.props()})
            self.rels[rel_id] = Rel(rel_type, rel_id, start[0], start[1], end[0], end[1], props)

    def projection(self) -> Projection:
        return Projection(
            self.org,
            sorted(self.nodes.values(), key=lambda n: (n.label, n.id)),
            sorted(self.rels.values(), key=lambda r: r.id),
        )


def _output_props(output: dict | None) -> dict[str, Any]:
    """Scalar and list-of-scalar fields of a validated agent output, copied as recorded."""
    props: dict[str, Any] = {}
    for name, v in (output or {}).items():
        if name in _OUTPUT_AS_GRAPH or name in _RESERVED:
            continue
        if isinstance(v, str | bool | int | float) or (
            isinstance(v, list) and all(isinstance(i, str | bool | int | float) for i in v)
        ):
            props[name] = v
    return props


def build_projection(db: Session, organization_id: str) -> Projection:
    """Read one organization's records and return the graph they imply. Reads only; never writes."""
    b = _Builder(organization_id)
    org = db.get(Organization, organization_id)
    if org is None:
        return b.projection()  # an empty projection removes whatever the graph still holds for this organization
    org_key = b.node("Organization", org.id, Source("organizations", org.id), name=org.name)

    projects = list(db.scalars(select(Project).where(Project.organization_id == org.id).order_by(Project.id)))
    for p in projects:
        src = Source("projects", p.id)
        key = b.node(
            "Project", p.id, src, project_id=p.id, name=p.name, code=p.code, client=p.client, location=p.location
        )
        b.rel("BELONGS_TO", key, org_key, src.at("organization_id"), project_id=p.id)
    for s in db.scalars(select(Site).where(Site.project_id.in_([p.id for p in projects])).order_by(Site.id)):
        src = Source("sites", s.id)
        key = b.node("Site", s.id, src, project_id=s.project_id, name=s.name)
        b.rel("PART_OF", key, ("Project", s.project_id), src.at("project_id"), project_id=s.project_id)

    incidents = {i.id: i for i in db.scalars(select(Incident).where(Incident.organization_id == org.id))}
    inc_ids = sorted(incidents)
    evidence = list(db.scalars(select(Evidence).where(Evidence.incident_id.in_(inc_ids)).order_by(Evidence.id)))
    documents = list(db.scalars(select(Document).where(Document.organization_id == org.id).order_by(Document.id)))
    memberships = list(
        db.scalars(select(Membership).where(Membership.organization_id == org.id).order_by(Membership.id))
    )
    runs = list(
        db.scalars(select(AgentRun).where(AgentRun.incident_id.in_(inc_ids)).order_by(AgentRun.started_at, AgentRun.id))
    )
    actions = list(db.scalars(select(CapaAction).where(CapaAction.incident_id.in_(inc_ids)).order_by(CapaAction.id)))
    action_ids = [a.id for a in actions]
    approvals = list(
        db.scalars(select(ApprovalEvent).where(ApprovalEvent.capa_id.in_(action_ids)).order_by(ApprovalEvent.id))
    )
    verifications = list(
        db.scalars(
            select(VerificationRecord).where(VerificationRecord.capa_id.in_(action_ids)).order_by(VerificationRecord.id)
        )
    )

    # People: members of the organization and anyone its records name.
    user_ids = {m.user_id for m in memberships} | {i.reporter_id for i in incidents.values()}
    user_ids |= {e.uploaded_by for e in evidence} | {a.assignee_id for a in actions if a.assignee_id}
    user_ids |= {a.reviewer_id for a in approvals} | {v.verifier_id for v in verifications}
    for u in db.scalars(select(User).where(User.id.in_(sorted(user_ids))).order_by(User.id)):
        b.node("Person", person_id(org.id, u.id), Source("users", u.id), name=u.full_name, active=u.is_active)

    def person(user_id: str | None) -> NodeKey | None:
        return ("Person", person_id(org.id, user_id)) if user_id else None

    for m in memberships:
        b.rel(
            "MEMBER_OF",
            ("Person", person_id(org.id, m.user_id)),
            ("Project", m.project_id) if m.project_id else org_key,
            Source("memberships", m.id),
            project_id=m.project_id,
            discriminator=m.id,
            role=m.role,
            scope="project" if m.project_id else "organization",
        )

    for d in documents:
        src = Source("documents", d.id)
        key = b.node(
            "Document",
            d.id,
            src,
            project_id=d.project_id,
            name=d.title,
            doc_type=d.doc_type,
            version=d.version,
            status=d.status,
            domain=d.domain,
            effective_date=d.effective_date,
            sha256=d.sha256,
            tags=list(d.tags or []),
        )
        if d.project_id:
            b.rel("FOR_PROJECT", key, ("Project", d.project_id), src.at("project_id"), project_id=d.project_id)
        else:
            b.rel("BELONGS_TO", key, org_key, src.at("organization_id"))

    for i in sorted(incidents.values(), key=lambda i: i.id):
        src = Source("incidents", i.id)
        key = b.node(
            "Incident",
            i.id,
            src,
            project_id=i.project_id,
            incident_id=i.id,
            name=i.title,
            reference=i.reference,
            status=i.status,
            severity=i.severity,
            domain=i.domain,
            category=i.category,
            activity=i.activity,
            occurred_at=i.occurred_at,
            reported_at=i.reported_at,
            closed_at=i.closed_at,
            is_synthetic=i.is_synthetic,
        )
        b.rel("IN_PROJECT", key, ("Project", i.project_id), src.at("project_id"), project_id=i.project_id)
        if i.site_id:
            b.rel("AT_SITE", key, ("Site", i.site_id), src.at("site_id"), project_id=i.project_id)
        b.rel("REPORTED_BY", key, person(i.reporter_id), src.at("reporter_id"), project_id=i.project_id)
        if i.location and i.location.strip():
            # No asset or location register exists: Location nodes come from the incident's free-text field.
            loc = b.node(
                "Location",
                f"{i.id}:location",
                src.at("location"),
                project_id=i.project_id,
                incident_id=i.id,
                name=i.location.strip(),
                key=_key(i.location),
                site_id=i.site_id,
            )
            b.rel("AT_LOCATION", key, loc, src.at("location"), project_id=i.project_id)

    for e in evidence:
        inc = incidents[e.incident_id]
        src = Source("evidence", e.id)
        key = b.node(
            "Evidence",
            e.id,
            src,
            project_id=inc.project_id,
            incident_id=inc.id,
            name=e.filename,
            content_type=e.content_type,
            size_bytes=e.size_bytes,
            sha256=e.sha256,
            created_at=e.created_at,
        )
        b.rel("HAS_EVIDENCE", ("Incident", inc.id), key, src.at("incident_id"), project_id=inc.project_id)
        b.rel("UPLOADED_BY", key, person(e.uploaded_by), src.at("uploaded_by"), project_id=inc.project_id)

    # chunk: refs cited by AI output resolve to their documents through document_chunks.
    chunk_ids = {ref.split(":", 1)[1] for ref in _all_refs(runs, actions) if ref.startswith("chunk:")}
    chunk_doc = _chunk_documents(db, chunk_ids)
    doc_scope = {d.id: d.project_id for d in documents}

    def cite_target(ref: str, inc: Incident) -> tuple[NodeKey, str | None] | None:
        """The node a ref points to, only if it is this incident's evidence or a document its project can see."""
        kind, _, rid = ref.partition(":")
        if kind == "evidence":
            node = b.nodes.get(("Evidence", rid))
            return (("Evidence", rid), None) if node and node.props.get("incident_id") == inc.id else None
        if kind == "chunk" and rid in chunk_doc:
            doc_id = chunk_doc[rid]
            if doc_id in doc_scope and doc_scope[doc_id] in (None, inc.project_id):
                return ("Document", doc_id), rid
        return None

    def cites(start: NodeKey, refs: Iterable[str], inc: Incident, src: Source) -> None:
        for ref in refs:
            target = cite_target(ref, inc)
            if target:
                node, chunk_id = target
                b.rel(
                    "CITES", start, node, src, project_id=inc.project_id, discriminator=ref, ref=ref, chunk_id=chunk_id
                )

    hazards: dict[tuple[str, str], list[NodeKey]] = {}  # (workflow, key) -> Hazard nodes, for ADDRESSES
    causes: dict[tuple[str, str], list[NodeKey]] = {}
    for run in runs:
        inc = incidents[run.incident_id]
        output = run.output if run.status == "SUCCEEDED" and isinstance(run.output, dict) else None
        scope: dict[str, Any] = {"project_id": inc.project_id, "incident_id": inc.id}
        if run.agent in INVESTIGATION_AGENTS or run.agent == "rca":
            label = "RCA" if run.agent == "rca" else "Investigation"
            key = b.node(
                label,
                run.id,
                _ai_source(run, "output"),
                **scope,
                name="Root cause analysis" if label == "RCA" else INVESTIGATION_AGENTS[run.agent],
                agent=run.agent,
                provider=run.provider,
                status=run.status,
                workflow_id=run.workflow_id,
                needs_human_review=run.needs_human_review,
                started_at=run.started_at,
                finished_at=run.finished_at,
                **_output_props(output),
            )
            has = "HAS_RCA" if label == "RCA" else "HAS_INVESTIGATION"
            b.rel(
                has, ("Incident", inc.id), key, Source("agent_runs", run.id, "incident_id"), project_id=inc.project_id
            )
            if output is None:
                continue
            cites(key, output.get("evidence_refs") or [], inc, _ai_source(run, "output.evidence_refs"))
            seen: set[str] = set()
            for idx, hazard in enumerate(output.get("hazards") or []):
                if not isinstance(hazard, str) or not hazard.strip() or _key(hazard) in seen:
                    continue
                seen.add(_key(hazard))
                src = _ai_source(run, f"output.hazards[{idx}]")
                h = b.node(
                    "Hazard",
                    f"{run.id}:hazard:{idx}",
                    src,
                    **scope,
                    name=hazard.strip(),
                    key=_key(hazard),
                    agent=run.agent,
                    workflow_id=run.workflow_id,
                )
                b.rel("IDENTIFIED_HAZARD", key, h, src, project_id=inc.project_id)
                hazards.setdefault((run.workflow_id, _key(hazard)), []).append(h)
            for idx, cause in enumerate(output.get("root_causes") or []):
                statement = str(cause.get("statement", "")).strip() if isinstance(cause, dict) else ""
                if not statement:
                    continue
                src = _ai_source(run, f"output.root_causes[{idx}]")
                c = b.node(
                    "Cause",
                    f"{run.id}:cause:{idx}",
                    src,
                    **scope,
                    name=statement,
                    key=_key(statement),
                    category=cause.get("category"),
                    confidence=cause.get("confidence"),
                    workflow_id=run.workflow_id,
                )
                b.rel("IDENTIFIED_CAUSE", key, c, src, project_id=inc.project_id)
                causes.setdefault((run.workflow_id, _key(statement)), []).append(c)
        elif run.agent == "compliance" and output is not None:
            for idx, finding in enumerate(output.get("findings") or []):
                requirement = str(finding.get("requirement", "")).strip() if isinstance(finding, dict) else ""
                if not requirement:
                    continue
                src = _ai_source(run, f"output.findings[{idx}]")
                req = b.node(
                    "Requirement",
                    f"{run.id}:finding:{idx}",
                    src,
                    **scope,
                    name=requirement,
                    status=finding.get("status"),
                    note=finding.get("note"),
                    source_title=finding.get("source_title"),
                    source_ref=finding.get("source_ref"),
                    workflow_id=run.workflow_id,
                )
                b.rel("HAS_REQUIREMENT", ("Incident", inc.id), req, src, project_id=inc.project_id)
                target = cite_target(str(finding.get("source_ref", "")), inc)
                if target and target[0][0] == "Document":
                    b.rel(
                        "FROM_DOCUMENT",
                        req,
                        target[0],
                        src.at(f"output.findings[{idx}].source_ref"),
                        project_id=inc.project_id,
                        chunk_id=target[1],
                    )

    workflow_of = {r.id: r.workflow_id for r in runs}
    for a in actions:
        inc = incidents[a.incident_id]
        src = Source(
            "capa_actions",
            a.id,
            None,
            a.ai_generated,
            a.source_run_id if a.ai_generated else None,
            REVIEW_STATUS.get(a.approval_status, UNREVIEWED),
        )
        key = b.node(
            "Action",
            a.id,
            src,
            project_id=inc.project_id,
            incident_id=inc.id,
            name=a.title,
            action_type=a.action_type,
            owner_role=a.owner_role,
            due_date=a.due_date,
            critical=a.critical,
            approval_status=a.approval_status,
            work_status=a.work_status,
        )
        record = Source("capa_actions", a.id)  # columns people set or the workflow records, not model output
        b.rel("HAS_ACTION", ("Incident", inc.id), key, record.at("incident_id"), project_id=inc.project_id)
        b.rel("ASSIGNED_TO", key, person(a.assignee_id), record.at("assignee_id"), project_id=inc.project_id)
        cites(key, a.evidence_refs or [], inc, src.at("evidence_refs"))
        addresses = (a.original_ai_output or {}).get("addresses") if a.ai_generated else None
        workflow = workflow_of.get(a.source_run_id or "")
        if isinstance(addresses, str) and workflow:
            # Linked only when the proposal names a hazard or cause of the same AI workflow word for word.
            targets = hazards.get((workflow, _key(addresses)), []) + causes.get((workflow, _key(addresses)), [])
            for target_key in targets:
                b.rel("ADDRESSES", key, target_key, src.at("original_ai_output.addresses"), project_id=inc.project_id)

    action_project = {a.id: incidents[a.incident_id].project_id for a in actions}
    for ev in approvals:
        b.rel(
            "REVIEWED_BY",
            ("Action", ev.capa_id),
            person(ev.reviewer_id),
            Source("approval_events", ev.id),
            project_id=action_project[ev.capa_id],
            discriminator=ev.id,
            decision=ev.decision,
            reason=ev.reason,
            at=ev.created_at,
        )
    for v in verifications:
        src = Source("verification_records", v.id)
        project_id = action_project[v.capa_id]
        b.rel(
            "VERIFIED_BY",
            ("Action", v.capa_id),
            person(v.verifier_id),
            src,
            project_id=project_id,
            discriminator=v.id,
            effective=v.effective,
            at=v.created_at,
        )
        if v.evidence_id:
            b.rel(
                "VERIFIED_WITH",
                ("Action", v.capa_id),
                ("Evidence", v.evidence_id),
                src.at("evidence_id"),
                project_id=project_id,
                discriminator=v.id,
            )
    return b.projection()


def _all_refs(runs: list[AgentRun], actions: list[CapaAction]) -> set[str]:
    refs: set[str] = set()
    for run in runs:
        out = run.output if isinstance(run.output, dict) else {}
        refs |= {r for r in out.get("evidence_refs") or [] if isinstance(r, str)}
        refs |= {
            f["source_ref"]
            for f in out.get("findings") or []
            if isinstance(f, dict) and isinstance(f.get("source_ref"), str)
        }
    for a in actions:
        refs |= {r for r in a.evidence_refs or [] if isinstance(r, str)}
    return refs


def _chunk_documents(db: Session, chunk_ids: set[str]) -> dict[str, str]:
    ids = sorted(chunk_ids)
    found: dict[str, str] = {}
    for start in range(0, len(ids), 500):
        stmt = select(DocumentChunk.id, DocumentChunk.document_id).where(DocumentChunk.id.in_(ids[start : start + 500]))
        for chunk_id, document_id in db.execute(stmt):
            found[chunk_id] = document_id
    return found


def validate_projection(projection: Projection) -> None:
    """Store boundary check: only schema labels and types, one organization, no dangling relationships."""
    org = projection.organization_id
    keys: set[NodeKey] = set()
    for n in projection.nodes:
        if n.label not in NODE_LABELS:
            raise ValueError(f"Unknown node label {n.label!r}")
        if n.props.get("organization_id") != org or n.props.get("id") != n.id:
            raise ValueError("Every node must carry its id and the projection's organization_id")
        keys.add((n.label, n.id))
    for r in projection.rels:
        if (r.start_label, r.end_label) not in REL_SCHEMA.get(r.type, ()):
            raise ValueError(f"Relationship {r.type!r} is not allowed from {r.start_label} to {r.end_label}")
        if r.props.get("organization_id") != org or r.props.get("id") != r.id:
            raise ValueError("Every relationship must carry its id and the projection's organization_id")
        if (r.start_label, r.start_id) not in keys or (r.end_label, r.end_id) not in keys:
            raise ValueError("Relationship endpoints must be nodes of the same projection")


# --- Stores ---------------------------------------------------------------------------------------------------------


class GraphStore(Protocol):
    backend: str

    def sync_organization(self, projection: Projection) -> SyncResult:
        """Make the organization's part of the graph equal to the projection (idempotent)."""
        ...

    def incident_subgraph(self, organization_id: str, incident_id: str, project_ids: Collection[str]) -> Subgraph:
        """Nodes owned by the incident plus their direct neighbours, limited to the organization and projects."""
        ...

    def organization_ids(self) -> set[str]: ...

    def close(self) -> None: ...


def _visible(props: dict, organization_id: str, project_ids: Collection[str]) -> bool:
    return props.get("organization_id") == organization_id and (
        props.get("project_id") is None or props.get("project_id") in project_ids
    )


class InMemoryGraphStore:
    """Process-local store with the same semantics as the Neo4j adapter. For tests and single-process demos."""

    backend = "memory"

    def __init__(self) -> None:
        self._nodes: dict[NodeKey, dict[str, Any]] = {}
        self._rels: dict[str, Rel] = {}
        self._lock = threading.Lock()

    def sync_organization(self, projection: Projection) -> SyncResult:
        validate_projection(projection)
        org = projection.organization_id
        result = SyncResult(org, self.backend, len(projection.nodes), len(projection.rels))
        with self._lock:
            for n in projection.nodes:
                existing = self._nodes.get((n.label, n.id))
                if existing is not None and existing["organization_id"] != org:
                    raise ValueError("Node id already belongs to another organization")
            wanted_nodes = {(n.label, n.id) for n in projection.nodes}
            wanted_rels = {r.id for r in projection.rels}
            for n in projection.nodes:
                result.nodes_created += (n.label, n.id) not in self._nodes
                self._nodes[(n.label, n.id)] = dict(n.props)
            for r in projection.rels:
                result.relationships_created += r.id not in self._rels
                self._rels[r.id] = replace(r, props=dict(r.props))
            stale = {k for k, p in self._nodes.items() if p["organization_id"] == org and k not in wanted_nodes}
            for rid, r in list(self._rels.items()):
                ends = {(r.start_label, r.start_id), (r.end_label, r.end_id)}
                if (r.props["organization_id"] == org and rid not in wanted_rels) or ends & stale:
                    del self._rels[rid]
                    result.relationships_deleted += 1
            for k in stale:
                del self._nodes[k]
            result.nodes_deleted = len(stale)
        return result

    def incident_subgraph(self, organization_id: str, incident_id: str, project_ids: Collection[str]) -> Subgraph:
        with self._lock:
            owned = {
                k
                for k, p in self._nodes.items()
                if p.get("incident_id") == incident_id and _visible(p, organization_id, project_ids)
            }
            nodes = set(owned)
            rels: list[Rel] = []
            for r in self._rels.values():
                start, end = (r.start_label, r.start_id), (r.end_label, r.end_id)
                if not ({start, end} & owned) or not _visible(r.props, organization_id, project_ids):
                    continue
                other = end if start in owned else start
                if other in self._nodes and _visible(self._nodes[other], organization_id, project_ids):
                    nodes.add(other)
                    rels.append(replace(r, props=dict(r.props)))
            return Subgraph(
                [Node(k[0], k[1], dict(self._nodes[k])) for k in sorted(nodes)], sorted(rels, key=lambda r: r.id)
            )

    def organization_ids(self) -> set[str]:
        with self._lock:
            return {p["organization_id"] for p in self._nodes.values()}

    def snapshot(self, organization_id: str) -> tuple[dict[NodeKey, dict], dict[str, Rel]]:
        """Everything stored for one organization (tests compare snapshots to prove idempotency and isolation)."""
        with self._lock:
            nodes = {k: dict(p) for k, p in self._nodes.items() if p["organization_id"] == organization_id}
            rels = {k: r for k, r in self._rels.items() if r.props["organization_id"] == organization_id}
            return nodes, rels

    def close(self) -> None:
        return None


# Neo4j: fixed query text per allowlisted label / relationship type. Record data is passed only as parameters.
_ENTITY = "SgEntity"  # common label on every Site Guard node: org/incident indexes and safe stale-node deletes
_CONSTRAINTS = tuple(
    f"CREATE CONSTRAINT sg_{label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
    for label in NODE_LABELS
)
_INDEXES = (
    f"CREATE INDEX sg_entity_org IF NOT EXISTS FOR (n:{_ENTITY}) ON (n.organization_id)",
    f"CREATE INDEX sg_entity_incident IF NOT EXISTS FOR (n:{_ENTITY}) ON (n.incident_id)",
)
_UPSERT_NODES = {
    label: (
        f"UNWIND $rows AS row MERGE (n:{label} {{id: row.id}}) "
        "ON CREATE SET n.organization_id = $organization_id "
        "WITH n, row WHERE n.organization_id = $organization_id "
        f"SET n = row.props, n:{_ENTITY} RETURN count(n) AS written"
    )
    for label in NODE_LABELS
}
_UPSERT_RELS = {
    (rel_type, start, end): (
        "UNWIND $rows AS row "
        f"MATCH (a:{start} {{id: row.start}}) WHERE a.organization_id = $organization_id "
        f"MATCH (b:{end} {{id: row.end}}) WHERE b.organization_id = $organization_id "
        f"MERGE (a)-[r:{rel_type} {{id: row.id}}]->(b) SET r = row.props RETURN count(r) AS written"
    )
    for rel_type, pairs in REL_SCHEMA.items()
    for start, end in pairs
}
_DELETE_STALE_RELS = (
    f"MATCH (a:{_ENTITY} {{organization_id: $organization_id}})-[r]->() "
    "WHERE r.organization_id = $organization_id AND NOT r.id IN $keep DELETE r"
)
_DELETE_STALE_NODES = {
    label: f"MATCH (n:{label}:{_ENTITY} {{organization_id: $organization_id}}) WHERE NOT n.id IN $keep DETACH DELETE n"
    for label in NODE_LABELS
}
_INCIDENT_SUBGRAPH = (
    f"MATCH (n:{_ENTITY} {{organization_id: $organization_id, incident_id: $incident_id}}) "
    "WHERE n.project_id IS NULL OR n.project_id IN $project_ids "
    f"OPTIONAL MATCH (n)-[r]-(m:{_ENTITY} {{organization_id: $organization_id}}) "
    "WHERE r.organization_id = $organization_id AND (r.project_id IS NULL OR r.project_id IN $project_ids) "
    "AND (m.project_id IS NULL OR m.project_id IN $project_ids) "
    "RETURN properties(n) AS n_props, labels(n) AS n_labels, type(r) AS r_type, properties(r) AS r_props, "
    "startNode(r).id AS r_start, endNode(r).id AS r_end, properties(m) AS m_props, labels(m) AS m_labels"
)
_ORGANIZATIONS = f"MATCH (n:{_ENTITY}) RETURN DISTINCT n.organization_id AS organization_id"
_BATCH = 500


def _batches(rows: list[dict], size: int = _BATCH) -> Iterable[list[dict]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _label_of(labels: list[str]) -> str:
    return next(label for label in labels if label in NODE_LABELS)


class Neo4jGraphStore:
    """Neo4j adapter on the official driver. Nodes MERGE on (label, id) under uniqueness constraints."""

    backend = "neo4j"

    def __init__(self, driver: Any):
        self._driver = driver
        self._schema_ready = False

    @classmethod
    def connect(cls, s: Settings) -> Neo4jGraphStore:
        from neo4j import GraphDatabase
        from neo4j.exceptions import DriverError

        try:
            driver = GraphDatabase.driver(
                s.neo4j_uri,
                auth=(s.neo4j_user, s.neo4j_password.get_secret_value()),
                connection_timeout=10.0,
                max_transaction_retry_time=15.0,
            )
        except (DriverError, ValueError) as exc:  # e.g. a malformed URI; the message may echo it, so log the type
            log.warning("graph store error", extra={"extra_fields": {"error": type(exc).__name__}})
            raise GraphUnavailable() from exc
        return cls(driver)

    def _guard(self, fn: Callable[[], Any]) -> Any:
        from neo4j.exceptions import DriverError, Neo4jError

        try:
            return fn()
        except (Neo4jError, DriverError) as exc:
            log.warning("graph store error", extra={"extra_fields": {"error": type(exc).__name__}})
            raise GraphUnavailable() from exc

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return

        def create() -> None:
            with self._driver.session() as session:
                for statement in _CONSTRAINTS + _INDEXES:
                    session.run(statement).consume()

        self._guard(create)
        self._schema_ready = True

    def sync_organization(self, projection: Projection) -> SyncResult:
        validate_projection(projection)
        self.ensure_schema()
        org = projection.organization_id
        by_label: dict[str, list[dict]] = {label: [] for label in NODE_LABELS}
        for n in projection.nodes:
            by_label[n.label].append({"id": n.id, "props": n.props})
        by_type: dict[tuple[str, str, str], list[dict]] = {}
        for r in projection.rels:
            row = {"id": r.id, "start": r.start_id, "end": r.end_id, "props": r.props}
            by_type.setdefault((r.type, r.start_label, r.end_label), []).append(row)

        def work(tx: Any) -> SyncResult:
            result = SyncResult(org, self.backend, len(projection.nodes), len(projection.rels))
            for label, rows in by_label.items():
                for batch in _batches(rows):
                    res = tx.run(_UPSERT_NODES[label], {"rows": batch, "organization_id": org})
                    if res.single()["written"] != len(batch):
                        raise ValueError("Node id already belongs to another organization")
                    result.nodes_created += res.consume().counters.nodes_created
            for key, rows in sorted(by_type.items()):
                for batch in _batches(rows):
                    res = tx.run(_UPSERT_RELS[key], {"rows": batch, "organization_id": org})
                    if res.single()["written"] != len(batch):
                        raise ValueError("Relationship endpoints are missing from the organization's graph")
                    result.relationships_created += res.consume().counters.relationships_created
            keep_rels = [r.id for r in projection.rels]
            counters = tx.run(_DELETE_STALE_RELS, {"organization_id": org, "keep": keep_rels}).consume().counters
            result.relationships_deleted += counters.relationships_deleted
            for label in NODE_LABELS:
                keep = [row["id"] for row in by_label[label]]
                counters = tx.run(_DELETE_STALE_NODES[label], {"organization_id": org, "keep": keep}).consume().counters
                result.nodes_deleted += counters.nodes_deleted
                result.relationships_deleted += counters.relationships_deleted
            return result

        def run() -> SyncResult:
            with self._driver.session() as session:
                return session.execute_write(work)

        return self._guard(run)

    def incident_subgraph(self, organization_id: str, incident_id: str, project_ids: Collection[str]) -> Subgraph:
        self.ensure_schema()
        params = {"organization_id": organization_id, "incident_id": incident_id, "project_ids": sorted(project_ids)}

        def run() -> list[dict]:
            with self._driver.session() as session:
                return session.execute_read(lambda tx: tx.run(_INCIDENT_SUBGRAPH, params).data())

        rows = self._guard(run)
        nodes: dict[NodeKey, Node] = {}
        for row in rows:
            for props_key, labels_key in (("n_props", "n_labels"), ("m_props", "m_labels")):
                props = row.get(props_key)
                if props:
                    label = _label_of(row[labels_key])
                    nodes[(label, props["id"])] = Node(label, props["id"], dict(props))
        label_of = {node_id: label for label, node_id in nodes}
        rels: dict[str, Rel] = {}
        for row in rows:
            if row.get("r_type") and row["r_start"] in label_of and row["r_end"] in label_of:
                props = dict(row["r_props"])
                start, end = row["r_start"], row["r_end"]
                rels[props["id"]] = Rel(row["r_type"], props["id"], label_of[start], start, label_of[end], end, props)
        return Subgraph([nodes[k] for k in sorted(nodes)], sorted(rels.values(), key=lambda r: r.id))

    def organization_ids(self) -> set[str]:
        self.ensure_schema()

        def run() -> list[dict]:
            with self._driver.session() as session:
                return session.execute_read(lambda tx: tx.run(_ORGANIZATIONS, {}).data())

        return {row["organization_id"] for row in self._guard(run) if row.get("organization_id")}

    def close(self) -> None:
        self._driver.close()


# --- Store selection and service functions ---------------------------------------------------------------------------

_store: GraphStore | None = None
_store_key: tuple | None = None
_store_lock = threading.Lock()


def get_store() -> GraphStore:
    """The configured store. Raises GraphDisabled (409) when SITEGUARD_GRAPH_BACKEND=disabled."""
    global _store, _store_key
    s = get_settings()
    if s.graph_backend == "disabled":
        raise GraphDisabled()
    key = (s.graph_backend, s.neo4j_uri, s.neo4j_user)
    with _store_lock:
        if _store is None or _store_key != key:
            if _store is not None:
                _store.close()
            _store = InMemoryGraphStore() if s.graph_backend == "memory" else Neo4jGraphStore.connect(s)
            _store_key = key
        return _store


def close_store() -> None:
    global _store, _store_key
    with _store_lock:
        if _store is not None:
            _store.close()
        _store, _store_key = None, None


def sync(db: Session, store: GraphStore, organization_id: str) -> SyncResult:
    """Rebuild one organization's projection from PostgreSQL and write it to the store."""
    return store.sync_organization(build_projection(db, organization_id))


def sync_all(db: Session, store: GraphStore) -> dict[str, dict]:
    """Every organization, then remove graph data of organizations that no longer exist in PostgreSQL."""
    org_ids = list(db.scalars(select(Organization.id).order_by(Organization.id)))
    out = {org_id: sync(db, store, org_id).as_dict() for org_id in org_ids}
    for gone in sorted(store.organization_ids() - set(org_ids)):
        out[gone] = store.sync_organization(Projection(gone)).as_dict()
    return out


def _split(props: dict) -> tuple[dict, dict]:
    provenance = {k: props.get(k) for k in PROVENANCE_KEYS}
    provenance["ai_derived"] = bool(provenance["ai_derived"])
    properties = {k: v for k, v in props.items() if k not in PROVENANCE_KEYS and k != "id"}
    return properties, provenance


def incident_graph(
    store: GraphStore, incident: Incident, project_ids: Collection[str], *, include_ai: bool = True
) -> dict:
    """The incident's neighbourhood with provenance, limited to its organization and the caller's projects."""
    org, allowed = incident.organization_id, set(project_ids)
    sub = store.incident_subgraph(org, incident.id, allowed)
    # Defence in depth: whatever the store returned, keep only this organization's records the caller may see.
    nodes = {
        (n.label, n.id): n
        for n in sub.nodes
        if _visible(n.props, org, allowed) and (include_ai or not n.props.get("ai_derived"))
    }
    rels = [
        r
        for r in sub.rels
        if (r.start_label, r.start_id) in nodes
        and (r.end_label, r.end_id) in nodes
        and _visible(r.props, org, allowed)
        and (include_ai or not r.props.get("ai_derived"))
    ]
    linked = {(r.start_label, r.start_id) for r in rels} | {(r.end_label, r.end_id) for r in rels}
    out_nodes, out_edges = [], []
    for k, n in nodes.items():
        if n.props.get("incident_id") == incident.id or k in linked:
            properties, provenance = _split(n.props)
            out_nodes.append({"id": n.id, "label": n.label, "properties": properties, "provenance": provenance})
    for r in rels:
        properties, provenance = _split(r.props)
        out_edges.append(
            {
                "id": r.id,
                "type": r.type,
                "source": r.start_id,
                "source_label": r.start_label,
                "target": r.end_id,
                "target_label": r.end_label,
                "properties": properties,
                "provenance": provenance,
            }
        )
    return {
        "incident_id": incident.id,
        "backend": store.backend,
        "include_ai": include_ai,
        "synced": ("Incident", incident.id) in nodes,
        "nodes": out_nodes,
        "edges": out_edges,
        "note": NOTE,
    }
