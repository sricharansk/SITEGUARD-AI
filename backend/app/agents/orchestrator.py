"""Stateful, bounded investigation workflow.

triage -> safety and/or quality -> deterministic risk -> RCA -> compliance -> CAPA (PENDING_REVIEW)

Agents never change incident status to CLOSED and never approve actions. The workflow ends at
PENDING_APPROVAL, where a human reviews every proposed action.
"""

import re
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.framework import AgentResult, Provider, run_agent
from app.agents.llm import get_provider
from app.agents.registry import AGENTS
from app.core.errors import Conflict
from app.models import (
    AgentRun,
    ApprovalStatus,
    CapaAction,
    Evidence,
    Incident,
    IncidentStatus,
    RiskAssessment,
    utcnow,
)
from app.services import audit, lifecycle, rag, risk, vision

RUNNABLE_FROM = {
    IncidentStatus.REPORTED,
    IncidentStatus.TRIAGED,
    IncidentStatus.UNDER_INVESTIGATION,
    IncidentStatus.PENDING_APPROVAL,
}
_WORD = re.compile(r"[a-z]{4,}")


def incident_dict(inc: Incident) -> dict:
    return {
        "id": inc.id,
        "reference": inc.reference,
        "title": inc.title,
        "description": inc.description,
        "domain": inc.domain.value if hasattr(inc.domain, "value") else inc.domain,
        "reported_severity": inc.severity.value if hasattr(inc.severity, "value") else inc.severity,
        "occurred_at": inc.occurred_at.isoformat(),
        "location": inc.location,
        "activity": inc.activity,
        "people_involved": inc.people_involved,
        "immediate_actions": inc.immediate_actions,
    }


def build_tools(db: Session, inc: Incident, state: dict) -> dict:
    def get_incident() -> dict:
        return incident_dict(inc)

    def list_evidence() -> list[dict]:
        rows = db.scalars(select(Evidence).where(Evidence.incident_id == inc.id).order_by(Evidence.created_at))
        return [
            {
                "id": e.id,
                "filename": e.filename,
                "content_type": e.content_type,
                "description": e.description,
                "sha256": e.sha256,
            }
            for e in rows
        ]

    def search_knowledge(query: str, domain=None, limit: int = 5) -> list[dict]:
        hits = rag.search(
            db,
            organization_id=inc.organization_id,
            project_id=inc.project_id,
            query=query,
            domain=domain,
            limit=min(limit, 8),
        )
        return [h.as_dict() for h in hits]

    def similar_incidents() -> list[dict]:
        mine = set(_WORD.findall(f"{inc.title} {inc.description}".lower()))
        rows = db.scalars(
            select(Incident).where(Incident.organization_id == inc.organization_id, Incident.id != inc.id)
        )
        scored = []
        for other in rows:
            theirs = set(_WORD.findall(f"{other.title} {other.description}".lower()))
            if mine and theirs:
                j = len(mine & theirs) / len(mine | theirs)
                if j >= 0.12:
                    scored.append((j, other))
        scored.sort(key=lambda t: -t[0])
        return [
            {"reference": o.reference, "title": o.title, "status": o.status.value, "similarity": round(j, 2)}
            for j, o in scored[:3]
        ]

    def get_prior_outputs() -> dict:
        return dict(state)

    def list_vision_observations() -> list[dict]:
        return vision.for_agents(db, inc.id)

    return {
        "get_incident": get_incident,
        "list_evidence": list_evidence,
        "search_knowledge": search_knowledge,
        "similar_incidents": similar_incidents,
        "get_prior_outputs": get_prior_outputs,
        "list_vision_observations": list_vision_observations,
    }


def _record_run(
    db: Session,
    inc: Incident,
    workflow_id: str,
    agent: str,
    result: AgentResult | None,
    user_id: str,
    error: str | None = None,
) -> AgentRun:
    run = AgentRun(
        incident_id=inc.id,
        workflow_id=workflow_id,
        agent=agent,
        provider=result.provider if result else "n/a",
        status="SUCCEEDED" if result else "FAILED",
        output=result.output.model_dump(mode="json") if result else None,
        trace=(result.trace + [{"type": "review_reasons", "reasons": result.review_reasons}]) if result else [],
        error=error,
        needs_human_review=result.needs_human_review if result else True,
        finished_at=utcnow(),
        triggered_by=user_id,
    )
    db.add(run)
    db.flush()
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=user_id,
        actor_type="AGENT",
        action=f"agent.{agent}.{run.status.lower()}",
        entity_type="incident",
        entity_id=inc.id,
        details={"run_id": run.id, "workflow_id": workflow_id, "provider": run.provider},
    )
    return run


def run_triage(db: Session, inc: Incident, user_id: str, provider: Provider | None = None) -> AgentRun:
    if inc.status not in RUNNABLE_FROM:
        raise Conflict(f"Agents cannot run on an incident in status {inc.status.value}", "INVALID_STATE")
    provider = provider or get_provider()
    workflow_id = str(uuid.uuid4())
    result = run_agent(AGENTS["triage"], build_tools(db, inc, {}), provider)
    run = _record_run(db, inc, workflow_id, "triage", result, user_id)
    if inc.status == IncidentStatus.REPORTED:
        lifecycle.transition(
            db, inc, IncidentStatus.TRIAGED, actor_id=user_id, actor_type="AGENT", note="AI triage completed"
        )
    return run


def run_investigation(db: Session, inc: Incident, user_id: str, provider: Provider | None = None) -> dict:
    if inc.status not in RUNNABLE_FROM:
        raise Conflict(f"Agents cannot run on an incident in status {inc.status.value}", "INVALID_STATE")
    provider = provider or get_provider()
    workflow_id = str(uuid.uuid4())
    state: dict = {}
    runs: dict[str, AgentRun] = {}
    tools = build_tools(db, inc, state)

    def step(name: str) -> AgentResult | None:
        try:
            result = run_agent(AGENTS[name], tools, provider)
        except Exception as exc:  # agent failure: keep the incident, record it, continue manually
            runs[name] = _record_run(db, inc, workflow_id, name, None, user_id, error=type(exc).__name__)
            return None
        runs[name] = _record_run(db, inc, workflow_id, name, result, user_id)
        state[name] = result.output.model_dump(mode="json")
        return result

    tri = step("triage")
    lifecycle.advance_to(
        db,
        inc,
        IncidentStatus.UNDER_INVESTIGATION,
        actor_id=user_id,
        actor_type="AGENT",
        note="AI investigation started",
    )
    next_agents = tri.output.recommended_next_agents if tri else ["safety", "quality"]  # type: ignore[attr-defined]
    for name in ("safety", "quality"):
        if name in next_agents:
            step(name)

    # Deterministic risk from the most severe suggested inputs.
    suggestions = [state[a] for a in ("safety", "quality") if a in state]
    assessment = None
    if suggestions:
        lk = max(s["likelihood"] for s in suggestions)
        cq = max(s["consequence"] for s in suggestions)
        r = risk.assess(lk, cq)
        assessment = RiskAssessment(
            incident_id=inc.id,
            matrix_version=r.matrix_version,
            likelihood=lk,
            consequence=cq,
            score=r.score,
            band=r.band,
            rationale=r.rationale,
            inputs_source="AI_SUGGESTED",
            assessed_by=user_id,
        )
        db.add(assessment)
        state["risk"] = {"score": r.score, "band": r.band, "rationale": r.rationale}

    for name in ("rca", "compliance", "capa"):
        step(name)

    # Conflict detection: triage vs reported severity.
    flags: list[str] = []
    if tri:
        order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        reported = inc.severity.value
        proposed = tri.output.severity_candidate.value  # type: ignore[attr-defined]
        if abs(order.index(reported) - order.index(proposed)) >= 2:
            flags.append(f"Reported severity {reported} differs from AI triage {proposed}; human review needed.")
    if assessment and assessment.band == "CRITICAL" and inc.severity.value != "CRITICAL":
        flags.append("Risk matrix rates this CRITICAL but the incident is not marked CRITICAL.")

    # Replace earlier AI proposals that nobody has reviewed yet.
    for old in db.scalars(
        select(CapaAction).where(
            CapaAction.incident_id == inc.id,
            CapaAction.ai_generated,
            CapaAction.approval_status == ApprovalStatus.PENDING_REVIEW,
        )
    ):
        old.approval_status = ApprovalStatus.SUPERSEDED

    created: list[CapaAction] = []
    if "capa" in state:
        critical = bool(assessment and assessment.band in ("HIGH", "CRITICAL")) or inc.severity.value == "CRITICAL"
        for p in state["capa"]["actions"]:
            action = CapaAction(
                incident_id=inc.id,
                action_type=p["action_type"],
                title=p["title"],
                description=p["description"],
                owner_role=p["owner_role"],
                due_date=date.today() + timedelta(days=p["due_in_days"]),
                verification_criteria=p["verification_criteria"],
                critical=critical,
                approval_status=ApprovalStatus.PENDING_REVIEW,
                ai_generated=True,
                original_ai_output=p,
                source_run_id=runs["capa"].id,
                evidence_refs=state["capa"].get("evidence_refs", []),
            )
            db.add(action)
            created.append(action)
    db.flush()
    if inc.status != IncidentStatus.PENDING_APPROVAL:
        lifecycle.transition(
            db,
            inc,
            IncidentStatus.PENDING_APPROVAL,
            actor_id=user_id,
            actor_type="AGENT",
            note=f"AI investigation finished; {len(created)} action(s) awaiting human review",
        )
    return {
        "workflow_id": workflow_id,
        "runs": list(runs.values()),
        "risk": assessment,
        "capa": created,
        "flags": flags,
    }
