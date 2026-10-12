"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
import { api, API_BASE, fmtDate, getToken, label } from "@/lib/api";
import type { AgentRun, Capa, Workspace } from "@/lib/types";
import { personName, useSession } from "@/components/Shell";
import { AiPanel, Button, Card, ErrorBanner, Field, inputCls, Loading, SeverityBadge, StatusBadge } from "@/components/ui";

const RUNNABLE = ["REPORTED", "TRIAGED", "UNDER_INVESTIGATION", "PENDING_APPROVAL"];

export default function IncidentPage() {
  return (
    <Suspense fallback={<Loading />}>
      <IncidentWorkspace />
    </Suspense>
  );
}

function reasons(run: AgentRun): string[] {
  return run.trace.find((t) => t.type === "review_reasons")?.reasons ?? [];
}

function List({ items }: { items: string[] | undefined }) {
  if (!items || items.length === 0) return <span className="text-muted">None</span>;
  return (
    <ul className="list-disc space-y-0.5 pl-5">
      {items.map((x) => (
        <li key={x}>{x}</li>
      ))}
    </ul>
  );
}

function IncidentWorkspace() {
  const id = useSearchParams().get("id") ?? "";
  const { people, can, me } = useSession();
  const [ws, setWs] = useState<Workspace | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [flags, setFlags] = useState<string[]>([]);

  const load = useCallback(() => {
    if (!id) return;
    api.get<Workspace>(`/incidents/${id}`).then(setWs).catch(setError);
  }, [id]);
  useEffect(load, [load]);

  async function act(name: string, fn: () => Promise<unknown>) {
    setBusy(name);
    setError(null);
    try {
      await fn();
      load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  if (!id) return <ErrorBanner error={{ code: "NOT_FOUND", message: "No incident selected." }} />;
  if (!ws) return error ? <ErrorBanner error={error} /> : <Loading what="Loading incident" />;
  const inc = ws.incident;
  const perms = new Set(ws.permissions);
  const runs = Object.fromEntries(ws.agent_runs.map((r) => [r.agent, r]));
  const tri = runs.triage?.output;

  async function downloadReport(format: "md" | "docx" | "pdf") {
    const file = await api.blob(`/incidents/${id}/report?format=${format}`);
    const url = URL.createObjectURL(file);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${inc.reference}-report.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div>
        <Link href="/incidents/" className="text-xs text-accent hover:underline">
          ← Incidents
        </Link>
        <div className="mt-1 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="tabular text-xs text-muted">{inc.reference}</p>
            <h1 className="text-xl font-semibold">{inc.title}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <StatusBadge value={inc.status} />
              <SeverityBadge value={inc.severity} prefix="Reported" />
              <span className="text-xs text-ink-2">{label(inc.domain)}</span>
              {inc.is_synthetic && <span className="text-xs text-muted">Synthetic demo data</span>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {perms.has("RUN_AGENTS") && RUNNABLE.includes(inc.status) && (
              <Button
                disabled={!!busy}
                onClick={() =>
                  act("investigate", async () => {
                    const r = await api.post<{ flags: string[] }>(`/incidents/${id}/investigate`);
                    setFlags(r.flags);
                  })
                }
              >
                {busy === "investigate" ? "Agents running…" : ws.agent_runs.length ? "Re-run AI investigation" : "Run AI investigation"}
              </Button>
            )}
            <div role="group" aria-label="Download report" className="flex gap-1">
              {(
                [
                  ["md", "Report (Markdown)"],
                  ["docx", "Word"],
                  ["pdf", "PDF"],
                ] as const
              ).map(([format, text]) => (
                <Button key={format} variant="secondary" disabled={!!busy} onClick={() => act("report", () => downloadReport(format))}>
                  {text}
                </Button>
              ))}
            </div>
          </div>
        </div>
      </div>
      <ErrorBanner error={error} />
      {flags.length > 0 && (
        <div role="status" className="rounded-md border border-serious bg-surface px-3 py-2 text-sm">
          <strong>Needs your attention:</strong> {flags.join(" ")}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4">
          <Card title="What happened">
            <p className="whitespace-pre-line text-sm">{inc.description}</p>
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
              {[
                ["Occurred", fmtDate(inc.occurred_at, true)],
                ["Location", inc.location],
                ["Activity", inc.activity],
                ["People involved", inc.people_involved],
                ["Reported by", personName(people, inc.reporter_id)],
                ["Immediate actions", inc.immediate_actions],
              ].map(([k, v]) => (
                <div key={k as string}>
                  <dt className="text-xs text-muted">{k}</dt>
                  <dd>{v || "–"}</dd>
                </div>
              ))}
            </dl>
          </Card>

          {ws.agent_runs.length === 0 ? (
            <Card title="AI investigation">
              <p className="text-sm text-muted">
                Not run yet. The agents triage the report, investigate safety and/or quality, suggest risk inputs, propose root causes,
                map retrieved requirements with citations and propose actions. Nothing they produce is approved until a person reviews it.
              </p>
            </Card>
          ) : (
            <AiSections ws={ws} runs={runs} />
          )}

          <Actions ws={ws} act={act} busy={busy} meId={me.id} can={(p) => perms.has(p)} triClass={tri?.incident_class} />
        </div>

        <div className="space-y-4">
          <Closure ws={ws} act={act} can={(p) => perms.has(p)} />
          <Evidence ws={ws} act={act} canUpload={perms.has("EDIT_INCIDENT") && inc.status !== "CLOSED"} />
          <Card title="Lifecycle">
            <ol className="space-y-2 text-sm">
              {ws.history.map((h) => (
                <li key={h.id} className="border-l-2 border-line pl-2">
                  <div className="flex flex-wrap items-center gap-1">
                    <StatusBadge value={h.to_status} />
                    <span className="text-xs text-muted">{fmtDate(h.created_at, true)}</span>
                  </div>
                  <div className="text-xs text-ink-2">
                    {personName(people, h.actor_id)}
                    {h.note ? ` — ${h.note}` : ""}
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
    </div>
  );
}

function AiSections({ ws, runs }: { ws: Workspace; runs: Record<string, AgentRun> }) {
  const tri = runs.triage?.output;
  const safety = runs.safety?.output;
  const quality = runs.quality?.output;
  const rca = runs.rca?.output;
  const comp = runs.compliance?.output;
  const failed = ws.agent_runs.filter((r) => r.status !== "SUCCEEDED");
  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold">AI investigation</h2>
      {failed.length > 0 && (
        <ErrorBanner error={{ code: "AGENT_FAILED", message: `${failed.map((r) => r.agent).join(", ")} did not complete. Continue manually: add actions and use the workflow.` }} />
      )}
      {tri && (
        <AiPanel title="Triage" provider={runs.triage.provider} flagged={runs.triage.needs_human_review} reasons={reasons(runs.triage)}>
          <div className="flex flex-wrap items-center gap-2">
            <strong>{tri.incident_class}</strong>
            <span className="text-xs text-ink-2">{label(tri.domain)}</span>
            <SeverityBadge value={tri.severity_candidate} prefix="AI" />
            <span className="text-xs">Priority {tri.priority}</span>
            <span className="text-xs text-muted">confidence {tri.confidence}</span>
          </div>
          <p className="mt-1 text-ink-2">{tri.rationale}</p>
          {tri.missing_information?.length > 0 && (
            <div className="mt-2">
              <span className="text-xs font-semibold">Missing information</span>
              <List items={tri.missing_information} />
            </div>
          )}
        </AiPanel>
      )}
      {safety && (
        <AiPanel title="Safety investigation" provider={runs.safety.provider} flagged={runs.safety.needs_human_review} reasons={reasons(runs.safety)}>
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <span className="text-xs font-semibold">Unsafe acts</span>
              <List items={safety.unsafe_acts} />
            </div>
            <div>
              <span className="text-xs font-semibold">Unsafe conditions</span>
              <List items={safety.unsafe_conditions} />
            </div>
            <div>
              <span className="text-xs font-semibold">Failed or missing controls</span>
              <List items={safety.failed_or_missing_controls} />
            </div>
          </div>
        </AiPanel>
      )}
      {quality && (
        <AiPanel title="Quality investigation" provider={runs.quality.provider} flagged={runs.quality.needs_human_review} reasons={reasons(runs.quality)}>
          <p>
            <strong>{quality.defects.join(", ")}</strong> · probable stage {label(quality.probable_stage)}
          </p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            <div>
              <span className="text-xs font-semibold">Requirement vs observed</span>
              <List items={quality.requirement_vs_observed} />
            </div>
            <div>
              <span className="text-xs font-semibold">Recommended tests</span>
              <List items={quality.recommended_tests} />
            </div>
          </div>
        </AiPanel>
      )}
      {ws.risk && (
        <Card title="Risk (deterministic 5×5 matrix)">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <SeverityBadge value={ws.risk.band} prefix="Risk" />
            <span className="tabular">
              L{ws.risk.likelihood} × C{ws.risk.consequence} = {ws.risk.score}
            </span>
            <span className="text-xs text-muted">
              {ws.risk.inputs_source === "HUMAN" ? "Inputs set by a person" : "Inputs suggested by AI; score computed by the matrix"} · {ws.risk.matrix_version}
            </span>
          </div>
        </Card>
      )}
      {rca && (
        <AiPanel title="Root cause hypotheses (5-Whys)" provider={runs.rca.provider} flagged={runs.rca.needs_human_review} reasons={reasons(runs.rca)}>
          <ol className="list-decimal space-y-0.5 pl-5 text-ink-2">
            {rca.whys.map((w: string) => (
              <li key={w}>{w}</li>
            ))}
          </ol>
          <ul className="mt-2 space-y-1">
            {rca.root_causes.map((c: { category: string; statement: string; confidence: number }) => (
              <li key={c.statement}>
                <span className="mr-1 rounded bg-surface-2 px-1 text-xs">{label(c.category)}</span>
                {c.statement} <span className="text-xs text-muted">({c.confidence})</span>
              </li>
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted">Hypotheses for the investigator to validate with the people involved.</p>
        </AiPanel>
      )}
      {comp && (
        <AiPanel title="Requirements from retrieved documents" provider={runs.compliance.provider} flagged={runs.compliance.needs_human_review} reasons={reasons(runs.compliance)}>
          {comp.findings.length === 0 ? (
            <p className="text-muted">No relevant requirement was retrieved.</p>
          ) : (
            <ul className="space-y-2">
              {comp.findings.map((f: { requirement: string; source_title: string; source_ref: string; status: string; note: string }) => (
                <li key={f.source_ref + f.requirement}>
                  <span className={`mr-1 rounded px-1 text-xs font-medium ${f.status === "LIKELY_NOT_MET" ? "bg-surface-2 text-critical-ink" : "bg-surface-2"}`}>
                    {label(f.status)}
                  </span>
                  {f.requirement}
                  <div className="text-xs text-muted">
                    Source: {f.source_title} · <code>{f.source_ref.slice(0, 14)}…</code> · {f.note}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs italic text-muted">{comp.disclaimer}</p>
        </AiPanel>
      )}
    </div>
  );
}

type Act = (name: string, fn: () => Promise<unknown>) => Promise<void>;

function Actions({ ws, act, busy, meId, can, triClass }: { ws: Workspace; act: Act; busy: string | null; meId: string; can: (p: string) => boolean; triClass?: string }) {
  const { people } = useSession();
  const [adding, setAdding] = useState(false);
  const visible = ws.capa.filter((a) => a.approval_status !== "SUPERSEDED");
  return (
    <Card
      title={`Corrective and preventive actions (${visible.length})`}
      actions={
        can("PROPOSE_CAPA") && ws.incident.status !== "CLOSED" ? (
          <Button variant="secondary" onClick={() => setAdding(!adding)}>
            {adding ? "Cancel" : "Add action"}
          </Button>
        ) : undefined
      }
    >
      {adding && <NewAction incidentId={ws.incident.id} act={act} done={() => setAdding(false)} />}
      {visible.length === 0 ? (
        <p className="text-sm text-muted">No actions yet{triClass ? "" : " — run the AI investigation or add one"}.</p>
      ) : (
        <ul className="space-y-3">
          {visible.map((a) => (
            <ActionItem key={a.id} a={a} ws={ws} act={act} busy={busy} meId={meId} can={can} people={people} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function ActionItem({ a, ws, act, busy, meId, can, people }: { a: Capa; ws: Workspace; act: Act; busy: string | null; meId: string; can: (p: string) => boolean; people: Record<string, { full_name: string; role: string }> }) {
  const [mode, setMode] = useState<"" | "APPROVE" | "MODIFY" | "REJECT" | "VERIFY">("");
  const [reason, setReason] = useState("");
  const [changes, setChanges] = useState({ title: a.title, due_date: a.due_date ?? "", assignee_id: a.assignee_id ?? "" });
  const [effective, setEffective] = useState(true);
  const decision = ws.approvals.find((x) => x.capa_id === a.id);
  const verifs = ws.verifications.filter((v) => v.capa_id === a.id);
  const canReview = a.approval_status === "PENDING_REVIEW" && can(a.critical ? "APPROVE_CRITICAL" : "APPROVE_CAPA");
  const active = a.approval_status === "APPROVED" || a.approval_status === "MODIFIED";
  const canWork = active && can("UPDATE_CAPA_PROGRESS") && ["NOT_STARTED", "IN_PROGRESS", "VERIFICATION_FAILED"].includes(a.work_status);
  const canVerify = active && a.work_status === "COMPLETED" && can("VERIFY_CAPA") && a.assignee_id !== meId;

  function submitReview(e: FormEvent) {
    e.preventDefault();
    const body: Record<string, unknown> = { decision: mode, reason };
    if (mode === "MODIFY") {
      const diff: Record<string, unknown> = {};
      if (changes.title !== a.title) diff.title = changes.title;
      if (changes.due_date !== (a.due_date ?? "")) diff.due_date = changes.due_date || null;
      if (changes.assignee_id !== (a.assignee_id ?? "")) diff.assignee_id = changes.assignee_id || null;
      body.changes = diff;
    }
    act(`review-${a.id}`, () => api.post(`/capa/${a.id}/review`, body)).then(() => setMode(""));
  }

  return (
    <li className={`rounded-md border border-line p-3 ${a.ai_generated && a.approval_status === "PENDING_REVIEW" ? "border-l-4 border-l-ai" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-surface-2 px-1 text-xs">{label(a.action_type)}</span>
        <strong className="text-sm">{a.title}</strong>
        <StatusBadge value={a.approval_status} />
        {active && <StatusBadge value={a.work_status} />}
        {a.ai_generated && <span className="text-[11px] font-semibold uppercase text-ai">AI-proposed</span>}
        {a.critical && <span className="text-xs text-critical-ink">▲ needs HSE manager</span>}
      </div>
      <p className="mt-1 text-sm text-ink-2">{a.description}</p>
      <dl className="mt-1 flex flex-wrap gap-x-4 text-xs text-ink-2">
        <div>
          <dt className="inline text-muted">Owner </dt>
          <dd className="inline">{a.assignee_id ? personName(people as never, a.assignee_id) : label(a.owner_role ?? "unassigned")}</dd>
        </div>
        <div>
          <dt className="inline text-muted">Due </dt>
          <dd className="inline">{fmtDate(a.due_date) || "–"}</dd>
        </div>
        <div>
          <dt className="inline text-muted">Verification </dt>
          <dd className="inline">{a.verification_criteria}</dd>
        </div>
      </dl>
      {decision && (
        <p className="mt-1 text-xs text-ink-2">
          {label(decision.decision)} by {personName(people as never, decision.reviewer_id)}: “{decision.reason}”
        </p>
      )}
      {verifs.map((v) => (
        <p key={v.id} className={`mt-1 text-xs ${v.effective ? "text-good-ink" : "text-critical-ink"}`}>
          {v.effective ? "✓ Verified effective" : "✗ Failed verification"} by {personName(people as never, v.verifier_id)}: “{v.notes}”
        </p>
      ))}

      <div className="mt-2 flex flex-wrap gap-2">
        {canReview &&
          (["APPROVE", "MODIFY", "REJECT"] as const).map((m) => (
            <Button key={m} variant={m === "REJECT" ? "danger" : m === "APPROVE" ? "primary" : "secondary"} onClick={() => setMode(mode === m ? "" : m)}>
              {label(m)}
            </Button>
          ))}
        {a.approval_status === "PENDING_REVIEW" && !canReview && <span className="text-xs text-muted">Awaiting review by {a.critical ? "the HSE manager" : "a project or HSE manager"}.</span>}
        {canWork && a.work_status === "NOT_STARTED" && (
          <Button variant="secondary" disabled={!!busy} onClick={() => act(`start-${a.id}`, () => api.patch(`/capa/${a.id}/progress`, { work_status: "IN_PROGRESS", assignee_id: a.assignee_id ?? meId }))}>
            Start work
          </Button>
        )}
        {canWork && (
          <Button variant="secondary" disabled={!!busy} onClick={() => act(`done-${a.id}`, () => api.patch(`/capa/${a.id}/progress`, { work_status: "COMPLETED", assignee_id: a.assignee_id ?? meId, note: "Completed" }))}>
            Mark completed
          </Button>
        )}
        {canVerify && (
          <Button variant="secondary" onClick={() => setMode(mode === "VERIFY" ? "" : "VERIFY")}>
            Verify
          </Button>
        )}
        {active && a.work_status === "COMPLETED" && a.assignee_id === meId && can("VERIFY_CAPA") && (
          <span className="text-xs text-muted">You did this action, so someone else must verify it.</span>
        )}
      </div>

      {mode && mode !== "VERIFY" && (
        <form onSubmit={submitReview} className="mt-2 space-y-2 rounded-md bg-surface-2 p-2">
          {mode === "MODIFY" && (
            <div className="grid gap-2 sm:grid-cols-3">
              <Field label="Title">
                <input className={inputCls} value={changes.title} onChange={(e) => setChanges({ ...changes, title: e.target.value })} />
              </Field>
              <Field label="Due date">
                <input type="date" className={inputCls} value={changes.due_date} onChange={(e) => setChanges({ ...changes, due_date: e.target.value })} />
              </Field>
              <Field label="Assignee">
                <select className={inputCls} value={changes.assignee_id} onChange={(e) => setChanges({ ...changes, assignee_id: e.target.value })}>
                  <option value="">Unassigned</option>
                  {Object.entries(people).map(([pid, p]) => (
                    <option key={pid} value={pid}>
                      {p.full_name}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          )}
          <Field label={`Reason for ${label(mode).toLowerCase()} (required, recorded in the audit trail)`}>
            <input className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} required />
          </Field>
          <Button type="submit" disabled={!reason.trim() || !!busy}>
            Confirm {label(mode).toLowerCase()}
          </Button>
        </form>
      )}
      {mode === "VERIFY" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            act(`verify-${a.id}`, () => api.post(`/capa/${a.id}/verify`, { effective, notes: reason })).then(() => setMode(""));
          }}
          className="mt-2 space-y-2 rounded-md bg-surface-2 p-2"
        >
          <fieldset className="flex gap-4 text-sm">
            <legend className="sr-only">Result</legend>
            <label className="flex items-center gap-1">
              <input type="radio" checked={effective} onChange={() => setEffective(true)} /> Effective
            </label>
            <label className="flex items-center gap-1">
              <input type="radio" checked={!effective} onChange={() => setEffective(false)} /> Not effective (send back)
            </label>
          </fieldset>
          <Field label="What you checked">
            <input className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} required />
          </Field>
          <Button type="submit" disabled={!reason.trim() || !!busy}>
            Record verification
          </Button>
        </form>
      )}
    </li>
  );
}

function NewAction({ incidentId, act, done }: { incidentId: string; act: Act; done: () => void }) {
  const [f, setF] = useState({ action_type: "CORRECTIVE", title: "", description: "", verification_criteria: "", due_date: "", critical: false });
  return (
    <form
      className="mb-3 grid gap-2 rounded-md bg-surface-2 p-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        act("new-action", () => api.post(`/incidents/${incidentId}/capa`, { ...f, due_date: f.due_date || null })).then(done);
      }}
    >
      <Field label="Type">
        <select className={inputCls} value={f.action_type} onChange={(e) => setF({ ...f, action_type: e.target.value })}>
          <option value="CORRECTIVE">Corrective</option>
          <option value="PREVENTIVE">Preventive</option>
        </select>
      </Field>
      <Field label="Due date">
        <input type="date" className={inputCls} value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} />
      </Field>
      <div className="sm:col-span-2">
        <Field label="Title">
          <input className={inputCls} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} required minLength={3} />
        </Field>
      </div>
      <Field label="Description">
        <textarea className={inputCls} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} required minLength={3} />
      </Field>
      <Field label="Verification criterion" hint="How someone else will check it worked">
        <textarea className={inputCls} value={f.verification_criteria} onChange={(e) => setF({ ...f, verification_criteria: e.target.value })} required minLength={3} />
      </Field>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={f.critical} onChange={(e) => setF({ ...f, critical: e.target.checked })} /> Critical (HSE manager must approve)
      </label>
      <div className="sm:col-span-2">
        <Button type="submit">Propose action for review</Button>
      </div>
    </form>
  );
}

function Closure({ ws, act, can }: { ws: Workspace; act: Act; can: (p: string) => boolean }) {
  const [note, setNote] = useState("");
  const inc = ws.incident;
  if (inc.status === "CLOSED") {
    return (
      <Card title="Closure">
        <p className="text-sm text-good-ink">✓ Closed {fmtDate(inc.closed_at, true)} after every approved action was verified effective.</p>
      </Card>
    );
  }
  const allowed = can("CLOSE_INCIDENT") && (inc.severity !== "CRITICAL" || can("APPROVE_CRITICAL"));
  return (
    <Card title="Closure">
      {ws.close_blockers.length > 0 ? (
        <>
          <p className="text-sm font-medium">Not closable yet:</p>
          <ul className="mt-1 list-disc pl-5 text-sm text-ink-2">
            {ws.close_blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </>
      ) : allowed ? (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            act("close", () => api.post(`/incidents/${inc.id}/close`, { note }));
          }}
        >
          <Field label="Closure note">
            <textarea className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} required />
          </Field>
          <Button type="submit" disabled={!note.trim()}>
            Close incident
          </Button>
        </form>
      ) : (
        <p className="text-sm text-ink-2">Ready to close. {inc.severity === "CRITICAL" ? "A critical incident is closed by the HSE manager." : "A project or HSE manager closes it."}</p>
      )}
    </Card>
  );
}

function Evidence({ ws, act, canUpload }: { ws: Workspace; act: Act; canUpload: boolean }) {
  const [file, setFile] = useState<File | null>(null);
  const [desc, setDesc] = useState("");
  return (
    <Card title={`Evidence (${ws.evidence.length})`}>
      {ws.evidence.length === 0 ? (
        <p className="text-sm text-muted">No evidence attached.</p>
      ) : (
        <ul className="space-y-1.5 text-sm">
          {ws.evidence.map((e) => (
            <li key={e.id}>
              <button
                className="text-accent hover:underline"
                onClick={() =>
                  act("download", async () => {
                    const r = await fetch(`${API_BASE}/evidence/${e.id}/download`, { headers: { Authorization: `Bearer ${getToken()}` } });
                    const url = URL.createObjectURL(await r.blob());
                    window.open(url, "_blank", "noopener");
                  })
                }
              >
                {e.filename}
              </button>
              <div className="text-xs text-muted">
                {e.description} · {(e.size_bytes / 1024).toFixed(1)} KB · SHA-256 {e.sha256.slice(0, 12)}…
              </div>
            </li>
          ))}
        </ul>
      )}
      {canUpload && (
        <form
          className="mt-3 space-y-2 border-t border-line pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!file) return;
            const fd = new FormData();
            fd.append("file", file);
            if (desc) fd.append("description", desc);
            act("upload", () => api.upload(`/incidents/${ws.incident.id}/evidence`, fd)).then(() => {
              setFile(null);
              setDesc("");
            });
          }}
        >
          <input aria-label="Evidence file" type="file" accept=".jpg,.jpeg,.png,.pdf,.txt" className="text-sm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <input aria-label="Evidence description" className={inputCls} placeholder="What does it show?" value={desc} onChange={(e) => setDesc(e.target.value)} />
          <Button type="submit" variant="secondary" disabled={!file}>
            Upload
          </Button>
        </form>
      )}
    </Card>
  );
}
