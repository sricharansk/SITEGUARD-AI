"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Workspace } from "@/lib/types";
import AgentOutput from "@/components/AgentOutput";
import CapaCard from "@/components/CapaCard";
import { Card, Empty, ErrorBox, Loading, SeverityBadge, StatusPill, fmtDate, label } from "@/components/ui";

export default function IncidentWorkspace() {
  const { id } = useParams<{ id: string }>();
  const [ws, setWs] = useState<Workspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Workspace>(`/incidents/${id}`).then(setWs).catch((e: Error) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);

  async function investigate() {
    setRunning(true);
    setRunError(null);
    try {
      await api(`/incidents/${id}/investigate`, { method: "POST" });
      load();
    } catch (e) {
      setRunError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  if (error) return <ErrorBox message={error} />;
  if (!ws) return <Loading what="incident" />;
  const { incident: i, risk } = ws;
  const canRun = ws.permissions.includes("RUN_AGENTS") && i.status !== "CLOSED";

  return (
    <div className="space-y-5">
      <Link href="/incidents" className="text-sm text-brand hover:underline">← All incidents</Link>
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm text-ink-soft">{i.reference}</span>
          <SeverityBadge value={i.severity} />
          <StatusPill value={i.status} />
          <span className="text-sm text-ink-soft">{label(i.domain)}</span>
          {i.is_synthetic && <span className="rounded bg-surface-alt px-1.5 py-0.5 text-xs text-ink-soft">Synthetic demo data</span>}
        </div>
        <h1 className="mt-1 text-2xl font-bold">{i.title}</h1>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Report">
            <p className="text-sm">{i.description}</p>
            <dl className="mt-3 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
              <div><dt className="inline text-ink-soft">Location: </dt><dd className="inline">{i.location ?? "—"}</dd></div>
              <div><dt className="inline text-ink-soft">Activity: </dt><dd className="inline">{i.activity ?? "—"}</dd></div>
              <div><dt className="inline text-ink-soft">Occurred: </dt><dd className="inline">{fmtDate(i.occurred_at)}</dd></div>
              <div><dt className="inline text-ink-soft">People involved: </dt><dd className="inline">{i.people_involved}</dd></div>
              <div className="sm:col-span-2"><dt className="inline text-ink-soft">Immediate actions: </dt><dd className="inline">{i.immediate_actions ?? "—"}</dd></div>
            </dl>
          </Card>

          <Card
            title="AI investigation"
            action={canRun && (
              <button onClick={investigate} disabled={running}
                className="rounded bg-ai px-3 py-1.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60">
                {running ? "Running agents…" : ws.agent_runs.length ? "Re-run investigation" : "Run investigation"}
              </button>
            )}
          >
            {runError && <div className="mb-3"><ErrorBox message={runError} /></div>}
            {ws.agent_runs.length === 0 ? (
              <Empty>No agent runs yet. Running the investigation produces draft findings and proposed actions; nothing is approved until a person reviews it.</Empty>
            ) : (
              <div className="space-y-3">{ws.agent_runs.map((r) => <AgentOutput key={r.id} run={r} />)}</div>
            )}
          </Card>

          <Card title={`Corrective and preventive actions (${ws.capa.length})`}>
            {ws.capa.length === 0 ? <Empty>No actions proposed yet.</Empty> : (
              <div className="space-y-3">{ws.capa.map((c) => <CapaCard key={c.id} capa={c} permissions={ws.permissions} onChanged={load} />)}</div>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Risk (5×5 matrix)">
            {risk ? (
              <div className="text-sm">
                <div className="flex items-center gap-2"><SeverityBadge value={risk.band} prefix="Risk:" /> <span className="font-semibold">Score {risk.score}</span></div>
                <p className="mt-2">Likelihood {risk.likelihood} × consequence {risk.consequence}</p>
                <p className="mt-1 text-ink-soft">{risk.rationale}</p>
                <p className="mt-1 text-xs text-ink-faint">Inputs: {label(risk.inputs_source)} · matrix {risk.matrix_version}. Score is computed deterministically.</p>
              </div>
            ) : <Empty>Not assessed yet.</Empty>}
          </Card>

          <Card title="Closure readiness">
            {i.status === "CLOSED" ? <p className="text-sm">Closed {fmtDate(i.closed_at)}.</p> : ws.close_blockers.length === 0 ? (
              <p className="text-sm">No blockers. A person with close permission can close this incident.</p>
            ) : (
              <ul className="list-disc space-y-1 pl-5 text-sm">{ws.close_blockers.map((b) => <li key={b}>{b}</li>)}</ul>
            )}
            <p className="mt-2 text-xs text-ink-faint">Incidents never close automatically; every approved action must be independently verified first.</p>
          </Card>

          <Card title={`Evidence (${ws.evidence.length})`}>
            {ws.evidence.length === 0 ? <Empty>No evidence attached.</Empty> : (
              <ul className="space-y-1 text-sm">
                {ws.evidence.map((e) => <li key={e.id}>{e.filename} <span className="font-mono text-xs text-ink-faint">{e.sha256.slice(0, 10)}…</span></li>)}
              </ul>
            )}
          </Card>

          <Card title="History">
            <ol className="space-y-2 text-sm">
              {ws.history.map((h) => (
                <li key={h.id}>
                  <div className="font-medium">{h.from_status ? `${label(h.from_status)} → ` : ""}{label(h.to_status)}</div>
                  <div className="text-xs text-ink-soft">{fmtDate(h.created_at)}{h.note ? ` · ${h.note}` : ""}</div>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
    </div>
  );
}
