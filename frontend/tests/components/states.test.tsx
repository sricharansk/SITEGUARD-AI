// Error states show the API's message and correlation ID; a 403 becomes the unauthorized state.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorState, PartialNotice } from "@/components/states";
import { ApiError } from "@/lib/api";

describe("ErrorState", () => {
  it("renders 403 as the unauthorized state", () => {
    const error = new ApiError(403, { code: "FORBIDDEN", message: "Role cannot view audit.", correlation_id: "cid-403-abc" });
    const { container } = render(<ErrorState error={error} what="the audit log" />);
    expect(screen.getByText("Not authorized")).toBeVisible();
    expect(screen.getByText(/Server message: Role cannot view audit./)).toBeVisible();
    expect(screen.getByText("cid-403-abc")).toBeVisible();
    expect(container.querySelector('[data-state="unauthorized"]')).not.toBeNull();
  });

  it("shows message, code and correlation ID, with a retry", () => {
    const onRetry = vi.fn();
    const error = new ApiError(500, { code: "INTERNAL_ERROR", message: "Unexpected error.", correlation_id: "cid-500-xyz" });
    render(<ErrorState error={error} onRetry={onRetry} />);
    expect(screen.getByText("Something went wrong")).toBeVisible();
    expect(screen.getByText("Unexpected error.")).toBeVisible();
    expect(screen.getByText("Code: INTERNAL_ERROR")).toBeVisible();
    expect(screen.getByText("cid-500-xyz")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("explains a 404 without offering a pointless retry", () => {
    const error = new ApiError(404, { code: "NOT_FOUND", message: "Incident not found.", correlation_id: null });
    render(<ErrorState error={error} onRetry={() => undefined} />);
    expect(screen.getByText("Not found")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });
});

describe("PartialNotice", () => {
  it("lists what is missing and renders nothing when complete", () => {
    const { container, rerender } = render(<PartialNotice items={["Risk matrix unavailable."]} />);
    expect(screen.getByText("Partial result")).toBeVisible();
    expect(screen.getByText("Risk matrix unavailable.")).toBeVisible();
    rerender(<PartialNotice items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
