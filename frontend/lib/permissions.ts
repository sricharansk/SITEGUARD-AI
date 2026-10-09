// UI permission gating. These checks only decide what to show: the API enforces every permission again and
// remains the authority (a 403 from the API is rendered as an "unauthorized" state).
import type { CapaAction, Incident, IncidentStatus, Me, Permission, WorkStatus } from "./types";

export type PermissionList = readonly Permission[] | undefined | null;

export function can(permissions: PermissionList, permission: Permission): boolean {
  return Boolean(permissions?.includes(permission));
}

/** Any membership grants the permission (used for organization-level screens such as the audit log). */
export function meCan(me: Me | undefined | null, permission: Permission): boolean {
  return Boolean(me?.memberships.some((m) => m.permissions.includes(permission)));
}

/** Critical actions (HIGH/CRITICAL risk) need APPROVE_CRITICAL; others APPROVE_CAPA. */
export function reviewPermissionFor(action: Pick<CapaAction, "critical">): Permission {
  return action.critical ? "APPROVE_CRITICAL" : "APPROVE_CAPA";
}

export function canReviewAction(permissions: PermissionList, action: Pick<CapaAction, "critical" | "approval_status">) {
  return action.approval_status === "PENDING_REVIEW" && can(permissions, reviewPermissionFor(action));
}

const WORKABLE: readonly WorkStatus[] = ["NOT_STARTED", "IN_PROGRESS", "VERIFICATION_FAILED"];

export function isActiveAction(action: Pick<CapaAction, "approval_status">): boolean {
  return action.approval_status === "APPROVED" || action.approval_status === "MODIFIED";
}

export function canUpdateProgress(permissions: PermissionList, action: Pick<CapaAction, "approval_status" | "work_status">) {
  return isActiveAction(action) && WORKABLE.includes(action.work_status) && can(permissions, "UPDATE_CAPA_PROGRESS");
}

export function canVerify(permissions: PermissionList, action: Pick<CapaAction, "work_status">): boolean {
  return action.work_status === "COMPLETED" && can(permissions, "VERIFY_CAPA");
}

/** Closing needs CLOSE_INCIDENT, and APPROVE_CRITICAL as well for CRITICAL incidents. */
export function canCloseIncident(permissions: PermissionList, incident: Pick<Incident, "severity">): boolean {
  if (!can(permissions, "CLOSE_INCIDENT")) return false;
  return incident.severity !== "CRITICAL" || can(permissions, "APPROVE_CRITICAL");
}

// Mirror of backend/app/services/lifecycle.py TRANSITIONS, without CLOSED (closing has its own checks).
const MANUAL_TRANSITIONS: Record<IncidentStatus, IncidentStatus[]> = {
  REPORTED: ["TRIAGED", "UNDER_INVESTIGATION"],
  TRIAGED: ["UNDER_INVESTIGATION"],
  UNDER_INVESTIGATION: ["PENDING_APPROVAL"],
  PENDING_APPROVAL: ["ACTION_IN_PROGRESS", "UNDER_INVESTIGATION"],
  ACTION_IN_PROGRESS: ["PENDING_VERIFICATION", "UNDER_INVESTIGATION"],
  PENDING_VERIFICATION: ["ACTION_IN_PROGRESS"],
  CLOSED: ["UNDER_INVESTIGATION"],
};

/** Statuses the user may move the incident to by hand. Reopening a closed incident needs CLOSE_INCIDENT. */
export function manualTransitionTargets(permissions: PermissionList, status: IncidentStatus): IncidentStatus[] {
  if (!can(permissions, "EDIT_INCIDENT")) return [];
  if (status === "CLOSED" && !can(permissions, "CLOSE_INCIDENT")) return [];
  return MANUAL_TRANSITIONS[status] ?? [];
}

// backend/app/agents/orchestrator.py RUNNABLE_FROM
const AGENT_RUNNABLE: readonly IncidentStatus[] = ["REPORTED", "TRIAGED", "UNDER_INVESTIGATION", "PENDING_APPROVAL"];

export function canRunInvestigation(permissions: PermissionList, status: IncidentStatus): boolean {
  return can(permissions, "RUN_AGENTS") && AGENT_RUNNABLE.includes(status);
}

export function agentsRunnableFrom(status: IncidentStatus): boolean {
  return AGENT_RUNNABLE.includes(status);
}
