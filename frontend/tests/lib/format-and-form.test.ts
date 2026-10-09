// Display helpers and the new-incident form checks (which mirror IncidentIn; the API validates again).
import { describe, expect, it } from "vitest";
import { formatDate, humanize, isOverdue, parseTimestamp, roleLabel } from "@/lib/format";
import { toIncidentBody, validateIncident, type IncidentForm } from "@/lib/incident-form";

describe("format helpers", () => {
  it("reads a timestamp without an offset as UTC", () => {
    expect(parseTimestamp("2026-10-09T08:00:00")?.toISOString()).toBe("2026-10-09T08:00:00.000Z");
    expect(parseTimestamp("2026-10-09T08:00:00+02:00")?.toISOString()).toBe("2026-10-09T06:00:00.000Z");
    expect(parseTimestamp("nonsense")).toBeNull();
  });

  it("formats calendar dates without shifting the day", () => {
    expect(formatDate("2026-01-31")).toBe("31 Jan 2026");
    expect(formatDate(null)).toBe("—");
  });

  it("detects overdue due dates against today", () => {
    const today = new Date(2026, 9, 9);
    expect(isOverdue("2026-10-08", today)).toBe(true);
    expect(isOverdue("2026-10-09", today)).toBe(false);
    expect(isOverdue(null, today)).toBe(false);
  });

  it("humanizes enums and roles", () => {
    expect(humanize("PENDING_APPROVAL")).toBe("Pending approval");
    expect(roleLabel("HSE_MANAGER")).toBe("HSE manager");
    expect(roleLabel("QA_QC_ENGINEER")).toBe("QA/QC engineer");
    expect(roleLabel("SOMETHING_NEW")).toBe("Something new");
  });
});

const valid: IncidentForm = {
  title: "Guardrail removed",
  description: "Guardrail at the slab edge removed for crane access.",
  domain: "SAFETY",
  severity: "HIGH",
  occurred_at: "2026-10-09T08:30",
  site_id: "",
  category: "",
  location: " Level 9 ",
  activity: "",
  people_involved: "1",
  immediate_actions: "",
};

describe("validateIncident", () => {
  const now = new Date("2026-10-09T12:00:00").getTime();

  it("accepts a complete report", () => {
    expect(validateIncident(valid, now)).toEqual({});
  });

  it("flags short text, a future time and a bad head count", () => {
    const errors = validateIncident(
      { ...valid, title: "ab", description: "short", occurred_at: "2026-10-10T08:00", people_involved: "-1" },
      now,
    );
    expect(Object.keys(errors).sort()).toEqual(["description", "occurred_at", "people_involved", "title"]);
  });

  it("builds the request body with nulls for empty optional fields", () => {
    const body = toIncidentBody(valid);
    expect(body.location).toBe("Level 9");
    expect(body.category).toBeNull();
    expect(body.site_id).toBeNull();
    expect(body.people_involved).toBe(1);
    expect(body.occurred_at).toMatch(/Z$/);
  });
});
