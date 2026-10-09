"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Dashboard } from "@/lib/types";
import { useApp } from "@/components/Shell";
import { Card, Empty, ErrorBox, Loading, SeverityBadge, StatusPill, fmtDate, label } from "@/components/ui";

function Tile({ name, value, tone }: { name: string; value: string | number | null; tone?: "warn" | "ok" }) {
  const color = tone === "warn" && Number(value) > 0 ? "text-red-700" : "text-ink";
  return (
    <div className="rounded-lg border border-surface-line bg-surface p-4 shadow-sm">
      <div className={`text-3xl font-bold ${color}`}>{value ?? "—"}</div>
      <div className="mt-1 text-sm text-ink-soft">{name}</div>
    </div>
  );
}

// Bars always carry their label and number so nothing relies on colour alone.
function Bars({ data, empty }: { data: Record<string, number>; empty: string }) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  if (!entries.length) return <Empty>{empty}</Empty>;
  return (
    <ul className="space-y-2">
      {entries.map(([k, v]) => (
        <li key={k} className="grid grid-cols-[9rem_1fr_2rem] items-center gap-2 text-sm">
          <span className="truncate">{label(k)}</span>
          <span className="h-3 rounded bg-surface-alt" aria-hidden>
            <span className="block h-3 rounded bg-brand" style={{ width: `${(v / max) * 100}%` }} />
          </span>
          <span className="text-right font-semibold tabular-nums">{v}</span>
        </li>
      ))}
    </ul>
  );
}

export default function DashboardPage() {
  const { project } = useApp();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    api<Dashboard>(`/dashboard?project_id=${project.id}`).then(setData).catch((e: Error) => setError(e.message));
  }, [project.id]);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading what="dashboard" />;
  const t = data.totals;
  const ordered = ["CRITICAL", "HIGH", "MEDIUM", "LOW"].filter((s) => data.by_severity[s]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{project.name}</h1>
        <p className="text-sm text-ink-soft">{project.code} · {project.location ?? "No location"} · {project.sites.map((s) => s.name).join(", ")}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
        <Tile name="Incidents" value={t.incidents} />
        <Tile name="Open" value={t.open} />
        <Tile name="Open critical" value={t.open_critical} tone="warn" />
        <Tile name="Actions awaiting review" value={t.awaiting_review} />
        <Tile name="Actions open" value={t.actions_open} />
        <Tile name="Actions overdue" value={t.actions_overdue} tone="warn" />
        <Tile name="Mean days to close" value={t.mean_days_to_close} />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card title="By status"><Bars data={data.by_status} empty="No incidents yet." /></Card>
        <Card title="By severity">
          <ul className="space-y-2 text-sm">
            {ordered.length === 0 && <Empty>No incidents yet.</Empty>}
            {ordered.map((s) => (
              <li key={s} className="flex items-center justify-between">
                <SeverityBadge value={s} /> <span className="font-semibold tabular-nums">{data.by_severity[s]}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="By domain"><Bars data={data.by_domain} empty="No incidents yet." /></Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Top hazards (from AI triage)">
          {data.top_hazards.length === 0 ? <Empty>No triaged incidents yet.</Empty> : (
            <ul className="space-y-1 text-sm">
              {data.top_hazards.map(([h, n]) => (
                <li key={h} className="flex justify-between border-b border-surface-line py-1 last:border-0"><span>{h}</span><span className="font-semibold">{n}</span></li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Agent activity">
          <dl className="grid grid-cols-2 gap-y-1 text-sm">
            <dt className="text-ink-soft">Runs</dt><dd className="font-semibold">{data.agents.runs}</dd>
            <dt className="text-ink-soft">Succeeded</dt><dd className="font-semibold">{data.agents.succeeded}</dd>
            <dt className="text-ink-soft">Failed</dt><dd className="font-semibold">{data.agents.failed}</dd>
            <dt className="text-ink-soft">Flagged for human review</dt><dd className="font-semibold">{data.agents.flagged_for_review}</dd>
            <dt className="text-ink-soft">Fell back to rules</dt><dd className="font-semibold">{data.agents.fallbacks}</dd>
            <dt className="text-ink-soft">Provider</dt><dd className="font-semibold">{Object.keys(data.agents.providers).join(", ") || "—"}</dd>
          </dl>
        </Card>
      </div>

      <Card title="Overdue actions">
        {data.overdue_actions.length === 0 ? <Empty>No overdue actions.</Empty> : (
          <ul className="space-y-1 text-sm">
            {data.overdue_actions.map((a) => (
              <li key={a.id}><Link className="text-brand hover:underline" href={`/incidents/${a.incident_id}`}>{a.title}</Link> — due {fmtDate(a.due_date)}</li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Recent incidents" action={<Link href="/incidents" className="text-sm text-brand hover:underline">View all</Link>}>
        <ul className="divide-y divide-surface-line">
          {data.recent.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center gap-2 py-2">
              <span className="w-28 font-mono text-xs text-ink-soft">{i.reference}</span>
              <Link href={`/incidents/${i.id}`} className="min-w-0 flex-1 font-medium text-brand hover:underline">{i.title}</Link>
              <SeverityBadge value={i.severity} />
              <StatusPill value={i.status} />
              <span className="w-24 text-right text-xs text-ink-soft">{fmtDate(i.reported_at)}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
