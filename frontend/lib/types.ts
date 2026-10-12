export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type Domain = "SAFETY" | "QUALITY" | "BOTH";
export type IncidentStatus =
  | "REPORTED"
  | "TRIAGED"
  | "UNDER_INVESTIGATION"
  | "PENDING_APPROVAL"
  | "ACTION_IN_PROGRESS"
  | "PENDING_VERIFICATION"
  | "CLOSED";

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
  site_id: string | null;
  title: string;
  description: string;
  domain: Domain;
  severity: Severity;
  status: IncidentStatus;
  occurred_at: string;
  reported_at: string;
  location: string | null;
  activity: string | null;
  people_involved: number;
  immediate_actions: string | null;
  reporter_id: string;
  closed_at: string | null;
  is_synthetic: boolean;
}

export interface AgentRun {
  id: string;
  workflow_id: string;
  agent: string;
  provider: string;
  status: string;
  output: Record<string, any> | null;
  trace: Record<string, any>[];
  error: string | null;
  needs_human_review: boolean;
  started_at: string;
}

export interface Risk {
  matrix_version: string;
  likelihood: number;
  consequence: number;
  score: number;
  band: string;
  rationale: string;
  inputs_source: "AI_SUGGESTED" | "HUMAN";
}

export interface Capa {
  id: string;
  incident_id: string;
  action_type: "CORRECTIVE" | "PREVENTIVE";
  title: string;
  description: string;
  owner_role: string | null;
  assignee_id: string | null;
  due_date: string | null;
  verification_criteria: string;
  critical: boolean;
  approval_status: string;
  work_status: string;
  ai_generated: boolean;
  evidence_refs: string[];
  incident_reference?: string;
  incident_title?: string;
  can_review?: boolean;
}

export interface Workspace {
  incident: Incident;
  history: { id: string; from_status: string | null; to_status: string; actor_id: string | null; note: string | null; created_at: string }[];
  evidence: { id: string; filename: string; content_type: string; size_bytes: number; sha256: string; description: string | null; created_at: string }[];
  agent_runs: AgentRun[];
  risk: Risk | null;
  capa: Capa[];
  approvals: { id: string; capa_id: string; reviewer_id: string; decision: string; reason: string; created_at: string }[];
  verifications: { id: string; capa_id: string; verifier_id: string; effective: boolean; notes: string; created_at: string }[];
  conflicts: Conflict[];
  close_blockers: string[];
  permissions: string[];
}

/** A disagreement the AI investigation recorded; a reviewer records the decision before closure. */
export interface Conflict {
  id: string;
  workflow_id: string;
  kind: string;
  summary: string;
  details: Record<string, unknown>;
  refs: string[];
  status: "OPEN" | "RESOLVED" | "SUPERSEDED";
  resolution: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
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
  agents: Record<string, any>;
  overdue_actions: Capa[];
  recent: Incident[];
}

export interface Person {
  id: string;
  full_name: string;
  role: string;
}

export interface Notification {
  id: string;
  kind: string;
  message: string;
  incident_id: string | null;
  capa_id: string | null;
  read_at: string | null;
  created_at: string;
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  memberships: { organization_id: string; organization: string; project_id: string | null; role: string; permissions: string[] }[];
}
