// A grounded knowledge answer is labelled AI decision support, cites title, version, page and section for every
// source, states insufficient and conflicting evidence plainly, and never presents removed claims as facts.
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AI_LABEL } from "@/components/ai/ai-panel";
import { GroundedAnswer, citationText } from "@/components/knowledge/grounded-answer";
import type { KnowledgeAnswer } from "@/lib/types";

const QUESTION = "How deep can an excavation be before shoring is required?";

function makeAnswer(overrides: Partial<KnowledgeAnswer> = {}): KnowledgeAnswer {
  return {
    status: "ANSWERED",
    answer: "Excavations 1.5 m or deeper need shoring or a trench box [1].",
    statements: [{ text: "Excavations 1.5 m or deeper need shoring or a trench box.", citations: ["document:d1#chunk:4"] }],
    citations: [
      {
        ref: "document:d1#chunk:4",
        document_id: "d1",
        document_title: "Excavation Safety Procedure",
        section: "3.2 Protective systems",
        page: 4,
        version: "2",
        effective_date: "2026-01-15",
      },
    ],
    confidence: 0.82,
    uncertainty: "Site-specific soil conditions are not covered.",
    unsupported_claims: [],
    conflicts: [],
    excluded_sources: [],
    needs_human_review: false,
    provider: "rules",
    retrieval: { sources: 3, best_rerank: 0.7, question_coverage: 0.8 },
    disclaimer: "Decision support only; not a legal or compliance determination.",
    ...overrides,
  };
}

function region() {
  return screen.getByRole("region", { name: "AI output: Grounded answer" });
}

describe("citationText", () => {
  it("names the title, version, page and section", () => {
    expect(citationText(makeAnswer().citations[0]!)).toBe("Excavation Safety Procedure · v2 · page 4 · section 3.2 Protective systems");
    expect(citationText({ document_title: "Note", version: "1", page: null, section: "" })).toBe("Note · v1 · no page number");
  });
});

describe("GroundedAnswer", () => {
  it("is labelled AI decision support with provider and confidence", () => {
    render(<GroundedAnswer result={makeAnswer()} question={QUESTION} />);
    const r = region();
    expect(r).toHaveAttribute("data-kind", "ai");
    expect(r).toHaveAttribute("data-status", "ANSWERED");
    expect(within(r).getByText(AI_LABEL)).toBeVisible();
    expect(within(r).getByText("Provider: rules")).toBeVisible();
    expect(within(r).getByText("Confidence 82%")).toBeVisible();
    expect(within(r).getByText("Answered from cited sources")).toBeVisible();
    expect(within(r).getByText(QUESTION)).toBeVisible();
  });

  it("links each statement to a citation that shows title, version, page and section", () => {
    render(<GroundedAnswer result={makeAnswer()} question={QUESTION} />);
    const statements = within(region()).getByRole("list", { name: "Answer statements" });
    expect(within(statements).getByText(/1\.5 m or deeper/)).toBeVisible();
    expect(within(statements).getByRole("link", { name: "Source 1" })).toHaveAttribute("href", "#citation-1");
    const [citation] = screen.getAllByTestId("answer-citation");
    expect(citation).toHaveAttribute("id", "citation-1");
    expect(citation).toHaveTextContent("Excavation Safety Procedure · v2 · page 4 · section 3.2 Protective systems");
    expect(citation).toHaveTextContent("document:d1#chunk:4");
  });

  it("states insufficient evidence plainly and cites nothing", () => {
    render(
      <GroundedAnswer
        result={makeAnswer({
          status: "INSUFFICIENT_EVIDENCE",
          answer: "The authorized documents do not answer this question.",
          statements: [],
          citations: [],
          confidence: 0.2,
          needs_human_review: true,
        })}
        question={QUESTION}
      />,
    );
    const r = region();
    expect(r).toHaveAttribute("data-status", "INSUFFICIENT_EVIDENCE");
    expect(within(r).getByText("Insufficient evidence")).toBeVisible();
    expect(within(r).getByText(/no answer was made up/)).toBeVisible();
    expect(within(r).getByText("The authorized documents do not answer this question.")).toBeVisible();
    expect(within(r).getByText("No sources cited: there is nothing here to act on.")).toBeVisible();
    expect(within(r).getByText("Confidence 20% (low)")).toBeVisible();
    expect(within(r).getByText("Flagged for review")).toBeVisible();
    expect(screen.queryAllByTestId("answer-citation")).toHaveLength(0);
  });

  it("shows conflicting evidence as an alert with both sources", () => {
    const second = { ...makeAnswer().citations[0]!, ref: "document:d2#chunk:1", document_id: "d2", document_title: "Site Rules", version: "5", page: null };
    render(
      <GroundedAnswer
        result={makeAnswer({
          status: "CONFLICTING_EVIDENCE",
          statements: [
            { text: "Shoring from 1.5 m.", citations: ["document:d1#chunk:4"] },
            { text: "Shoring from 1.2 m.", citations: ["document:d2#chunk:1"] },
          ],
          citations: [makeAnswer().citations[0]!, second],
          conflicts: ["The sources give different depths: 1.5 m and 1.2 m."],
          needs_human_review: true,
        })}
        question={QUESTION}
      />,
    );
    const r = region();
    expect(within(r).getByText("Conflicting evidence")).toBeVisible();
    expect(within(r).getByRole("alert")).toHaveTextContent("The sources give different depths: 1.5 m and 1.2 m.");
    const citations = screen.getAllByTestId("answer-citation");
    expect(citations).toHaveLength(2);
    expect(citations[1]).toHaveTextContent("Site Rules · v5 · no page number · section 3.2 Protective systems");
  });

  it("lists removed claims only as struck-out text and names excluded sources", () => {
    render(
      <GroundedAnswer
        result={makeAnswer({
          unsupported_claims: ["Shoring is never needed in clay."],
          excluded_sources: [{ ref: "document:d9#chunk:2", reason: "instruction-like text" }],
        })}
        question={QUESTION}
      />,
    );
    const removed = screen.getByText("Shoring is never needed in clay.");
    expect(removed.closest("ul")).toHaveClass("line-through");
    expect(removed.closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText(/1 statement\(s\) removed/)).toBeVisible();
    expect(screen.getByText(/document:d9#chunk:2/)).toBeVisible();
  });
});
