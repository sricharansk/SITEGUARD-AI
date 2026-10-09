// AI output is always labelled as decision support that needs human review, with provider, confidence, open
// questions, review flags and the evidence it cites.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AI_LABEL, AiPanel } from "@/components/ai/ai-panel";
import { buildRefIndex } from "@/components/ai/refs";
import { EVIDENCE, EVIDENCE_ID, INCIDENT_ID, makeRun } from "../fixtures";

const refIndex = buildRefIndex({ id: INCIDENT_ID, reference: "SG-2026-0001" }, [EVIDENCE], []);

function panel(name: string) {
  return screen.getByRole("region", { name });
}

describe("AiPanel", () => {
  it("labels the output as AI decision support that needs human review", () => {
    render(<AiPanel run={makeRun()} refIndex={refIndex} />);
    const region = panel("AI output: Triage");
    expect(region).toHaveAttribute("data-kind", "ai");
    expect(within(region).getByText(AI_LABEL)).toBeVisible();
    expect(AI_LABEL).toBe("AI decision support, needs human review");
    expect(within(region).getByText("Provider: rules")).toBeVisible();
    expect(within(region).getByText("Confidence 80%")).toBeVisible();
  });

  it("shows the agent's findings, open questions and cited evidence", () => {
    render(<AiPanel run={makeRun()} refIndex={refIndex} />);
    const region = panel("AI output: Triage");
    expect(within(region).getByText("Fall from height")).toBeVisible();
    expect(within(region).getByText("Who removed the guardrail?")).toBeVisible();
    expect(within(region).getByText("Incident report SG-2026-0001")).toBeVisible();
    const evidenceLink = within(region).getByRole("link", { name: "Evidence: supervisor-note.txt" });
    expect(evidenceLink).toHaveAttribute("href", `/api/backend/evidence/${EVIDENCE_ID}/download`);
  });

  it("makes a fallback provider and low confidence stand out", () => {
    const run = makeRun({
      provider: "rules (fallback from anthropic)",
      output: { ...makeRun().output, confidence: 0.42 },
      needs_human_review: true,
      trace: [{ type: "review_reasons", reasons: ["Low confidence (0.42)."] }],
    });
    render(<AiPanel run={run} refIndex={refIndex} />);
    const region = panel("AI output: Triage");
    expect(within(region).getByText("Fallback provider: rules (fallback from anthropic)")).toBeVisible();
    expect(within(region).getByText("Confidence 42% (low)")).toBeVisible();
    expect(within(region).getByText("Flagged for review")).toBeVisible();
    expect(within(region).getByText("Why this needs extra review")).toBeVisible();
    expect(within(region).getByText("Low confidence (0.42).")).toBeVisible();
  });

  it("warns when the output cites nothing", () => {
    render(<AiPanel run={makeRun({ output: { ...makeRun().output, evidence_refs: [] } })} refIndex={refIndex} />);
    expect(screen.getByText("No citations: treat this output as unsupported.")).toBeVisible();
  });

  it("reports a failed agent and points to the manual workflow", () => {
    render(<AiPanel run={makeRun({ agent: "rca", status: "FAILED", output: null, error: "provider timeout" })} refIndex={refIndex} />);
    const region = panel("AI output: Root cause analysis (5 Whys)");
    expect(within(region).getByText(AI_LABEL)).toBeVisible();
    expect(within(region).getByRole("alert")).toHaveTextContent("This agent failed (provider timeout)");
    expect(within(region).queryByText("Open questions for the investigator")).toBeNull();
  });

  it("frames compliance findings as possible gaps, not legal determinations", () => {
    const run = makeRun({
      agent: "compliance",
      output: {
        findings: [
          {
            requirement: "Open edges must be protected by guardrails.",
            source_title: "Working at Height Procedure",
            source_ref: "chunk:abc",
            status: "LIKELY_NOT_MET",
            note: "The report describes a removed guardrail.",
          },
        ],
        disclaimer: "Decision support only; not a legal compliance determination.",
        confidence: 0.6,
        open_questions: [],
        evidence_refs: ["chunk:abc"],
      },
    });
    render(<AiPanel run={run} refIndex={buildRefIndex(undefined, [], [run])} />);
    const region = panel("AI output: Compliance evidence mapping");
    expect(within(region).getByText("Possible gap")).toBeVisible();
    expect(within(region).getByText("Decision support only; not a legal compliance determination.")).toBeVisible();
    expect(within(region).getByText("Document: Working at Height Procedure")).toBeVisible();
  });
});
