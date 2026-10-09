// Small, typed fixtures shaped like the API's responses (backend/app/api/serializers.py).
import type { AgentRun, CapaAction, Evidence, Member } from "@/lib/types";

export const INCIDENT_ID = "11111111-1111-4111-8111-111111111111";
export const EVIDENCE_ID = "22222222-2222-4222-8222-222222222222";
export const ASSIGNEE_ID = "33333333-3333-4333-8333-333333333333";

export function envelopeResponse(data: unknown, init: { status?: number; headers?: Record<string, string> } = {}) {
  return new Response(JSON.stringify({ data, error: null }), {
    status: init.status ?? 200,
    headers: { "content-type": "application/json", ...init.headers },
  });
}

export function errorEnvelopeResponse(status: number, code: string, message: string, correlationId = "cid-12345678") {
  return new Response(JSON.stringify({ data: null, error: { code, message, correlation_id: correlationId } }), {
    status,
    headers: { "content-type": "application/json", "x-correlation-id": correlationId },
  });
}

export function makeRun(overrides: Partial<AgentRun> = {}): AgentRun {
  return {
    id: "run-1",
    workflow_id: "wf-1",
    agent: "triage",
    provider: "rules",
    status: "SUCCEEDED",
    output: {
      incident_class: "Fall from height",
      severity_candidate: "HIGH",
      priority: "P1",
      domain: "SAFETY",
      hazards: ["Unprotected slab edge"],
      missing_information: [],
      recommended_next_agents: ["safety"],
      rationale: "Open edge with no harness.",
      confidence: 0.8,
      open_questions: ["Who removed the guardrail?"],
      evidence_refs: [`incident:${INCIDENT_ID}`, `evidence:${EVIDENCE_ID}`],
    },
    trace: [],
    error: null,
    needs_human_review: false,
    started_at: "2026-10-09T08:00:00",
    finished_at: "2026-10-09T08:00:01",
    ...overrides,
  };
}

export const EVIDENCE: Evidence = {
  id: EVIDENCE_ID,
  filename: "supervisor-note.txt",
  content_type: "text/plain",
  size_bytes: 80,
  sha256: "a".repeat(64),
  description: "Supervisor statement",
  uploaded_by: null,
  created_at: "2026-10-09T08:00:00",
};

export function makeAction(overrides: Partial<CapaAction> = {}): CapaAction {
  return {
    id: "capa-1",
    incident_id: INCIDENT_ID,
    action_type: "CORRECTIVE",
    title: "Reinstate edge protection",
    description: "Install compliant guardrails at the slab edge.",
    owner_role: "SITE_ENGINEER",
    assignee_id: null,
    due_date: "2099-01-31",
    verification_criteria: "Photo evidence and supervisor sign-off.",
    critical: false,
    approval_status: "PENDING_REVIEW",
    work_status: "NOT_STARTED",
    ai_generated: true,
    original_ai_output: null,
    source_run_id: "run-1",
    evidence_refs: [`incident:${INCIDENT_ID}`],
    created_at: "2026-10-09T08:00:00",
    updated_at: "2026-10-09T08:00:00",
    ...overrides,
  };
}

export const MEMBERS: Member[] = [
  { user_id: ASSIGNEE_ID, full_name: "Sid Site", email: "site@example.test", role: "SITE_ENGINEER", scope: "project" },
];
