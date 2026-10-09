"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useAppContext } from "@/components/app-context";
import { ApprovalBadge, DomainBadge, SeverityBadge, StatusBadge, SyntheticBadge, WorkBadge } from "@/components/badges";
import { BarList, ColumnChart, StatTile, type BarItem } from "@/components/charts";
import { AlertIcon, OctagonShape } from "@/components/icons";
import { Card, PageHeader } from "@/components/layout";
import { EmptyState, ErrorState, LoadingState, PartialNotice } from "@/components/states";
import { formatDate, formatDateTime, humanize, roleLabel } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { can } from "@/lib/permissions";
import { INCIDENT_STATUSES, SEVERITIES, type Dashboard } from "@/lib/types";

const OVERDUE_LIMIT = 10; // GET /dashboard returns at most 10 overdue actions
const RECENT_LIMIT = 8; // and the 8 most recent incidents

function ordered(record: Record<string, number>, order: readonly string[]): [string, number][] {
  const known = order.filter((k) => k in record).map((k) => [k, record[k] ?? 0] as [string, number]);
  const extra = Object.entries(record).filter(([k]) => !order.includes(k));
  return [...known, ...extra];
}

function monthLabel(key: string): string {
  const [y, m] = key.split("-");
  const date = new Date(Date.UTC(Number(y), Number(m) - 1, 1));
  return Number.isNaN(date.getTime())
    ? key
    : new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: "UTC" }).format(date);
}

export default function DashboardPage() {
  const { project } = useAppContext();
  const dash = useApi<Dashboard>(project ? "/dashboard" : null, { project_id: project?.id });

  if (!project) return null;
  const header = (
    <PageHeader
      kicker={`${project.code} · ${project.client ?? "Project"}`}
      title="Project dashboard"
      subtitle={`${project.name}${project.location ? ` · ${project.location}` : ""}. All dates; counts are live.`}
      actions={
        can(project.permissions, "CREATE_INCIDENT") ? (
          <Link href="/incidents/new" className="btn-primary">
            Report incident
          </Link>
        ) : null
      }
    />
  );

  if (dash.status === "error" && dash.error && !dash.data) {
    return (
      <>
        {header}
        <ErrorState error={dash.error} onRetry={dash.reload} what="this project's dashboard" />
      </>
    );
  }
  if (!dash.data) {
    return (
      <>
        {header}
        <LoadingState label="Loading dashboard…" />
      </>
    );
  }

  const d = dash.data;
  const t = d.totals;
  if (t.incidents === 0) {
    return (
      <>
        {header}
        <div className="card">
          <EmptyState title="No incidents reported for this project yet">
            When incidents and quality observations are reported, counts, hazards and corrective actions appear here.
          </EmptyState>
        </div>
      </>
    );
  }

  const partial: string[] = [];
  if (t.actions_overdue > d.overdue_actions.length) {
    partial.push(`Showing ${d.overdue_actions.length} of ${t.actions_overdue} overdue actions.`);
  }
  if (d.agents.failed > 0) {
    partial.push(`${d.agents.failed} AI agent run(s) failed; those incidents continue through the manual workflow.`);
  }

  const toItems = (pairs: [string, number][], render?: (k: string) => ReactNode): BarItem[] =>
    pairs.map(([k, v]) => ({ key: k, label: render ? render(k) : humanize(k), text: humanize(k), value: v }));

  return (
    <>
      {header}
      {dash.refreshing ? <p className="sr-only" role="status">Refreshing…</p> : null}
      <div className="space-y-4">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
          <StatTile label="Incidents" value={t.incidents} />
          <StatTile label="Open" value={t.open} />
          <StatTile
            label="Open critical"
            value={t.open_critical}
            emphasis={t.open_critical > 0}
            icon={t.open_critical > 0 ? <OctagonShape size={12} className="text-red-700" /> : undefined}
            hint={t.open_critical > 0 ? "Needs HSE attention" : "None open"}
          />
          <StatTile label="Awaiting review" value={t.awaiting_review} hint="Proposed actions" />
          <StatTile label="Actions open" value={t.actions_open} hint="Approved, not verified" />
          <StatTile
            label="Actions overdue"
            value={t.actions_overdue}
            emphasis={t.actions_overdue > 0}
            icon={t.actions_overdue > 0 ? <AlertIcon size={12} className="text-red-700" /> : undefined}
            hint={t.actions_overdue > 0 ? "Past due date" : "None overdue"}
          />
          <StatTile
            label="Mean days to close"
            value={t.mean_days_to_close ?? "—"}
            hint={t.mean_days_to_close === null ? "No closed incidents" : "Closed incidents"}
          />
        </dl>

        <PartialNotice title="Partial result" items={partial} />

        <div className="grid items-start gap-4 lg:grid-cols-3">
          <Card title="Incidents by status">
            <BarList caption="Incidents by status" keepOrder items={toItems(ordered(d.by_status, INCIDENT_STATUSES))} />
          </Card>
          <Card title="Incidents by severity">
            <BarList
              caption="Incidents by severity"
              keepOrder
              items={toItems(ordered(d.by_severity, SEVERITIES), (k) => <SeverityBadge severity={k} />)}
            />
          </Card>
          <Card title="Safety vs quality">
            <BarList caption="Incidents by domain" items={toItems(Object.entries(d.by_domain))} />
          </Card>
          <Card title="Incidents by month (date occurred)">
            <ColumnChart
              caption="Incidents by month"
              items={Object.entries(d.by_month).map(([k, v]) => ({ key: k, label: monthLabel(k), text: monthLabel(k), value: v }))}
            />
          </Card>
          <Card title="Recurring hazards and defects (AI triage)">
            <BarList
              caption="Top hazards from AI triage"
              items={d.top_hazards.map(([k, v]) => ({ key: k, label: k, text: k, value: v }))}
              emptyText="No triage results yet."
            />
            <p className="mt-2 text-xs text-slate-500">From AI triage output; confirm on the incident before acting.</p>
          </Card>
          <Card title="AI agent runs">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <dt className="text-slate-600">Runs</dt>
              <dd className="text-right font-semibold tabular-nums">{d.agents.runs}</dd>
              <dt className="text-slate-600">Succeeded</dt>
              <dd className="text-right font-semibold tabular-nums">{d.agents.succeeded}</dd>
              <dt className="text-slate-600">Failed</dt>
              <dd className="text-right font-semibold tabular-nums">{d.agents.failed}</dd>
              <dt className="text-slate-600">Flagged for human review</dt>
              <dd className="text-right font-semibold tabular-nums">{d.agents.flagged_for_review}</dd>
              <dt className="text-slate-600">Provider fallbacks</dt>
              <dd className="text-right font-semibold tabular-nums">{d.agents.fallbacks}</dd>
            </dl>
            <p className="kicker mt-3">Providers</p>
            <ul className="mt-1 text-sm">
              {Object.entries(d.agents.providers).map(([name, count]) => (
                <li key={name} className="flex justify-between">
                  <span className="mono">{name}</span>
                  <span className="font-semibold tabular-nums">{count}</span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="CAPA approval status">
            <BarList
              caption="Corrective and preventive actions by approval status"
              items={toItems(Object.entries(d.capa_by_status), (k) => <ApprovalBadge status={k} />)}
            />
          </Card>
          <Card title="Approved CAPA work status">
            <BarList
              caption="Approved actions by work status"
              items={toItems(Object.entries(d.capa_work), (k) => <WorkBadge status={k} />)}
            />
          </Card>
        </div>

        <div className="grid items-start gap-4 xl:grid-cols-2">
          <Card title={`Overdue actions (${t.actions_overdue})`} bodyClassName="overflow-x-auto">
            {d.overdue_actions.length === 0 ? (
              <EmptyState title="No overdue actions">Approved actions are all within their due dates.</EmptyState>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">Action</th>
                    <th scope="col">Due</th>
                    <th scope="col">Work</th>
                  </tr>
                </thead>
                <tbody>
                  {d.overdue_actions.slice(0, OVERDUE_LIMIT).map((a) => (
                    <tr key={a.id}>
                      <td>
                        <Link className="link" href={`/incidents/${a.incident_id}#capa`}>
                          {a.title}
                        </Link>
                        <div className="text-xs text-slate-600">{roleLabel(a.owner_role)}</div>
                      </td>
                      <td className="font-semibold whitespace-nowrap text-red-800">
                        <AlertIcon size={12} className="mr-1 inline" />
                        {formatDate(a.due_date)}
                      </td>
                      <td>
                        <WorkBadge status={a.work_status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
          <Card title={`Recent incidents (latest ${RECENT_LIMIT})`} bodyClassName="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Incident</th>
                  <th scope="col">Severity</th>
                  <th scope="col">Status</th>
                  <th scope="col">Reported</th>
                </tr>
              </thead>
              <tbody>
                {d.recent.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <Link className="link" href={`/incidents/${i.id}`}>
                        {i.reference}
                      </Link>{" "}
                      <span className="text-slate-800">{i.title}</span>
                      <div className="mt-0.5 flex gap-1">
                        <DomainBadge domain={i.domain} />
                        {i.is_synthetic ? <SyntheticBadge /> : null}
                      </div>
                    </td>
                    <td>
                      <SeverityBadge severity={i.severity} />
                    </td>
                    <td>
                      <StatusBadge status={i.status} />
                    </td>
                    <td className="whitespace-nowrap text-slate-700">{formatDateTime(i.reported_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </div>
    </>
  );
}
