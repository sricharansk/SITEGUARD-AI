// Dashboard filters: presets, range validation (mirrors the API's rules), the query sent to GET /dashboard and the
// duration and period formats.
import { describe, expect, it } from "vitest";
import {
  DEFAULT_FILTERS,
  dashboardQuery,
  formatDays,
  formatHours,
  isValidDay,
  periodLabel,
  presetRange,
  validateFilters,
} from "@/lib/dashboard";

const TODAY = new Date("2026-10-09T15:30:00Z");

describe("presetRange", () => {
  it("ends every preset today (UTC) and counts today as a day", () => {
    expect(presetRange("30d", TODAY)).toEqual({ from: "2026-09-10", to: "2026-10-09" });
    expect(presetRange("90d", TODAY)).toEqual({ from: "2026-07-12", to: "2026-10-09" });
    expect(presetRange("12m", TODAY)).toEqual({ from: "2025-10-10", to: "2026-10-09" });
  });

  it("clears the range for all dates and leaves a custom range alone", () => {
    expect(presetRange("all", TODAY)).toEqual({ from: "", to: "" });
    expect(presetRange("custom", TODAY)).toBeNull();
  });
});

describe("validateFilters", () => {
  it("accepts open, one-sided and ordered ranges", () => {
    expect(validateFilters({ from: "", to: "" })).toBeNull();
    expect(validateFilters({ from: "2026-01-01", to: "" })).toBeNull();
    expect(validateFilters({ from: "2026-01-01", to: "2026-01-01" })).toBeNull();
  });

  it("rejects an inverted range, impossible dates and dates outside the API's bounds", () => {
    expect(validateFilters({ from: "2026-05-01", to: "2026-04-30" })).toBe("From must be on or before To.");
    expect(validateFilters({ from: "2026-02-30", to: "" })).toMatch(/From is not a valid date/);
    expect(validateFilters({ from: "", to: "09/10/2026" })).toMatch(/To is not a valid date/);
    expect(validateFilters({ from: "1900-01-01", to: "" })).toMatch(/between 1970-01-01 and 2999-12-31/);
    expect(isValidDay("2028-02-29")).toBe(true);
    expect(isValidDay("2026-02-29")).toBe(false);
  });
});

describe("dashboardQuery", () => {
  it("sends the project only for the project scope, and only the bounds that are set", () => {
    expect(dashboardQuery(DEFAULT_FILTERS, "p1")).toEqual({
      project_id: "p1",
      date_from: undefined,
      date_to: undefined,
      interval: "month",
    });
    expect(dashboardQuery({ ...DEFAULT_FILTERS, scope: "all", from: "2026-09-01", interval: "week" }, "p1")).toEqual({
      project_id: undefined,
      date_from: "2026-09-01",
      date_to: undefined,
      interval: "week",
    });
  });
});

describe("formats", () => {
  it("shows response times in minutes, hours or days", () => {
    expect(formatHours(null)).toBe("—");
    expect(formatHours(0.25)).toBe("15 min");
    expect(formatHours(6)).toBe("6.0 h");
    expect(formatHours(60)).toBe("2.5 days");
    expect(formatDays(1)).toBe("1.0 day");
    expect(formatDays(7.25)).toBe("7.3 days");
    expect(formatDays(undefined)).toBe("—");
  });

  it("labels months and ISO weeks", () => {
    expect(periodLabel("2026-10")).toBe("Oct 2026");
    expect(periodLabel("2026-10", true)).toBe("Oct 26");
    expect(periodLabel("2026-W09")).toBe("Week 9, 2026");
    expect(periodLabel("2026-W09", true)).toBe("W09");
    expect(periodLabel("2026-09")).toBe("Sep 2026");
    expect(periodLabel("2026-13")).toBe("2026-13");
    expect(periodLabel("unexpected")).toBe("unexpected");
  });
});
