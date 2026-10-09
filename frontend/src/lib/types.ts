export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface Membership {
  organization_id: string;
  organization: string;
  project_id: string | null;
  role: string;
  permissions: string[];
}
export interface Me {
  id: string;
  email: string;
  full_name: string;
  memberships: Membership[];
}
export interface Project {
  id: string;
  organization_id: string;
  code: string;
  name: string;
  client: string | null;
  location: string | null;
  sites: { id: string; name: string }[];
}
export interface Incident {
  id: string;
  reference: string;
  project_id: string;
  title: string;
  description: string;
  domain: string;
  severity: Severity;
  status: string;
  occurred_at: string;
  reported_at: string;
  location: string | null;
  activity: string | null;
  people_involved: number;
  immediate_actions: string | null;
  closed_at: string | null;
  is_synthetic: boolean;
}
export interface Capa {
  id: string;
  incident_id: string;
  action_type: string;
  title: string;
  description: string;
  owner_role: string | null;
  due_date: string | null;
  verification_criteria: string;
  critical: boolean;
  approval_status: string;
  work_status: string;
  ai_generated: boolean;
  evidence_refs: string[];
}
export interface AgentRun {
  id: string;
  agent: string;
  provider: string;
  status: string;
  output: Record<string, unknown> | null;
  trace: Record<string, unknown>[];
  error: string | null;
  needs_human_review: boolean;
}
export interface Risk {
  matrix_version: string;
  likelihood: number;
  consequence: number;
  score: number;
  band: string;
  rationale: string;
  inputs_source: string;
}
export interface Workspace {
  incident: Incident;
  history: { id: string; from_status: string | null; to_status: string; note: string | null; created_at: string }[];
  evidence: { id: string; filename: string; size_bytes: number; sha256: string }[];
  agent_runs: AgentRun[];
  risk: Risk | null;
  capa: Capa[];
  approvals: { id: string; decision?: string; reason?: string; created_at: string }[];
  verifications: { id: string; effective?: boolean; notes?: string; created_at: string }[];
  close_blockers: string[];
  permissions: string[];
}
export interface Dashboard {
  totals: Record<string, number | null>;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
  by_domain: Record<string, number>;
  by_month: Record<string, number>;
  top_hazards: [string, number][];
  capa_by_status: Record<string, number>;
  capa_work: Record<string, number>;
  agents: { runs: number; succeeded: number; failed: number; flagged_for_review: number; fallbacks: number; providers: Record<string, number> };
  overdue_actions: Capa[];
  recent: Incident[];
}
