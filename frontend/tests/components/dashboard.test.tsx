// Dashboard filters are staged and applied together, an invalid range never reaches the API, and the trend charts
// show periods without data as "—" rather than as zero.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DashboardFilterBar } from "@/components/dashboard/filter-bar";
import { TrendCharts } from "@/components/dashboard/trends";
import { DEFAULT_FILTERS } from "@/lib/dashboard";
import type { TrendBucket } from "@/lib/types";

const PROJECT = { code: "TWR-A", name: "Tower A" };

function bucket(period: string, overrides: Partial<TrendBucket> = {}): TrendBucket {
  return {
    period,
    start: `${period}-01`,
    end: `${period}-28`,
    incidents: 0,
    closed: 0,
    open: 0,
    responded: 0,
    median_response_hours: null,
    mean_response_hours: null,
    median_days_to_close: null,
    mean_days_to_close: null,
    ...overrides,
  };
}

describe("DashboardFilterBar", () => {
  it("refuses an inverted range without applying it", () => {
    const onApply = vi.fn();
    render(<DashboardFilterBar value={DEFAULT_FILTERS} project={PROJECT} projectCount={1} onApply={onApply} />);
    const form = screen.getByRole("form", { name: "Dashboard filters" });
    fireEvent.change(within(form).getByLabelText("From"), { target: { value: "2026-05-01" } });
    fireEvent.change(within(form).getByLabelText("To"), { target: { value: "2026-04-30" } });
    fireEvent.click(within(form).getByRole("button", { name: "Apply filters" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("From must be on or before To.");
    expect(within(form).getByLabelText("From")).toHaveAttribute("aria-invalid", "true");
    expect(onApply).not.toHaveBeenCalled();
  });

  it("applies a custom range, interval and scope together", () => {
    const onApply = vi.fn();
    render(<DashboardFilterBar value={DEFAULT_FILTERS} project={PROJECT} projectCount={3} onApply={onApply} />);
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-01-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-03-31" } });
    fireEvent.change(screen.getByLabelText("Trend by"), { target: { value: "week" } });
    fireEvent.change(screen.getByLabelText("Projects"), { target: { value: "all" } });
    expect(screen.getByLabelText("Period (date occurred, UTC)")).toHaveValue("custom");
    expect(onApply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(onApply).toHaveBeenCalledWith({ scope: "all", preset: "custom", from: "2026-01-01", to: "2026-03-31", interval: "week" });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers the all-projects scope only to users with more than one project", () => {
    render(<DashboardFilterBar value={DEFAULT_FILTERS} project={PROJECT} projectCount={1} onApply={vi.fn()} />);
    expect(screen.queryByLabelText("Projects")).toBeNull();
  });

  it("fills the range from a preset", () => {
    render(<DashboardFilterBar value={DEFAULT_FILTERS} project={PROJECT} projectCount={1} onApply={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Period (date occurred, UTC)"), { target: { value: "30d" } });
    expect(screen.getByLabelText("From")).not.toHaveValue("");
    expect(screen.getByLabelText("To")).not.toHaveValue("");
  });
});

describe("TrendCharts", () => {
  it("draws periods without data as a dash and lists the exact values in a table", () => {
    render(
      <TrendCharts
        trends={{
          interval: "month",
          truncated: false,
          buckets: [
            bucket("2026-08", { incidents: 2, closed: 1, open: 1, responded: 2, median_response_hours: 6, mean_days_to_close: 3 }),
            bucket("2026-09"),
          ],
        }}
      />,
    );
    expect(screen.getByText("Incidents per month")).toBeVisible();
    const table = screen.getByRole("table", { name: "Response and closure by month of occurrence" });
    const september = within(table).getByRole("row", { name: /Sep 2026/ });
    expect(within(september).getAllByText("—")).toHaveLength(3);
    const august = within(table).getByRole("row", { name: /Aug 2026/ });
    expect(august).toHaveTextContent("6.0 h");
    expect(august).toHaveTextContent("3.0 days");
    expect(screen.getByRole("table", { name: "Median hours from report to first response, per month" })).toHaveTextContent("No data");
  });

  it("says so when the period has no incidents", () => {
    render(<TrendCharts trends={{ interval: "week", truncated: false, buckets: [] }} />);
    expect(screen.getByText("No incidents in this period, so there is no trend to show.")).toBeVisible();
  });
});
