"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { useAppContext } from "@/components/app-context";
import { ApprovalBadge, DomainBadge, SeverityBadge, StatusBadge, SyntheticBadge, WorkBadge } from "@/components/badges";
import { BarList, StatTile, type BarItem } from "@/components/charts";
import { DashboardFilterBar } from "@/components/dashboard/filter-bar";
import { TrendCharts } from "@/components/dashboard/trends";
import { AlertIcon, OctagonShape } from "@/components/icons";
import { Card, PageHeader } from "@/components/layout";
import { EmptyState, ErrorState, LoadingState, PartialNotice } from "@/components/states";
import { DEFAULT_FILTERS, dashboardQuery, formatDays, formatHours, type DashboardFilters } from "@/lib/dashboard";
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

/** "on any date", "01 Sep 2026 – 09 Oct 2026", "from …" or "up to …" for the range the API applied. */
function rangeText(from: string | null, to: string | null): string {
  if (!from && !to) return "on any date";
  if (from && to) return `${formatDate(from)} – ${formatDate(to)}`;
  return from ? `from ${formatDate(from)}` : `up to ${formatDate(to)}`;
}

export default function DashboardPage() {
  const { project, projects } = useAppContext();
  const [filters, setFilters] = useState<DashboardFilters>(DEFAULT_FILTERS);
  const dash = useApi<Dashboard>(project ? "/dashboard" : null, project ? dashboardQuery(filters, project.id) : undefined);

  if (!project) return null;
  const projectCount = projects?.length ?? 1;
  const allProjects = filters.scope === "all" && projectCount > 1;
  const header = (
    <PageHeader
      kicker={allProjects ? `All my projects (${projectCount})` : `${project.code} · ${project.client ?? "Project"}`}
      title="Project dashboard"
      subtitle={
        allProjects
          ? "Every project you can access. Counts are live."
          : `${project.name}${project.location ? ` · ${project.location}` : ""}. Counts are live.`
      }
      actions={
        can(project.permissions, "CREATE_INCIDENT") ? (
          <Link href="/incidents/new" className="btn-primary">
            Report incident
          </Link>
        ) : null
      }
    />
  );
  const filterBar = (
    <DashboardFilterBar
      value={filters}
      project={project}
      projectCount={projectCount}
      onApply={setFilters}
      busy={dash.status === "loading"}
    />
  );

  if (dash.status === "error" && dash.error && !dash.data) {
    return (
      <>
        {header}
        <div className="space-y-3">
          {filterBar}
          <ErrorState error={dash.error} onRetry={dash.reload} what="this project's dashboard" />
        </div>
      </>
    );
  }
  if (!dash.data) {
    return (
      <>
        {header}
        <div className="space-y-3">
          {filterBar}
          <LoadingState label="Loading dashboard…" />
        </div>
      </>
    );
  }

  const d = dash.data;
  const t = d.totals;
  const summary = (
    <p className="text-xs text-slate-600" data-testid="dashboard-scope">
      Showing incidents that occurred {rangeText(d.filters.date_from, d.filters.date_to)} (UTC) in{" "}
      {d.filters.project_id ? `${project.code} only` : `all ${d.filters.projects} project(s) you can access`}; trend by{" "}
      {d.filters.interval === "week" ? "ISO week" : "month"}.
    </p>
  );
  if (t.incidents === 0) {
    const filtered = Boolean(d.filters.date_from || d.filters.date_to);
    return (
      <>
        {header}
        <div className="space-y-3">
          {filterBar}
          {summary}
          <div className="card">
            <EmptyState title={filtered ? "No incidents in this period" : "No incidents reported for this project yet"}>
              {filtered
                ? "Widen the date range or choose All dates."
                : "When incidents and quality observations are reported, counts, hazards and corrective actions appear here."}
            </EmptyState>
          </div>
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
  if (d.trends.truncated) {
    partial.push(
      `The trend shows the latest ${d.trends.buckets.length} periods; narrow the dates to see earlier ones. Totals cover the whole range.`,
    );
  }

  const toItems = (pairs: [string, number][], render?: (k: string) => ReactNode): BarItem[] =>
    pairs.map(([k, v]) => ({ key: k, label: render ? render(k) : humanize(k), text: humanize(k), value: v }));
  const interval = d.trends.interval === "week" ? "ISO week" : "month";

  return (
    <>
      {header}
      <div className="space-y-4">
        {filterBar}
        {summary}
        {/* Refetch keeps the frame: the previous numbers stay, dimmed, until the new slice arrives. */}
        <div className={`space-y-4 transition-opacity ${dash.refreshing ? "opacity-60" : ""}`} aria-busy={dash.refreshing || undefined}>
          {dash.refreshing ? (
            <p className="sr-only" role="status">
              Refreshing…
            </p>
          ) : null}
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-5">
            <StatTile label="Incidents" value={t.incidents} />
            <StatTile label="Open" value={t.open} />
            <StatTile
              label="Open critical"
              value={t.open_critical}
              emphasis={t.open_critical > 0}
              icon={t.open_critical > 0 ? <OctagonShape size={12} className="text-red-700" /> : undefined}
              hint={t.open_critical > 0 ? "Needs HSE attention" : "None open"}
            />
            <StatTile label="Closed" value={t.closed} hint="Verified and closed" />
            <StatTile
              label="Awaiting first response"
              value={t.awaiting_response}
              emphasis={t.awaiting_response > 0}
              icon={t.awaiting_response > 0 ? <AlertIcon size={12} className="text-red-700" /> : undefined}
              hint={t.awaiting_response > 0 ? "Still in Reported" : "All picked up"}
            />
            <StatTile
              label="Median first response"
              value={formatHours(t.median_response_hours)}
              hint={t.mean_response_hours === null ? "No responses yet" : `Mean ${formatHours(t.mean_response_hours)}`}
            />
            <StatTile
              label="Mean days to close"
              value={t.mean_days_to_close === null ? "—" : t.mean_days_to_close.toFixed(1)}
              hint={t.median_days_to_close === null ? "No closed incidents" : `Median ${formatDays(t.median_days_to_close)}`}
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
          </dl>

          <PartialNotice title="Partial result" items={partial} />

          <Card id="trends" title={`Response and closure trend (by ${interval} occurred)`}>
            <TrendCharts trends={d.trends} />
            <p className="mt-2 text-xs text-slate-600">
              First response: from the report to its first move out of Reported (a manual transition, or an AI triage or
              investigation that a person started). Days to close: from the report to closure, for closed incidents.
            </p>
          </Card>

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
            <Card title="Recurring hazards (AI triage)">
              <BarList
                caption="Top hazards from AI triage"
                items={d.top_hazards.map(([k, v]) => ({ key: k, label: k, text: k, value: v }))}
                emptyText="No triage results yet."
              />
              <p className="mt-2 text-xs text-slate-600">
                Incidents whose latest AI triage lists the item. AI decision support: confirm on the incident before
                acting.
              </p>
            </Card>
            <Card title="Quality defects (AI quality investigation)">
              <BarList
                caption="Top quality defects from AI quality investigation"
                items={d.top_defects.map(([k, v]) => ({ key: k, label: k, text: k, value: v }))}
                emptyText="No quality investigations yet."
              />
              <p className="mt-2 text-xs text-slate-600">
                Incidents whose latest AI quality investigation lists the defect. AI decision support: confirm on site.
              </p>
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
      </div>
    </>
  );
}
