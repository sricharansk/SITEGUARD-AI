"use client";

// Incident workspace panels for photo review, the investigation workflow and the knowledge graph. The API checks every
// permission again; these panels only hide what the caller cannot do.

import { useCallback, useEffect, useState } from "react";
import { ApiError, api, fmtDate, label } from "@/lib/api";
import type { GraphView, VisionAnalysis, VisionObservation, Workspace, WorkflowRun } from "@/lib/types";
import { AiPanel, Button, Card, ErrorBanner, Field, inputCls } from "@/components/ui";

type Act = (name: string, fn: () => Promise<unknown>) => Promise<void>;
const IMAGE_TYPES = ["image/jpeg", "image/png"];
const ACTIVE = ["RUNNING", "PAUSED", "FAILED"];

/** Photo evidence: run an analysis, see observations with their boxes, confirm or reject each one. */
export function PhotoReview({ ws, busy, canRun, onChange }: { ws: Workspace; busy: string | null; canRun: boolean; onChange: () => void }) {
  const photos = ws.evidence.filter((e) => IMAGE_TYPES.includes(e.content_type));
  const [analyses, setAnalyses] = useState<VisionAnalysis[]>([]);
  const [disclaimer, setDisclaimer] = useState("");
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const incidentId = ws.incident.id;

  const load = useCallback(() => {
    api
      .get<{ disclaimer: string; analyses: VisionAnalysis[] }>(`/incidents/${incidentId}/vision`)
      .then((r) => {
        setAnalyses(r.analyses);
        setDisclaimer(r.disclaimer);
      })
      .catch(setError);
  }, [incidentId]);
  useEffect(load, [load]);

  if (photos.length === 0) return null;

  async function run(evidenceId: string, task: VisionAnalysis["task"]) {
    setRunning(`${evidenceId}:${task}`);
    setError(null);
    try {
      await api.post(`/evidence/${evidenceId}/vision`, { task });
      load();
      onChange();
    } catch (e) {
      setError(e);
    } finally {
      setRunning(null);
    }
  }

  return (
    <Card title="Photo review">
      <p className="mb-2 text-xs text-ink-2">{disclaimer}</p>
      <ErrorBanner error={error} />
      <ul className="space-y-4">
        {photos.map((p) => {
          const mine = analyses.filter((a) => a.evidence_id === p.id);
          const observations = mine.flatMap((a) => a.observations);
          return (
            <li key={p.id} className="space-y-2 border-t border-line pt-3 first:border-0 first:pt-0">
              <div className="flex flex-wrap items-start gap-3">
                <Photo evidenceId={p.id} name={p.filename} boxes={observations.filter((o) => o.box && o.review_status !== "REJECTED")} />
                <div className="min-w-0 flex-1 space-y-2">
                  <p className="text-sm font-medium">{p.filename}</p>
                  {canRun && ws.incident.status !== "CLOSED" && (
                    <div className="flex flex-wrap gap-2">
                      {(["PPE_HAZARD", "DEFECT"] as const).map((task) => (
                        <Button key={task} variant="secondary" disabled={!!running || !!busy} onClick={() => run(p.id, task)}>
                          {running === `${p.id}:${task}` ? "Analyzing…" : task === "PPE_HAZARD" ? "Check PPE and hazards" : "Check defects"}
                        </Button>
                      ))}
                    </div>
                  )}
                  {mine.map((a) => (
                    <Analysis key={a.id} a={a} canReview={canRun && ws.incident.status !== "CLOSED"} onReviewed={load} />
                  ))}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function Photo({ evidenceId, name, boxes }: { evidenceId: string; name: string; boxes: VisionObservation[] }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    let made: string | null = null;
    api
      .blob(`/evidence/${evidenceId}/download`)
      .then((b) => {
        made = URL.createObjectURL(b);
        if (current) setUrl(made);
      })
      .catch(() => {});
    return () => {
      current = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [evidenceId]);
  return (
    <div className="relative w-48 shrink-0 overflow-hidden rounded border border-line bg-surface-2">
      {url ? (
        <img src={url} alt={`Photo evidence: ${name}`} className="block w-full" />
      ) : (
        <div className="flex h-32 items-center justify-center text-xs text-muted">Loading photo…</div>
      )}
      {url &&
        boxes.map((o) => (
          <span
            key={o.id}
            title={`${o.name} (${Math.round(o.confidence * 100)}%)`}
            className={`absolute border-2 ${o.review_status === "CONFIRMED" ? "border-critical" : "border-dashed border-ai"}`}
            style={{ left: `${o.box!.x * 100}%`, top: `${o.box!.y * 100}%`, width: `${o.box!.w * 100}%`, height: `${o.box!.h * 100}%` }}
          />
        ))}
    </div>
  );
}

function Analysis({ a, canReview, onReviewed }: { a: VisionAnalysis; canReview: boolean; onReviewed: () => void }) {
  const flags = a.image_quality.flags ?? [];
  return (
    <AiPanel title={`${label(a.task)} analysis · ${fmtDate(a.created_at, true)}`} provider={`${a.analyzer} ${a.model_version}`}>
      <p className={`text-xs ${a.status === "FAILED" ? "text-critical-ink" : "text-ink-2"}`}>
        {a.status === "FAILED" ? `Failed: ${a.error}` : `${a.observations.length} observation(s)`}
        {flags.length > 0 && ` · image quality: ${flags.map(label).join(", ")}`} · taxonomy {a.taxonomy_version}
      </p>
      <ul className="mt-1 list-disc pl-5 text-xs text-ink-2">
        {a.limitations.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
      {a.observations.length > 0 && (
        <ul className="mt-2 space-y-2">
          {a.observations.map((o) => (
            <Observation key={o.id} o={o} canReview={canReview} onReviewed={onReviewed} />
          ))}
        </ul>
      )}
    </AiPanel>
  );
}

function Observation({ o, canReview, onReviewed }: { o: VisionObservation; canReview: boolean; onReviewed: () => void }) {
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function decide(decision: "CONFIRMED" | "REJECTED") {
    setSaving(true);
    setError(null);
    try {
      await api.post(`/vision/observations/${o.id}/review`, { decision, note });
      setNote("");
      onReviewed();
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }

  return (
    <li className="rounded border border-line p-2 text-xs">
      <p className="font-medium text-ink">
        {o.name} · {Math.round(o.confidence * 100)}% (threshold {Math.round(o.threshold * 100)}%)
        {!o.above_threshold && " · below threshold"}
      </p>
      {o.maps_to && <p className="text-ink-2">Maps to: {o.maps_to}</p>}
      <p className={o.review_status === "CONFIRMED" ? "text-good-ink" : o.review_status === "REJECTED" ? "text-muted" : "text-ink-2"}>
        {o.review_status === "UNREVIEWED" ? "Not reviewed: a machine observation, not a finding." : `${label(o.review_status)}: ${o.review_note ?? ""}`}
      </p>
      {canReview && (
        <div className="mt-1 space-y-1">
          <Field label="Review note">
            <input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} placeholder="What you checked on the photo or on site" />
          </Field>
          <div className="flex gap-2">
            <Button variant="secondary" disabled={saving || note.trim().length < 3} onClick={() => decide("CONFIRMED")}>
              Confirm
            </Button>
            <Button variant="secondary" disabled={saving || note.trim().length < 3} onClick={() => decide("REJECTED")}>
              Reject
            </Button>
          </div>
          <ErrorBanner error={error} />
        </div>
      )}
    </li>
  );
}

/** The latest investigation workflow: stages, uncertainty, and pause / resume / cancel. */
export function WorkflowCard({ wf, act, busy, canRun, onFlags }: { wf: WorkflowRun | null; act: Act; busy: string | null; canRun: boolean; onFlags: (f: string[]) => void }) {
  const [reason, setReason] = useState("");
  if (!wf || wf.kind !== "INVESTIGATION") return null;
  const u = wf.uncertainty ?? {};
  const resumable = wf.status === "PAUSED" || wf.status === "FAILED";
  return (
    <Card title="AI investigation workflow">
      <p className="text-sm">
        <span className="font-medium">{label(wf.status)}</span>
        {wf.current_stage && ACTIVE.includes(wf.status) ? ` at ${wf.current_stage}` : ""} · provider {wf.provider}
      </p>
      {wf.status_reason && <p className="text-xs text-ink-2">{wf.status_reason}</p>}
      <ol className="mt-2 grid grid-cols-2 gap-x-3 text-xs">
        {Object.entries(wf.stages ?? {}).map(([name, s]) => (
          <li key={name} className={s.status === "FAILED" || s.status === "ERROR" ? "text-critical-ink" : "text-ink-2"}>
            {name}: {label(s.status)}
            {s.attempts && s.attempts > 1 ? ` (${s.attempts} attempts)` : ""}
          </li>
        ))}
      </ol>
      {u.min_confidence != null && (
        <div className="mt-2 text-xs text-ink-2">
          <p>
            Lowest agent confidence {Math.round(u.min_confidence * 100)}%
            {u.low_confidence_agents?.length ? ` · low confidence: ${u.low_confidence_agents.join(", ")}` : ""}
            {u.failed_stages?.length ? ` · failed: ${u.failed_stages.join(", ")}` : ""}
          </p>
          {u.unresolved_questions && u.unresolved_questions.length > 0 && <p>{u.unresolved_questions.length} open question(s) for the investigator.</p>}
        </div>
      )}
      {canRun && resumable && (
        <div className="mt-3 space-y-2 border-t border-line pt-3">
          <Button
            disabled={!!busy}
            onClick={() =>
              act("resume", async () => {
                const r = await api.post<{ flags: string[] }>(`/workflows/${wf.id}/resume`, {});
                onFlags(r.flags);
              })
            }
          >
            {busy === "resume" ? "Resuming…" : "Resume investigation"}
          </Button>
          <Field label="Reason to cancel">
            <input className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <Button variant="danger" disabled={!!busy || reason.trim().length < 3} onClick={() => act("cancel", () => api.post(`/workflows/${wf.id}/cancel`, { reason }))}>
            Cancel workflow
          </Button>
        </div>
      )}
      {canRun && wf.status === "RUNNING" && (
        <Button variant="secondary" className="mt-3" disabled={!!busy} onClick={() => act("pause", () => api.post(`/workflows/${wf.id}/pause`, {}))}>
          Pause before the next stage
        </Button>
      )}
    </Card>
  );
}

export const workflowActive = (wf: WorkflowRun | null) => !!wf && ACTIVE.includes(wf.status);

/** The incident's neighbourhood in the knowledge graph, loaded on request, with provenance. */
export function GraphCard({ incidentId, organizationId, canSync }: { incidentId: string; organizationId: string; canSync: boolean }) {
  const [graph, setGraph] = useState<GraphView | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "disabled">("idle");
  const [error, setError] = useState<unknown>(null);

  async function load(sync = false) {
    setState("loading");
    setError(null);
    try {
      if (sync) await api.post(`/graph/sync?organization_id=${organizationId}`, {});
      setGraph(await api.get<GraphView>(`/incidents/${incidentId}/graph`));
      setState("idle");
    } catch (e) {
      if (e instanceof ApiError && e.code === "GRAPH_DISABLED") setState("disabled");
      else {
        setError(e);
        setState("idle");
      }
    }
  }

  const name = (n: GraphView["nodes"][number]) =>
    String(n.properties.reference ?? n.properties.title ?? n.properties.name ?? n.properties.statement ?? n.properties.requirement ?? n.id);
  const byId = Object.fromEntries((graph?.nodes ?? []).map((n) => [`${n.label}:${n.id}`, n]));
  return (
    <Card title="Knowledge graph">
      {state === "disabled" ? (
        <p className="text-sm text-ink-2">The knowledge graph is not enabled on this server.</p>
      ) : !graph ? (
        <Button variant="secondary" disabled={state === "loading"} onClick={() => load()}>
          {state === "loading" ? "Loading…" : "Show related records"}
        </Button>
      ) : (
        <div className="space-y-2 text-xs">
          {!graph.synced ? (
            <p className="text-ink-2">This incident is not in the graph yet.</p>
          ) : (
            <ul className="space-y-0.5">
              {graph.edges.map((e) => {
                const src = byId[`${e.source_label}:${e.source}`];
                const dst = byId[`${e.target_label}:${e.target}`];
                return (
                  <li key={e.id}>
                    {src ? name(src) : e.source} <span className="text-muted">—{label(e.type)}→</span> {dst ? name(dst) : e.target}
                    {e.provenance.ai_derived ? <span className="ml-1 rounded bg-ai-wash px-1">AI, {label(String(e.provenance.review_status ?? "UNREVIEWED"))}</span> : null}
                  </li>
                );
              })}
            </ul>
          )}
          <p className="text-muted">
            {graph.nodes.length} node(s), {graph.edges.length} relationship(s) · {graph.backend} store. {graph.note}
          </p>
          {canSync && (
            <Button variant="secondary" disabled={state === "loading"} onClick={() => load(true)}>
              Rebuild from records
            </Button>
          )}
        </div>
      )}
      <ErrorBanner error={error} />
    </Card>
  );
}
