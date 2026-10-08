"""Human approval, CAPA workflow, verification and incident closure (docs/AGENTS.md#human-approval)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, Forbidden
from app.core.security import Permission, Principal
from app.models import (
    ApprovalEvent,
    ApprovalStatus,
    CapaAction,
    Incident,
    IncidentStatus,
    Severity,
    VerificationRecord,
    WorkStatus,
)
from app.services import audit, lifecycle

ACTIVE = (ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED)
EDITABLE_FIELDS = (
    "title",
    "description",
    "owner_role",
    "assignee_id",
    "due_date",
    "verification_criteria",
    "action_type",
)


def snapshot(a: CapaAction) -> dict:
    return {
        "title": a.title,
        "description": a.description,
        "action_type": a.action_type,
        "owner_role": a.owner_role,
        "assignee_id": a.assignee_id,
        "due_date": a.due_date.isoformat() if a.due_date else None,
        "verification_criteria": a.verification_criteria,
        "approval_status": a.approval_status.value,
        "work_status": a.work_status.value,
    }


def review(
    db: Session,
    p: Principal,
    inc: Incident,
    action: CapaAction,
    decision: str,
    reason: str,
    changes: dict | None,
) -> CapaAction:
    if action.approval_status != ApprovalStatus.PENDING_REVIEW:
        raise Conflict(f"Action is {action.approval_status.value}, not PENDING_REVIEW", "INVALID_STATE")
    perm = Permission.APPROVE_CRITICAL if action.critical else Permission.APPROVE_CAPA
    p.require(perm, inc.organization_id, inc.project_id)
    if not reason.strip():
        raise AppError("A reason is required for every review decision")
    before = snapshot(action)
    if decision == "APPROVE":
        if changes:
            raise AppError("Use MODIFY to change an action")
        action.approval_status = ApprovalStatus.APPROVED
    elif decision == "MODIFY":
        if not changes:
            raise AppError("MODIFY needs at least one change")
        for key, value in changes.items():
            if key not in EDITABLE_FIELDS:
                raise AppError(f"Field '{key}' cannot be modified")
            if key == "due_date" and isinstance(value, str):
                value = date.fromisoformat(value)
            setattr(action, key, value)
        action.approval_status = ApprovalStatus.MODIFIED
    elif decision == "REJECT":
        action.approval_status = ApprovalStatus.REJECTED
    else:
        raise AppError("decision must be APPROVE, MODIFY or REJECT")
    after = snapshot(action)
    db.add(
        ApprovalEvent(capa_id=action.id, reviewer_id=p.id, decision=decision, reason=reason, before=before, after=after)
    )
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=p.id,
        action=f"capa.{decision.lower()}",
        entity_type="capa",
        entity_id=action.id,
        details={
            "incident_id": inc.id,
            "reason": reason,
            "ai_generated": action.ai_generated,
            "critical": action.critical,
        },
    )
    db.flush()
    _sync_incident(db, inc, p.id)
    return action


def update_progress(
    db: Session,
    p: Principal,
    inc: Incident,
    action: CapaAction,
    work_status: WorkStatus | None,
    assignee_id: str | None,
    note: str | None,
) -> CapaAction:
    p.require(Permission.UPDATE_CAPA_PROGRESS, inc.organization_id, inc.project_id)
    if action.approval_status not in ACTIVE:
        raise Conflict("Only approved actions can be worked on", "NOT_APPROVED")
    allowed = {
        WorkStatus.NOT_STARTED: {WorkStatus.IN_PROGRESS, WorkStatus.COMPLETED},
        WorkStatus.IN_PROGRESS: {WorkStatus.COMPLETED},
        WorkStatus.VERIFICATION_FAILED: {WorkStatus.IN_PROGRESS, WorkStatus.COMPLETED},
    }
    before = action.work_status
    if work_status and work_status != before:
        if work_status not in allowed.get(before, set()):
            raise Conflict(f"Invalid work status change {before.value} -> {work_status.value}", "INVALID_TRANSITION")
        action.work_status = work_status
    if assignee_id is not None:
        action.assignee_id = assignee_id
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=p.id,
        action="capa.progress",
        entity_type="capa",
        entity_id=action.id,
        details={
            "from": before.value,
            "to": action.work_status.value,
            "note": note,
            "assignee_id": action.assignee_id,
        },
    )
    db.flush()
    _sync_incident(db, inc, p.id)
    return action


def verify(
    db: Session,
    p: Principal,
    inc: Incident,
    action: CapaAction,
    effective: bool,
    notes: str,
    evidence_id: str | None,
) -> VerificationRecord:
    p.require(Permission.VERIFY_CAPA, inc.organization_id, inc.project_id)
    if action.work_status != WorkStatus.COMPLETED:
        raise Conflict("Only completed actions can be verified", "INVALID_STATE")
    if action.assignee_id and action.assignee_id == p.id:
        raise Forbidden("The person who did the action cannot verify it")
    if not notes.strip():
        raise AppError("Verification notes are required")
    rec = VerificationRecord(
        capa_id=action.id, verifier_id=p.id, effective=effective, notes=notes, evidence_id=evidence_id
    )
    db.add(rec)
    action.work_status = WorkStatus.VERIFIED if effective else WorkStatus.VERIFICATION_FAILED
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=p.id,
        action="capa.verify",
        entity_type="capa",
        entity_id=action.id,
        details={"effective": effective, "notes": notes, "evidence_id": evidence_id},
    )
    db.flush()
    _sync_incident(db, inc, p.id)
    return rec


def _actions(db: Session, inc: Incident) -> list[CapaAction]:
    return list(db.scalars(select(CapaAction).where(CapaAction.incident_id == inc.id)))


def _sync_incident(db: Session, inc: Incident, actor_id: str) -> None:
    """Move the incident forward when its actions allow it. Never closes it."""
    actions = _actions(db, inc)
    active = [a for a in actions if a.approval_status in ACTIVE]
    pending = [a for a in actions if a.approval_status == ApprovalStatus.PENDING_REVIEW]
    status = inc.status
    if status == IncidentStatus.PENDING_APPROVAL and active and not pending:
        lifecycle.transition(
            db,
            inc,
            IncidentStatus.ACTION_IN_PROGRESS,
            actor_id=actor_id,
            note="All proposed actions reviewed",
        )
        status = inc.status
    if (
        status == IncidentStatus.ACTION_IN_PROGRESS
        and active
        and all(a.work_status in (WorkStatus.COMPLETED, WorkStatus.VERIFIED) for a in active)
    ):
        lifecycle.transition(
            db,
            inc,
            IncidentStatus.PENDING_VERIFICATION,
            actor_id=actor_id,
            note="All approved actions completed",
        )
    elif status == IncidentStatus.PENDING_VERIFICATION and any(
        a.work_status in (WorkStatus.VERIFICATION_FAILED, WorkStatus.IN_PROGRESS) for a in active
    ):
        lifecycle.transition(
            db,
            inc,
            IncidentStatus.ACTION_IN_PROGRESS,
            actor_id=actor_id,
            note="An action failed verification",
        )


def close_blockers(db: Session, inc: Incident) -> list[str]:
    blockers: list[str] = []
    if inc.status != IncidentStatus.PENDING_VERIFICATION:
        blockers.append(f"Incident is {inc.status.value}; it must be PENDING_VERIFICATION.")
    actions = _actions(db, inc)
    active = [a for a in actions if a.approval_status in ACTIVE]
    if not active:
        blockers.append("At least one approved corrective or preventive action is required.")
    if any(a.approval_status == ApprovalStatus.PENDING_REVIEW for a in actions):
        blockers.append("Some proposed actions are still awaiting review.")
    unverified = [a.title for a in active if a.work_status != WorkStatus.VERIFIED]
    if unverified:
        blockers.append(f"{len(unverified)} approved action(s) not verified effective.")
    return blockers


def close_incident(db: Session, p: Principal, inc: Incident, note: str) -> Incident:
    p.require(Permission.CLOSE_INCIDENT, inc.organization_id, inc.project_id)
    if inc.severity == Severity.CRITICAL:
        p.require(Permission.APPROVE_CRITICAL, inc.organization_id, inc.project_id)
    blockers = close_blockers(db, inc)
    if blockers:
        raise Conflict("Incident cannot be closed: " + " ".join(blockers), "CLOSE_BLOCKED")
    if not note.strip():
        raise AppError("A closure note is required")
    lifecycle.transition(db, inc, IncidentStatus.CLOSED, actor_id=p.id, note=note)
    return inc
