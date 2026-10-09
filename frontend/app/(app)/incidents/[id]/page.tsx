"use client";

// Incident command center: one workspace to follow an incident from report to verified closure.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { buildRefIndex } from "@/components/ai/refs";
import { useAppContext } from "@/components/app-context";
import { CapaActionCard, ProposeActionForm } from "@/components/incident/capa";
import { EvidencePanel } from "@/components/incident/evidence-panel";
import { InvestigationPanel } from "@/components/incident/investigation-panel";
import { peopleIndex } from "@/components/incident/people";
import { RiskPanel } from "@/components/incident/risk-panel";
import { IncidentSummary, LifecycleStepper, Timeline } from "@/components/incident/summary";
import { CloseControl, TransitionControl } from "@/components/incident/workflow-panel";
import { Card, PageHeader } from "@/components/layout";
import { EmptyState, ErrorState, LoadingState, PartialNotice, SuccessNote } from "@/components/states";
import { useApi } from "@/lib/hooks";
import { can } from "@/lib/permissions";
import type { CapaAction, IncidentWorkspace, Member, RiskMatrix } from "@/lib/types";

const SECTIONS = [
  ["facts", "Facts"],
  ["investigation", "AI investigation"],
  ["risk", "Risk"],
  ["capa", "Actions"],
  ["evidence", "Evidence"],
  ["workflow", "Workflow"],
  ["timeline", "Timeline"],
] as const;

function actionRank(a: CapaAction): number {
  if (a.approval_status === "PENDING_REVIEW") return 0;
  if (a.approval_status === "APPROVED" || a.approval_status === "MODIFIED") return 1;
  return 2;
}

export default function IncidentPage() {
  const params = useParams<{ id: string }>();
  const incidentId = params.id;
  const { me, projects } = useAppContext();
  const ws = useApi<IncidentWorkspace>(`/incidents/${encodeURIComponent(incidentId)}`);
  const matrix = useApi<RiskMatrix>("/risk/matrix");
  const projectId = ws.data?.incident.project_id;
  const members = useApi<Member[]>(projectId ? `/projects/${projectId}/members` : null);
  const [notice, setNotice] = useState<string | null>(null);

  const people = useMemo(() => peopleIndex(members.data), [members.data]);
  const refIndex = useMemo(
    () => buildRefIndex(ws.data?.incident, ws.data?.evidence ?? [], ws.data?.agent_runs ?? []),
    [ws.data],
  );

  if (ws.status === "error" && ws.error && !ws.data) {
    return (
      <>
        <PageHeader title="Incident" actions={<Link href="/incidents" className="btn-secondary">Back to incidents</Link>} />
        <ErrorState error={ws.error} onRetry={ws.reload} what="this incident" />
      </>
    );
  }
  if (!ws.data) return <LoadingState label="Loading incident workspace…" />;

  const data = ws.data;
  const { incident, permissions } = data;
  const project = projects?.find((p) => p.id === incident.project_id);
  const reload = ws.reload;
  const onActionChanged = (message?: string) => {
    setNotice(message ?? null);
    reload();
  };

  const partial: string[] = [];
  if (matrix.status === "error") partial.push(`Risk matrix unavailable (${matrix.error?.message ?? "error"}).`);
  if (members.status === "error") partial.push("People on the project could not be loaded; names show as IDs and assignment is limited.");

  const actions = [...data.capa].sort((a, b) => actionRank(a) - actionRank(b));
  const current = actions.filter((a) => actionRank(a) < 2);
  const closedOut = actions.filter((a) => actionRank(a) === 2);
  const pendingCount = actions.filter((a) => a.approval_status === "PENDING_REVIEW").length;

  const card = (a: CapaAction) => (
    <CapaActionCard
      key={a.id}
      action={a}
      permissions={permissions}
      meId={me?.id}
      members={members.data}
      people={people}
      approvals={data.approvals.filter((x) => x.capa_id === a.id)}
      verifications={data.verifications.filter((x) => x.capa_id === a.id)}
      evidence={data.evidence}
      refIndex={refIndex}
      onChanged={onActionChanged}
    />
  );

  return (
    <>
      <PageHeader
        kicker={`${incident.reference}${project ? ` · ${project.code} ${project.name}` : ""}`}
        title={incident.title}
        subtitle={<div className="mt-2"><LifecycleStepper status={incident.status} /></div>}
        actions={
          <Link href="/incidents" className="btn-secondary">
            Back to incidents
          </Link>
        }
      />
      <nav aria-label="Incident sections" className="mb-3 flex flex-wrap gap-1 text-xs">
        {SECTIONS.map(([id, label]) => (
          <a key={id} href={`#${id}`} className="rounded border border-slate-300 bg-white px-2 py-1 font-medium text-slate-700 hover:bg-slate-50">
            {label}
            {id === "capa" && pendingCount > 0 ? ` (${pendingCount} to review)` : ""}
          </a>
        ))}
        {ws.refreshing ? (
          <span role="status" className="ml-2 self-center text-slate-500">
            Updating…
          </span>
        ) : null}
      </nav>
      <div className="mb-3 space-y-2">
        <PartialNotice items={partial} />
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-3">
        <div className="min-w-0 space-y-4 xl:col-span-2">
          <div id="facts">
            <IncidentSummary incident={incident} project={project} people={people} />
          </div>
          <Card id="investigation" title="AI investigation (decision support)">
            <InvestigationPanel
              incidentId={incident.id}
              status={incident.status}
              runs={data.agent_runs}
              refIndex={refIndex}
              permissions={permissions}
              onChanged={reload}
            />
          </Card>
          <Card id="risk" title="Risk assessment">
            <RiskPanel
              incidentId={incident.id}
              risk={data.risk}
              matrix={matrix.data}
              people={people}
              canAssess={can(permissions, "RUN_AGENTS") && incident.status !== "CLOSED"}
              onChanged={reload}
            />
          </Card>
          <Card
            id="capa"
            title={`Corrective and preventive actions (${actions.length})`}
            actions={pendingCount > 0 ? <span className="text-xs font-semibold text-amber-900">{pendingCount} awaiting review</span> : null}
          >
            <div className="space-y-3">
              <SuccessNote message={notice} />
              {current.length === 0 ? (
                <EmptyState title="No open actions">
                  Run the AI investigation to get proposals, or add a human-authored action.
                </EmptyState>
              ) : (
                current.map(card)
              )}
              {closedOut.length > 0 ? (
                <details className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                  <summary className="cursor-pointer text-sm font-medium">Rejected or superseded proposals ({closedOut.length})</summary>
                  <div className="mt-2 space-y-2">{closedOut.map(card)}</div>
                </details>
              ) : null}
              {can(permissions, "PROPOSE_CAPA") && incident.status !== "CLOSED" ? (
                <ProposeActionForm incidentId={incident.id} members={members.data} onChanged={onActionChanged} />
              ) : null}
            </div>
          </Card>
        </div>

        <div className="min-w-0 space-y-4">
          <Card id="evidence" title={`Evidence (${data.evidence.length})`} className="border-l-4 border-l-emerald-600">
            <EvidencePanel
              incidentId={incident.id}
              evidence={data.evidence}
              people={people}
              canUpload={can(permissions, "EDIT_INCIDENT")}
              onChanged={reload}
            />
          </Card>
          <Card id="workflow" title="Workflow and closure">
            <div className="space-y-4">
              <TransitionControl incident={incident} permissions={permissions} onChanged={reload} />
              <hr className="border-slate-200" />
              <CloseControl incident={incident} blockers={data.close_blockers} permissions={permissions} onChanged={reload} />
            </div>
          </Card>
          <Card id="timeline" title="Lifecycle timeline">
            <Timeline history={data.history} people={people} />
          </Card>
        </div>
      </div>
    </>
  );
}
