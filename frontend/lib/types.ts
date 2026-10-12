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
  organization_id: string;
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
  workflow: WorkflowRun | null;
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

/** Knowledge document (procedure, ITP, specification). Content is untrusted. */
export interface KnowledgeDoc {
  id: string;
  organization_id: string;
  project_id: string | null;
  scope: "project" | "organization";
  title: string;
  doc_type: string;
  source: string;
  version: string;
  effective_date: string | null;
  tags: string[];
  domain: Domain;
  status: "PENDING" | "PROCESSING" | "READY" | "FAILED";
  error: string | null;
  file_name: string | null;
  content_type: string | null;
  size_bytes: number | null;
  page_count: number | null;
  parser: string | null;
  chunks: number;
  suspicious_chunks: number;
  sha256: string;
  uploaded_by: string | null;
  processed_at: string | null;
  created_at: string;
  duplicate?: boolean;
  chunk_list?: { ref: string; ordinal: number; section: string; page: number | null; suspicious: boolean; text: string }[];
}

export interface SearchHit {
  ref: string;
  document_id: string;
  document_title: string;
  doc_type: string;
  domain: Domain;
  source: string;
  section: string;
  page: number | null;
  version: string;
  effective_date: string | null;
  tags: string[];
  scope: "project" | "organization";
  text: string;
  score: number;
  scores: Record<string, number>;
  suspicious: boolean;
}

export interface GroundedAnswer {
  status: "ANSWERED" | "INSUFFICIENT_EVIDENCE" | "CONFLICTING_EVIDENCE";
  answer: string;
  statements: { text: string; citations: string[] }[];
  citations: { ref: string; document_id: string; document_title: string; section: string; page: number | null; version: string; effective_date: string | null }[];
  confidence: number;
  uncertainty: string;
  unsupported_claims: string[];
  conflicts: string[];
  excluded_sources: { ref: string; reason: string }[];
  needs_human_review: boolean;
  provider: string;
  disclaimer: string;
}

export interface VisionObservation {
  id: string;
  ref: string;
  analysis_id: string;
  evidence_id: string;
  category: "PPE" | "HAZARD" | "DEFECT";
  label: string;
  name: string;
  maps_to: string | null;
  confidence: number;
  threshold: number;
  above_threshold: boolean;
  box: { x: number; y: number; w: number; h: number } | null;
  note: string | null;
  review_status: "UNREVIEWED" | "CONFIRMED" | "REJECTED";
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
}

export interface VisionAnalysis {
  id: string;
  evidence_id: string;
  task: "PPE_HAZARD" | "DEFECT";
  analyzer: string;
  model: string;
  model_version: string;
  taxonomy_version: string;
  status: "COMPLETED" | "FAILED";
  error: string | null;
  image_quality: { flags?: string[] };
  limitations: string[];
  created_at: string;
  observations: VisionObservation[];
}

export interface WorkflowRun {
  id: string;
  kind: "TRIAGE" | "INVESTIGATION";
  status: "RUNNING" | "PAUSED" | "FAILED" | "COMPLETED" | "CANCELLED";
  status_reason: string | null;
  provider: string;
  current_stage: string | null;
  stages: Record<string, { status: string; attempts?: number; errors?: string[]; reason?: string }>;
  pause_after: string[];
  uncertainty: {
    min_confidence?: number | null;
    low_confidence_agents?: string[];
    failed_stages?: string[];
    agents_needing_review?: { agent: string; reasons: string[] }[];
    unresolved_questions?: { agent: string; question: string }[];
  };
  created_at: string;
  finished_at: string | null;
}

export interface GraphView {
  backend: string;
  synced: boolean;
  include_ai: boolean;
  nodes: { id: string; label: string; properties: Record<string, unknown>; provenance: Record<string, unknown> }[];
  edges: { id: string; type: string; source: string; source_label: string; target: string; target_label: string; provenance: Record<string, unknown> }[];
  note: string;
}
