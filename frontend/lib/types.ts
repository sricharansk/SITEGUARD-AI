// Response shapes of the Site Guard API (backend/app/api/serializers.py and the route modules).
// Timestamps are ISO strings; SQLite deployments omit the UTC offset, see lib/format.ts.

export type Permission =
  | "READ"
  | "CREATE_INCIDENT"
  | "EDIT_INCIDENT"
  | "RUN_AGENTS"
  | "PROPOSE_CAPA"
  | "APPROVE_CAPA"
  | "APPROVE_CRITICAL"
  | "UPDATE_CAPA_PROGRESS"
  | "VERIFY_CAPA"
  | "CLOSE_INCIDENT"
  | "MANAGE_DOCUMENTS"
  | "MANAGE_PROJECTS"
  | "VIEW_AUDIT";

export type Domain = "SAFETY" | "QUALITY" | "BOTH";
export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type RiskBand = Severity;
export type IncidentStatus =
  | "REPORTED"
  | "TRIAGED"
  | "UNDER_INVESTIGATION"
  | "PENDING_APPROVAL"
  | "ACTION_IN_PROGRESS"
  | "PENDING_VERIFICATION"
  | "CLOSED";
export type ApprovalStatus = "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "MODIFIED" | "REJECTED" | "SUPERSEDED";
export type WorkStatus = "NOT_STARTED" | "IN_PROGRESS" | "COMPLETED" | "VERIFIED" | "VERIFICATION_FAILED";

export const DOMAINS: readonly Domain[] = ["SAFETY", "QUALITY", "BOTH"];
export const SEVERITIES: readonly Severity[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
export const INCIDENT_STATUSES: readonly IncidentStatus[] = [
  "REPORTED",
  "TRIAGED",
  "UNDER_INVESTIGATION",
  "PENDING_APPROVAL",
  "ACTION_IN_PROGRESS",
  "PENDING_VERIFICATION",
  "CLOSED",
];

export interface ApiErrorBody {
  code: string;
  message: string;
  correlation_id: string | null;
}

export interface Envelope<T> {
  data: T | null;
  error: ApiErrorBody | null;
}

export interface Membership {
  organization_id: string;
  organization: string | null;
  project_id: string | null;
  role: string;
  permissions: Permission[];
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  memberships: Membership[];
}

export interface Site {
  id: string;
  name: string;
}

export interface Project {
  id: string;
  organization_id: string;
  code: string;
  name: string;
  client: string | null;
  location: string | null;
  sites: Site[];
  permissions: Permission[];
}

export interface Member {
  user_id: string;
  full_name: string;
  email: string;
  role: string;
  scope: "organization" | "project";
}

export interface Incident {
  id: string;
  reference: string;
  organization_id: string;
  project_id: string;
  site_id: string | null;
  title: string;
  description: string;
  category: string | null;
  domain: Domain;
  severity: Severity;
  status: IncidentStatus;
  occurred_at: string;
  reported_at: string;
  location: string | null;
  activity: string | null;
  people_involved: number;
  immediate_actions: string | null;
  reporter_id: string | null;
  closed_at: string | null;
  is_synthetic: boolean;
  updated_at: string;
}

export interface IncidentEvent {
  id: string;
  from_status: IncidentStatus | null;
  to_status: IncidentStatus;
  actor_id: string | null;
  note: string | null;
  created_at: string;
}

export interface Evidence {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  description: string | null;
  uploaded_by: string | null;
  created_at: string;
}

export interface TraceEntry {
  type: string;
  tool?: string;
  provider?: string;
  reasons?: string[];
  [key: string]: unknown;
}

export type AgentName = "triage" | "safety" | "quality" | "rca" | "compliance" | "capa";

export interface AgentRun {
  id: string;
  workflow_id: string;
  agent: AgentName | string;
  provider: string;
  status: "SUCCEEDED" | "FAILED" | string;
  output: Record<string, unknown> | null;
  trace: TraceEntry[];
  error: string | null;
  needs_human_review: boolean;
  started_at: string;
  finished_at: string | null;
}

export interface RiskAssessment {
  id: string;
  matrix_version: string;
  likelihood: number;
  consequence: number;
  score: number;
  band: RiskBand;
  rationale: string;
  inputs_source: "AI_SUGGESTED" | "HUMAN" | string;
  assessed_by: string | null;
  created_at: string;
}

export interface RiskMatrix {
  version: string;
  likelihood: Record<string, string>;
  consequence: Record<string, string>;
  /** rows = likelihood 1..5, columns = consequence 1..5 */
  bands: RiskBand[][];
}

export interface CapaAction {
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
  approval_status: ApprovalStatus;
  work_status: WorkStatus;
  ai_generated: boolean;
  original_ai_output: Record<string, unknown> | null;
  source_run_id: string | null;
  evidence_refs: string[] | null;
  created_at: string;
  updated_at: string;
}

export interface CapaBoardRow extends CapaAction {
  incident: Pick<Incident, "id" | "reference" | "title" | "severity" | "status">;
}

export interface ApprovalEvent {
  id: string;
  capa_id: string;
  reviewer_id: string;
  decision: "APPROVE" | "MODIFY" | "REJECT";
  reason: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
}

export interface VerificationRecord {
  id: string;
  capa_id: string;
  verifier_id: string;
  effective: boolean;
  notes: string;
  evidence_id: string | null;
  created_at: string;
}

export interface IncidentWorkspace {
  incident: Incident;
  history: IncidentEvent[];
  evidence: Evidence[];
  agent_runs: AgentRun[];
  risk: RiskAssessment | null;
  capa: CapaAction[];
  approvals: ApprovalEvent[];
  verifications: VerificationRecord[];
  close_blockers: string[];
  permissions: Permission[];
}

export interface InvestigationResult {
  workflow_id: string;
  incident_status: IncidentStatus;
  runs: AgentRun[];
  risk: RiskAssessment | null;
  proposed_actions: CapaAction[];
  flags: string[];
}

export interface Dashboard {
  totals: {
    incidents: number;
    open: number;
    open_critical: number;
    awaiting_review: number;
    actions_open: number;
    actions_overdue: number;
    mean_days_to_close: number | null;
  };
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
  by_domain: Record<string, number>;
  by_month: Record<string, number>;
  top_hazards: [string, number][];
  capa_by_status: Record<string, number>;
  capa_work: Record<string, number>;
  agents: {
    runs: number;
    succeeded: number;
    failed: number;
    flagged_for_review: number;
    fallbacks: number;
    providers: Record<string, number>;
  };
  overdue_actions: CapaAction[];
  recent: Incident[];
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  doc_type: string;
  source: string;
  version: string;
  domain: Domain;
  project_id: string | null;
  chunks: number;
  suspicious_chunks: number;
  sha256: string;
}

export interface SearchHit {
  ref: string;
  document_id: string;
  document_title: string;
  doc_type: string;
  domain: Domain;
  source: string;
  section: string;
  text: string;
  score: number;
  suspicious: boolean;
}

export interface AuditEvent {
  id: string;
  actor_id: string | null;
  actor_type: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  details: Record<string, unknown> | null;
  correlation_id: string | null;
  created_at: string;
}
