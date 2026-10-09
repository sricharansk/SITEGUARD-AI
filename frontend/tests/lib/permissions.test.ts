// UI permission gating mirrors the API's rules. It only decides what to show; the API enforces them again.
import { describe, expect, it } from "vitest";
import {
  can,
  canCloseIncident,
  canReviewAction,
  canRunInvestigation,
  canUpdateProgress,
  canVerify,
  manualTransitionTargets,
  meCan,
  reviewPermissionFor,
} from "@/lib/permissions";
import type { Me, Permission } from "@/lib/types";
import { makeAction } from "../fixtures";

const AUDITOR: Permission[] = ["READ", "VIEW_AUDIT"];
const HSE: Permission[] = [
  "READ",
  "CREATE_INCIDENT",
  "EDIT_INCIDENT",
  "RUN_AGENTS",
  "PROPOSE_CAPA",
  "APPROVE_CAPA",
  "APPROVE_CRITICAL",
  "UPDATE_CAPA_PROGRESS",
  "VERIFY_CAPA",
  "CLOSE_INCIDENT",
  "VIEW_AUDIT",
];
const PROJECT_MANAGER: Permission[] = ["READ", "EDIT_INCIDENT", "APPROVE_CAPA", "CLOSE_INCIDENT", "UPDATE_CAPA_PROGRESS"];

describe("can / meCan", () => {
  it("is false for missing permission lists", () => {
    expect(can(undefined, "READ")).toBe(false);
    expect(can(null, "READ")).toBe(false);
    expect(can([], "READ")).toBe(false);
    expect(can(AUDITOR, "VIEW_AUDIT")).toBe(true);
  });

  it("meCan checks every membership", () => {
    const me: Me = {
      id: "u",
      email: "a@b.c",
      full_name: "A",
      memberships: [
        { organization_id: "o", organization: "Org", project_id: "p1", role: "VIEWER", permissions: ["READ"] },
        { organization_id: "o", organization: "Org", project_id: null, role: "AUDITOR", permissions: AUDITOR },
      ],
    };
    expect(meCan(me, "VIEW_AUDIT")).toBe(true);
    expect(meCan(me, "APPROVE_CAPA")).toBe(false);
    expect(meCan(undefined, "READ")).toBe(false);
  });
});

describe("CAPA review gating", () => {
  it("critical actions need APPROVE_CRITICAL, others APPROVE_CAPA", () => {
    expect(reviewPermissionFor({ critical: true })).toBe("APPROVE_CRITICAL");
    expect(reviewPermissionFor({ critical: false })).toBe("APPROVE_CAPA");
  });

  it("only pending actions can be reviewed, and only with the right permission", () => {
    const pending = makeAction();
    const critical = makeAction({ critical: true });
    expect(canReviewAction(PROJECT_MANAGER, pending)).toBe(true);
    expect(canReviewAction(PROJECT_MANAGER, critical)).toBe(false);
    expect(canReviewAction(HSE, critical)).toBe(true);
    expect(canReviewAction(AUDITOR, pending)).toBe(false);
    expect(canReviewAction(HSE, makeAction({ approval_status: "APPROVED" }))).toBe(false);
  });

  it("progress updates need an approved action in a workable state", () => {
    expect(canUpdateProgress(HSE, makeAction())).toBe(false);
    expect(canUpdateProgress(HSE, makeAction({ approval_status: "APPROVED" }))).toBe(true);
    expect(canUpdateProgress(HSE, makeAction({ approval_status: "MODIFIED", work_status: "VERIFICATION_FAILED" }))).toBe(true);
    expect(canUpdateProgress(HSE, makeAction({ approval_status: "APPROVED", work_status: "COMPLETED" }))).toBe(false);
    expect(canUpdateProgress(AUDITOR, makeAction({ approval_status: "APPROVED" }))).toBe(false);
  });

  it("verification needs a completed action and VERIFY_CAPA", () => {
    expect(canVerify(HSE, makeAction({ approval_status: "APPROVED", work_status: "COMPLETED" }))).toBe(true);
    expect(canVerify(PROJECT_MANAGER, makeAction({ approval_status: "APPROVED", work_status: "COMPLETED" }))).toBe(false);
    expect(canVerify(HSE, makeAction({ approval_status: "APPROVED", work_status: "IN_PROGRESS" }))).toBe(false);
  });
});

describe("incident workflow gating", () => {
  it("closing a CRITICAL incident also needs APPROVE_CRITICAL", () => {
    expect(canCloseIncident(PROJECT_MANAGER, { severity: "HIGH" })).toBe(true);
    expect(canCloseIncident(PROJECT_MANAGER, { severity: "CRITICAL" })).toBe(false);
    expect(canCloseIncident(HSE, { severity: "CRITICAL" })).toBe(true);
    expect(canCloseIncident(AUDITOR, { severity: "LOW" })).toBe(false);
  });

  it("manual transitions follow the lifecycle and never include CLOSED", () => {
    expect(manualTransitionTargets(HSE, "REPORTED")).toEqual(["TRIAGED", "UNDER_INVESTIGATION"]);
    expect(manualTransitionTargets(HSE, "PENDING_VERIFICATION")).toEqual(["ACTION_IN_PROGRESS"]);
    for (const status of ["REPORTED", "PENDING_APPROVAL", "ACTION_IN_PROGRESS", "PENDING_VERIFICATION"] as const) {
      expect(manualTransitionTargets(HSE, status)).not.toContain("CLOSED");
    }
    expect(manualTransitionTargets(AUDITOR, "REPORTED")).toEqual([]);
  });

  it("reopening a closed incident needs CLOSE_INCIDENT", () => {
    expect(manualTransitionTargets(HSE, "CLOSED")).toEqual(["UNDER_INVESTIGATION"]);
    expect(manualTransitionTargets(["READ", "EDIT_INCIDENT"], "CLOSED")).toEqual([]);
  });

  it("the AI investigation runs only with RUN_AGENTS from an open, pre-action status", () => {
    expect(canRunInvestigation(HSE, "REPORTED")).toBe(true);
    expect(canRunInvestigation(HSE, "PENDING_APPROVAL")).toBe(true);
    expect(canRunInvestigation(HSE, "ACTION_IN_PROGRESS")).toBe(false);
    expect(canRunInvestigation(HSE, "CLOSED")).toBe(false);
    expect(canRunInvestigation(AUDITOR, "REPORTED")).toBe(false);
  });
});
