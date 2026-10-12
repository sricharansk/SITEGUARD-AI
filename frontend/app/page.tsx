"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, fmtDate, label, qs } from "@/lib/api";
import type { Dashboard } from "@/lib/types";
import { useSession } from "@/components/Shell";
import { BarList, Button, Card, ErrorBanner, Loading, SeverityBadge, StatTile, StatusBadge } from "@/components/ui";

const LIFECYCLE = ["REPORTED", "TRIAGED", "UNDER_INVESTIGATION", "PENDING_APPROVAL", "ACTION_IN_PROGRESS", "PENDING_VERIFICATION", "CLOSED"];

export default function DashboardPage() {
  const { project, can } = useSession();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [escalated, setEscalated] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!project) return;
    let current = true; // ignore a slower response for a project the user switched away from
    api
      .get<Dashboard>(`/dashboard${qs({ project_id: project.id })}`)
      .then((d) => current && setData(d))
      .catch((e) => current && setError(e));
    return () => {
      current = false;
    };
  }, [project]);
  useEffect(load, [load]);

  if (!project) return <p className="text-sm text-muted">You have no projects yet.</p>;
  if (error) return <ErrorBanner error={error} />;
  if (!data) return <Loading what="Loading dashboard" />;
  const t = data.totals;

  async function escalate() {
    const r = await api.post<{ escalations: unknown[] }>("/capa/escalate-overdue", { project_id: project!.id });
    setEscalated(`${r.escalations.length} escalation(s) sent.`);
    load();
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">{project.name}</h1>
          <p className="text-sm text-ink-2">
            {project.code} · {project.location} · safety and quality incidents, AI investigations and corrective actions
          </p>
        </div>
        <div className="flex items-center gap-2">
          {escalated && <span className="text-sm text-ink-2" role="status">{escalated}</span>}
          {can("APPROVE_CAPA") && (
            <Button variant="secondary" onClick={escalate}>
              Escalate overdue actions
            </Button>
          )}
          {can("CREATE_INCIDENT") && (
            <Link href="/incidents/new/" className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-ink">
              Report incident
            </Link>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
        <StatTile label="Incidents" value={t.incidents} />
        <StatTile label="Open" value={t.open} />
        <StatTile label="Open critical" value={t.open_critical} />
        <StatTile label="Actions awaiting review" value={t.awaiting_review} />
        <StatTile label="Actions in progress" value={t.actions_open} />
        <StatTile label="Actions overdue" value={t.actions_overdue} note={t.actions_escalated ? `${t.actions_escalated} escalated` : undefined} />
        <StatTile label="Mean days to close" value={t.mean_days_to_close} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <BarList title="Incidents by status" rows={LIFECYCLE.filter((s) => data.by_status[s]).map((s) => [s, data.by_status[s]])} />
        <BarList title="Top hazards and defects (AI triage)" rows={data.top_hazards} />
        <div className="space-y-4">
          <BarList title="Incidents by domain" rows={Object.entries(data.by_domain).sort((a, b) => b[1] - a[1])} />
          <Card title="Reported severity">
            <ul className="flex flex-wrap gap-2">
              {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => (
                <li key={s} className="flex items-center gap-1 text-sm">
                  <SeverityBadge value={s} /> <span className="tabular">{data.by_severity[s] ?? 0}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Recent incidents" actions={<Link href="/incidents/" className="text-xs text-accent hover:underline">All incidents</Link>}>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-1 font-medium">Ref</th>
                <th className="py-1 font-medium">Incident</th>
                <th className="py-1 font-medium">Severity</th>
                <th className="py-1 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.recent.map((i) => (
                <tr key={i.id} className="border-t border-line align-top">
                  <td className="tabular whitespace-nowrap py-1.5 pr-2 text-xs">{i.reference}</td>
                  <td className="py-1.5 pr-2">
                    <Link href={`/incident/?id=${i.id}`} className="text-accent hover:underline">
                      {i.title}
                    </Link>
                  </td>
                  <td className="py-1.5 pr-2"><SeverityBadge value={i.severity} /></td>
                  <td className="py-1.5"><StatusBadge value={i.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <div className="space-y-4">
          <Card title="Overdue actions">
            {data.overdue_actions.length === 0 ? (
              <p className="text-sm text-muted">No approved action is overdue.</p>
            ) : (
              <ul className="divide-y divide-line text-sm">
                {data.overdue_actions.map((a) => (
                  <li key={a.id} className="py-1.5">
                    <Link href={`/incident/?id=${a.incident_id}`} className="text-accent hover:underline">{a.title}</Link>
                    <span className="block text-xs text-muted">due {fmtDate(a.due_date)} · {label(a.work_status)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="AI agents">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
              {(["runs", "succeeded", "failed", "flagged_for_review", "fallbacks"] as const).map((k) => (
                <div key={k}>
                  <dt className="text-xs text-muted">{label(k)}</dt>
                  <dd className="tabular font-semibold">{data.agents[k]}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-xs text-muted">
              Action decisions: {Object.entries(data.capa_by_status).map(([k, v]) => `${label(k)} ${v}`).join(" · ")}
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
