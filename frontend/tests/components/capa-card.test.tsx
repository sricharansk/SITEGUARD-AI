// Permission gating on a CAPA action: review, progress and verification controls appear only for roles the API
// would allow, and the review decision always carries a reason.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CapaActionCard } from "@/components/incident/capa";
import { peopleIndex } from "@/components/incident/people";
import type { CapaAction, Permission } from "@/lib/types";
import { ASSIGNEE_ID, MEMBERS, envelopeResponse, errorEnvelopeResponse, makeAction } from "../fixtures";

function renderCard(action: CapaAction, permissions: Permission[], meId = "me-1") {
  const onChanged = vi.fn();
  render(
    <CapaActionCard
      action={action}
      permissions={permissions}
      meId={meId}
      members={MEMBERS}
      people={peopleIndex(MEMBERS)}
      onChanged={onChanged}
    />,
  );
  return { onChanged, card: screen.getByTestId("capa-action") };
}

describe("CapaActionCard review gating", () => {
  it("shows the review form to a role with APPROVE_CAPA for a non-critical action", () => {
    const { card } = renderCard(makeAction(), ["READ", "APPROVE_CAPA"]);
    expect(within(card).getByRole("button", { name: "Approve" })).toBeVisible();
    expect(within(card).getByRole("button", { name: "Reject" })).toBeVisible();
    expect(within(card).getByText("AI decision support, needs human review before any work starts.")).toBeVisible();
  });

  it("hides every review control from a read-only role", () => {
    const { card } = renderCard(makeAction(), ["READ", "VIEW_AUDIT"]);
    expect(within(card).queryByRole("button")).toBeNull();
    expect(within(card).getByText(/Awaiting review by someone with CAPA approval rights/)).toBeVisible();
  });

  it("keeps critical actions for APPROVE_CRITICAL holders", () => {
    renderCard(makeAction({ critical: true }), ["READ", "APPROVE_CAPA"]);
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
    expect(screen.getByText(/HSE manager \(critical\) approval rights/)).toBeVisible();
  });

  it("lets an HSE manager review a critical action", () => {
    renderCard(makeAction({ critical: true }), ["READ", "APPROVE_CAPA", "APPROVE_CRITICAL"]);
    expect(screen.getByRole("button", { name: "Approve" })).toBeVisible();
  });

  it("requires a reason before sending a decision", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderCard(makeAction(), ["APPROVE_CAPA"]);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(screen.getByRole("alert")).toHaveTextContent("A reason is required for every review decision.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends the decision with its reason and reports success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(envelopeResponse({ id: "capa-1" }));
    vi.stubGlobal("fetch", fetchMock);
    const { onChanged } = renderCard(makeAction(), ["APPROVE_CAPA"]);
    fireEvent.change(screen.getByLabelText("Review reason (required)"), { target: { value: "  Control fits the hazard. " } });
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("“Reinstate edge protection” approved."));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/backend/capa/capa-1/review");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ decision: "APPROVE", reason: "Control fits the hazard." });
  });

  it("shows the API's refusal with its correlation ID instead of hiding it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(errorEnvelopeResponse(403, "FORBIDDEN", "Critical actions need an HSE manager.", "cid-forbid-1")));
    const { onChanged } = renderCard(makeAction(), ["APPROVE_CAPA"]);
    fireEvent.change(screen.getByLabelText("Review reason (required)"), { target: { value: "ok" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Not authorized: Critical actions need an HSE manager.");
    expect(alert).toHaveTextContent("cid-forbid-1");
    expect(onChanged).not.toHaveBeenCalled();
  });
});

describe("CapaActionCard progress and verification gating", () => {
  it("offers progress controls only with UPDATE_CAPA_PROGRESS on an approved action", () => {
    const approved = makeAction({ approval_status: "APPROVED" });
    renderCard(approved, ["UPDATE_CAPA_PROGRESS"]);
    expect(screen.getByRole("button", { name: "Start work" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Mark complete" })).toBeVisible();
  });

  it("shows no progress controls without the permission", () => {
    renderCard(makeAction({ approval_status: "APPROVED" }), ["READ"]);
    expect(screen.queryByRole("button", { name: "Start work" })).toBeNull();
  });

  it("offers verification for a completed action with VERIFY_CAPA", () => {
    renderCard(makeAction({ approval_status: "APPROVED", work_status: "COMPLETED", assignee_id: ASSIGNEE_ID }), ["VERIFY_CAPA"]);
    expect(screen.getByRole("button", { name: "Record verification" })).toBeVisible();
  });

  it("tells the assignee that someone else must verify", () => {
    renderCard(
      makeAction({ approval_status: "APPROVED", work_status: "COMPLETED", assignee_id: ASSIGNEE_ID }),
      ["VERIFY_CAPA"],
      ASSIGNEE_ID,
    );
    expect(screen.getByText(/someone else must verify this action/)).toBeVisible();
  });
});
