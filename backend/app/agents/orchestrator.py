"""Stateful, bounded, resumable investigation workflow (Playbook Prompts 29, 30 and 37; docs/AGENTS.md#workflow).

intake -> triage -> safety and/or quality -> deterministic risk -> RCA -> compliance -> CAPA -> approval hand-off

Each agent retrieves its own knowledge (RAG) through the `search_knowledge` tool. The workflow is a `WorkflowRun`
checkpointed after every stage, so it can pause for human review, be resumed, and survive a crash without redoing
or duplicating finished stages. Agents never change incident status to CLOSED and never approve actions; the
workflow ends at PENDING_APPROVAL, where people review every proposed action and every recorded conflict.
"""

import re
import time
from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.framework import AgentResult, Provider, run_agent
from app.agents.llm import get_provider
from app.agents.registry import AGENTS
from app.core.config import get_settings
from app.core.errors import AppError, Conflict
from app.models import (
    AgentConflict,
    AgentRun,
    ApprovalStatus,
    CapaAction,
    Evidence,
    Incident,
    IncidentStatus,
    RiskAssessment,
    WorkflowRun,
    WorkflowStatus,
    utcnow,
)
from app.services import audit, conflicts, lifecycle, rag, risk, vision

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

    def list_vision_observations() -> dict:
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


STAGES = ("triage", "safety", "quality", "risk", "rca", "compliance", "capa", "approval")
PAUSABLE = STAGES[:-1]  # a person may stop the workflow after any stage before the hand-off
DONE = {"SUCCEEDED", "FAILED", "SKIPPED"}  # FAILED: an agent failed after its retries; the workflow carried on
Checkpoint = Callable[[], None]


def _lease(wf: WorkflowRun) -> None:
    wf.lease_expires_at = utcnow() + timedelta(seconds=get_settings().workflow_lease_seconds)


def _lease_expired(wf: WorkflowRun) -> bool:
    expires = wf.lease_expires_at
    if expires is None:
        return True
    if expires.tzinfo is None:  # SQLite returns naive datetimes
        expires = expires.replace(tzinfo=utcnow().tzinfo)
    return expires < utcnow()


def active_workflow(db: Session, incident_id: str) -> WorkflowRun | None:
    return db.scalar(
        select(WorkflowRun).where(
            WorkflowRun.incident_id == incident_id,
            WorkflowRun.status.in_([WorkflowStatus.RUNNING, WorkflowStatus.PAUSED]),
        )
    )


def _lock_incident(db: Session, inc: Incident) -> None:
    """Serialize workflow starts per incident (row lock on PostgreSQL; SQLite serializes writers anyway)."""
    db.execute(select(Incident.id).where(Incident.id == inc.id).with_for_update())


def _check_runnable(db: Session, inc: Incident) -> None:
    if inc.status not in RUNNABLE_FROM:
        raise Conflict(f"Agents cannot run on an incident in status {inc.status.value}", "INVALID_STATE")
    current = active_workflow(db, inc.id)
    if current is not None:
        raise Conflict(
            f"Workflow {current.id} is {current.status.value} for this incident; resume or cancel it first",
            "WORKFLOW_ACTIVE",
        )


def _audit(db: Session, wf: WorkflowRun, inc: Incident, action: str, user_id: str, **details) -> None:
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=user_id,
        action=action,
        entity_type="workflow",
        entity_id=wf.id,
        details={"incident_id": inc.id, **details},
    )


def _validate_pause_after(pause_after) -> list[str]:
    stages = list(dict.fromkeys(pause_after or []))
    unknown = [s for s in stages if s not in PAUSABLE]
    if unknown:
        raise AppError(f"Unknown pause stage(s) {', '.join(unknown)}; choose from {', '.join(PAUSABLE)}")
    return stages


def run_triage(db: Session, inc: Incident, user_id: str, provider: Provider | None = None) -> AgentRun:
    _lock_incident(db, inc)
    _check_runnable(db, inc)
    provider = provider or get_provider()
    wf = WorkflowRun(
        organization_id=inc.organization_id,
        incident_id=inc.id,
        kind="TRIAGE",
        status=WorkflowStatus.RUNNING,
        provider=provider.name,
        current_stage="triage",
        started_by=user_id,
    )
    db.add(wf)
    db.flush()
    result = run_agent(AGENTS["triage"], build_tools(db, inc, {}), provider)
    run = _record_run(db, inc, wf.id, "triage", result, user_id)
    wf.stages = {"triage": _stage_record("SUCCEEDED", 1, [], run, result)}
    wf.state = {"triage": result.output.model_dump(mode="json")}
    wf.status, wf.finished_at, wf.current_stage = WorkflowStatus.COMPLETED, utcnow(), None
    if inc.status == IncidentStatus.REPORTED:
        lifecycle.transition(
            db, inc, IncidentStatus.TRIAGED, actor_id=user_id, actor_type="AGENT", note="AI triage completed"
        )
    return run


def _stage_record(status: str, attempts: int, errors: list[str], run: AgentRun | None, result=None) -> dict:
    rec: dict = {"status": status, "attempts": attempts, "errors": errors, "finished_at": utcnow().isoformat()}
    if run is not None:
        rec["run_id"] = run.id
    if result is not None:
        rec["confidence"] = result.output.confidence
        rec["needs_human_review"] = result.needs_human_review
        rec["review_reasons"] = result.review_reasons
    return rec


def start_investigation(
    db: Session,
    inc: Incident,
    user_id: str,
    provider: Provider | None = None,
    *,
    pause_after=(),
    checkpoint: Checkpoint | None = None,
) -> WorkflowRun:
    """Start a new investigation workflow and run it until it completes, pauses or fails.

    `checkpoint` commits after each stage (the API passes `db.commit`); without it, stages are only flushed, so the
    caller's transaction decides (seeding and unit tests)."""
    stages = _validate_pause_after(pause_after)
    _lock_incident(db, inc)
    _check_runnable(db, inc)
    provider = provider or get_provider()
    wf = WorkflowRun(
        organization_id=inc.organization_id,
        incident_id=inc.id,
        kind="INVESTIGATION",
        status=WorkflowStatus.RUNNING,
        provider=provider.name,
        stages={},
        state={},
        pause_after=stages,
        started_by=user_id,
    )
    _lease(wf)
    db.add(wf)
    db.flush()
    _audit(db, wf, inc, "workflow.start", user_id, provider=provider.name, pause_after=stages)
    (checkpoint or db.flush)()
    return _run(db, wf, inc, user_id, provider, checkpoint)


def resume(
    db: Session,
    wf: WorkflowRun,
    inc: Incident,
    user_id: str,
    provider: Provider | None = None,
    *,
    pause_after=None,
    checkpoint: Checkpoint | None = None,
) -> WorkflowRun:
    """Continue a PAUSED or FAILED workflow, or a RUNNING one whose process died (lease expired)."""
    _lock_incident(db, inc)
    if wf.kind != "INVESTIGATION":
        raise Conflict("Only investigation workflows can be resumed", "INVALID_STATE")
    resumable = wf.status in (WorkflowStatus.PAUSED, WorkflowStatus.FAILED) or (
        wf.status == WorkflowStatus.RUNNING and _lease_expired(wf)
    )
    if not resumable:
        raise Conflict(f"Workflow is {wf.status.value} and cannot be resumed", "INVALID_STATE")
    if inc.status not in RUNNABLE_FROM:
        raise Conflict(f"Agents cannot run on an incident in status {inc.status.value}", "INVALID_STATE")
    other = active_workflow(db, inc.id)
    if other is not None and other.id != wf.id:
        raise Conflict(f"Workflow {other.id} is {other.status.value} for this incident", "WORKFLOW_ACTIVE")
    if pause_after is not None:
        wf.pause_after = _validate_pause_after(pause_after)
    provider = provider or get_provider()
    previous = wf.status.value
    wf.status, wf.pause_requested, wf.status_reason, wf.provider = WorkflowStatus.RUNNING, False, None, provider.name
    _lease(wf)
    _audit(db, wf, inc, "workflow.resume", user_id, previous=previous, provider=provider.name)
    (checkpoint or db.flush)()
    return _run(db, wf, inc, user_id, provider, checkpoint)


def request_pause(db: Session, wf: WorkflowRun, inc: Incident, user_id: str) -> WorkflowRun:
    """Ask a RUNNING workflow to stop before its next stage. The stage in progress finishes first."""
    if wf.status != WorkflowStatus.RUNNING:
        raise Conflict(f"Workflow is {wf.status.value}; only a RUNNING workflow can be paused", "INVALID_STATE")
    wf.pause_requested = True
    _audit(db, wf, inc, "workflow.pause_requested", user_id)
    return wf


def cancel(db: Session, wf: WorkflowRun, inc: Incident, user_id: str, reason: str) -> WorkflowRun:
    """Stop a workflow for good. Everything it produced (runs, risk, proposals, conflicts) is kept."""
    stoppable = wf.status in (WorkflowStatus.PAUSED, WorkflowStatus.FAILED) or (
        wf.status == WorkflowStatus.RUNNING and _lease_expired(wf)
    )
    if not stoppable:
        raise Conflict(f"Workflow is {wf.status.value} and cannot be cancelled", "INVALID_STATE")
    wf.status, wf.status_reason, wf.finished_at, wf.lease_expires_at = (
        WorkflowStatus.CANCELLED,
        reason,
        utcnow(),
        None,
    )
    _audit(db, wf, inc, "workflow.cancel", user_id, reason=reason)
    return wf


def _run(
    db: Session,
    wf: WorkflowRun,
    inc: Incident,
    user_id: str,
    provider: Provider,
    checkpoint: Checkpoint | None,
) -> WorkflowRun:
    commit = checkpoint or db.flush
    wf_id, inc_id = wf.id, inc.id
    state: dict = dict(wf.state or {})
    stages: dict = dict(wf.stages or {})
    tools = build_tools(db, inc, state)
    for name in STAGES:
        if stages.get(name, {}).get("status") in DONE:
            continue
        db.refresh(wf, ["pause_requested"])  # a pause requested by another request takes effect here
        if wf.pause_requested:
            _pause(db, wf, inc, user_id, f"Paused on request before the {name} stage.")
            commit()
            return wf
        wf.current_stage = name
        _lease(wf)
        try:
            stages[name] = _run_stage(db, wf, inc, name, state, stages, tools, provider, user_id)
        except Exception as exc:  # unexpected: keep finished stages, record the failure, allow resume
            if checkpoint is None:
                raise
            db.rollback()
            wf, inc = db.get(WorkflowRun, wf_id), db.get(Incident, inc_id)  # type: ignore[assignment]
            stages = dict(wf.stages or {})
            stages[name] = {"status": "ERROR", "error": type(exc).__name__, "finished_at": utcnow().isoformat()}
            wf.stages, wf.status, wf.lease_expires_at = stages, WorkflowStatus.FAILED, None
            wf.status_reason = (
                f"The {name} stage failed ({type(exc).__name__}). Finished stages and their results are kept; "
                "resume the workflow to retry this stage."
            )
            _audit(db, wf, inc, "workflow.failed", user_id, stage=name, error=type(exc).__name__)
            checkpoint()
            return wf
        wf.stages, wf.state = dict(stages), dict(state)
        if name in (wf.pause_after or []):
            _pause(db, wf, inc, user_id, f"Paused for human review after the {name} stage.")
            commit()
            return wf
        commit()
    wf.status, wf.current_stage, wf.finished_at, wf.lease_expires_at = WorkflowStatus.COMPLETED, None, utcnow(), None
    _audit(db, wf, inc, "workflow.complete", user_id, stages={k: v.get("status") for k, v in stages.items()})
    commit()
    return wf


def _pause(db: Session, wf: WorkflowRun, inc: Incident, user_id: str, reason: str) -> None:
    wf.status, wf.status_reason, wf.pause_requested, wf.lease_expires_at = WorkflowStatus.PAUSED, reason, False, None
    _audit(db, wf, inc, "workflow.paused", user_id, stage=wf.current_stage, reason=reason)


def _agent_stage(db, wf, inc, name, state, tools, provider, user_id) -> dict:
    """Run one agent with bounded retries and exponential backoff. Agents only read, so a retry is safe."""
    s = get_settings()
    errors: list[str] = []
    for attempt in range(1, s.agent_max_attempts + 1):
        try:
            result = run_agent(AGENTS[name], tools, provider)
        except Exception as exc:  # agent failure: isolated, recorded, the workflow continues without it
            errors.append(type(exc).__name__)
            if attempt < s.agent_max_attempts:
                time.sleep(s.agent_retry_backoff_seconds * 2 ** (attempt - 1))
                continue
            run = _record_run(db, inc, wf.id, name, None, user_id, error=type(exc).__name__)
            return _stage_record("FAILED", attempt, errors, run)
        run = _record_run(db, inc, wf.id, name, result, user_id)
        state[name] = result.output.model_dump(mode="json")
        return _stage_record("SUCCEEDED", attempt, errors, run, result)
    raise AssertionError("unreachable")  # pragma: no cover


def _run_stage(db, wf, inc, name, state, stages, tools, provider, user_id) -> dict:
    if name == "triage":
        rec = _agent_stage(db, wf, inc, name, state, tools, provider, user_id)
        lifecycle.advance_to(
            db,
            inc,
            IncidentStatus.UNDER_INVESTIGATION,
            actor_id=user_id,
            actor_type="AGENT",
            note="AI investigation started",
        )
        return rec
    if name in ("safety", "quality"):
        wanted = state["triage"]["recommended_next_agents"] if "triage" in state else ["safety", "quality"]
        if name not in wanted:
            return {"status": "SKIPPED", "reason": "Not recommended by triage", "finished_at": utcnow().isoformat()}
        return _agent_stage(db, wf, inc, name, state, tools, provider, user_id)
    if name == "risk":
        return _risk_stage(db, inc, state, user_id)
    if name in ("rca", "compliance"):
        return _agent_stage(db, wf, inc, name, state, tools, provider, user_id)
    if name == "capa":
        rec = _agent_stage(db, wf, inc, name, state, tools, provider, user_id)
        rec["actions"] = _propose_actions(db, inc, state, rec, stages, user_id) if rec["status"] == "SUCCEEDED" else []
        return rec
    if name == "approval":
        return _approval_stage(db, wf, inc, state, stages, user_id)
    raise ValueError(name)  # pragma: no cover


def _risk_stage(db: Session, inc: Incident, state: dict, user_id: str) -> dict:
    """Deterministic risk from the most severe suggested inputs. A disagreement between agents is kept (Prompt 30)."""
    suggestions = [state[a] for a in ("safety", "quality") if a in state]
    if not suggestions:
        return {"status": "SKIPPED", "reason": "No investigation output to score", "finished_at": utcnow().isoformat()}
    lk = max(x["likelihood"] for x in suggestions)
    cq = max(x["consequence"] for x in suggestions)
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
    db.flush()
    state["risk"] = {"score": r.score, "band": r.band, "rationale": r.rationale, "assessment_id": assessment.id}
    return {"status": "SUCCEEDED", "assessment_id": assessment.id, "finished_at": utcnow().isoformat()}


def _propose_actions(db: Session, inc: Incident, state: dict, rec: dict, stages: dict, user_id: str) -> list[str]:
    """Create the CAPA proposals. Runs in the same checkpoint as the stage, so a resume never creates them twice."""
    for old in db.scalars(
        select(CapaAction).where(
            CapaAction.incident_id == inc.id,
            CapaAction.ai_generated,
            CapaAction.approval_status == ApprovalStatus.PENDING_REVIEW,
        )
    ):
        old.approval_status = ApprovalStatus.SUPERSEDED  # earlier AI proposals nobody reviewed yet
    band = state.get("risk", {}).get("band")
    critical = band in ("HIGH", "CRITICAL") or inc.severity.value == "CRITICAL"
    created = []
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
            source_run_id=rec["run_id"],
            evidence_refs=state["capa"].get("evidence_refs", []),
        )
        db.add(action)
        created.append(action)
    db.flush()
    return [a.id for a in created]


def _approval_stage(db: Session, wf: WorkflowRun, inc: Incident, state: dict, stages: dict, user_id: str) -> dict:
    """Record conflicts and uncertainty, then hand the incident to people (PENDING_APPROVAL)."""
    findings = (
        conflicts.agent_findings(inc, state)
        + conflicts.source_findings(db, inc, state)
        + conflicts.vision_findings(db, inc)
    )
    rows = conflicts.record(db, inc, wf.id, findings, user_id)
    wf.uncertainty = conflicts.uncertainty(state, stages)
    proposed = len(stages.get("capa", {}).get("actions", []))
    if inc.status != IncidentStatus.PENDING_APPROVAL:
        lifecycle.transition(
            db,
            inc,
            IncidentStatus.PENDING_APPROVAL,
            actor_id=user_id,
            actor_type="AGENT",
            note=f"AI investigation finished; {proposed} action(s) awaiting human review",
        )
    return {"status": "SUCCEEDED", "conflicts": [r.id for r in rows], "finished_at": utcnow().isoformat()}


def investigation_result(db: Session, wf: WorkflowRun) -> dict:
    runs = list(db.scalars(select(AgentRun).where(AgentRun.workflow_id == wf.id).order_by(AgentRun.started_at)))
    stages = wf.stages or {}
    assessment_id = stages.get("risk", {}).get("assessment_id")
    action_ids = stages.get("capa", {}).get("actions", [])
    found = list(
        db.scalars(select(AgentConflict).where(AgentConflict.workflow_id == wf.id).order_by(AgentConflict.created_at))
    )
    return {
        "workflow": wf,
        "workflow_id": wf.id,
        "runs": runs,
        "risk": db.get(RiskAssessment, assessment_id) if assessment_id else None,
        "capa": [a for a in (db.get(CapaAction, i) for i in action_ids) if a is not None],
        "conflicts": found,
        "flags": [c.summary for c in found],
    }


def run_investigation(
    db: Session,
    inc: Incident,
    user_id: str,
    provider: Provider | None = None,
    *,
    pause_after=(),
    checkpoint: Checkpoint | None = None,
) -> dict:
    wf = start_investigation(db, inc, user_id, provider, pause_after=pause_after, checkpoint=checkpoint)
    return investigation_result(db, wf)
