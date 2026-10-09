"use client";

// Staged progress for POST /incidents/{id}/investigate. The API runs the bounded workflow in one request and
// commits at the end, so while it runs the stages advance in workflow order as an estimate (and say so); when
// the response arrives every stage shows what actually happened.
import { useEffect, useState } from "react";
import type { ApiError } from "@/lib/api";
import type { InvestigationResult } from "@/lib/types";
import { RiskBadge } from "../badges";
import { CheckIcon, CrossIcon, DashIcon, RingIcon, SpinnerIcon } from "../icons";

export const STAGES = [
  { key: "triage", label: "Triage" },
  { key: "safety", label: "Safety investigation" },
  { key: "quality", label: "Quality investigation" },
  { key: "risk", label: "Deterministic risk matrix" },
  { key: "rca", label: "Root cause analysis" },
  { key: "compliance", label: "Compliance evidence mapping" },
  { key: "capa", label: "CAPA proposals" },
] as const;

const STEP_MS = 1200;

type StageState = "pending" | "running" | "estimated" | "done" | "failed" | "skipped" | "stopped";

export function stageOutcome(key: string, result: InvestigationResult): { state: StageState; detail: string } {
  if (key === "risk") {
    return result.risk
      ? { state: "done", detail: `Scored ${result.risk.band} (${result.risk.score})` }
      : { state: "skipped", detail: "No risk inputs from the investigation agents" };
  }
  const run = result.runs.find((r) => r.agent === key);
  if (!run) return { state: "skipped", detail: "Not needed for this incident (triage routing)" };
  if (run.status !== "SUCCEEDED") return { state: "failed", detail: "Failed: continue manually" };
  return { state: "done", detail: run.needs_human_review ? "Done, flagged for review" : "Done" };
}

function StageIcon({ state }: { state: StageState }) {
  switch (state) {
    case "done":
      return <CheckIcon size={14} className="text-emerald-700" />;
    case "estimated":
      return <CheckIcon size={14} className="text-slate-400" />;
    case "failed":
    case "stopped":
      return <CrossIcon size={14} className="text-red-700" />;
    case "running":
      return <SpinnerIcon size={14} className="text-violet-700" />;
    case "skipped":
      return <DashIcon size={14} className="text-slate-500" />;
    default:
      return <RingIcon size={14} className="text-slate-400" />;
  }
}

export function InvestigationProgress({
  startedAt,
  result,
  error,
}: {
  /** Time the run was requested (ms since epoch) while it is in flight; null once it has finished. */
  startedAt: number | null;
  result: InvestigationResult | undefined;
  error: ApiError | undefined;
}) {
  const running = startedAt !== null;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (startedAt === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  const ms = startedAt === null ? 0 : Math.max(0, now - startedAt);
  const elapsed = Math.floor(ms / 1000);
  const step = Math.min(STAGES.length - 1, Math.floor(ms / STEP_MS));

  if (!running && !result && !error) return null;

  const rows = STAGES.map((stage, i) => {
    if (running) {
      const state: StageState = i < step ? "estimated" : i === step ? "running" : "pending";
      const detail = state === "running" ? "Running…" : state === "estimated" ? "Likely complete" : "Waiting";
      return { ...stage, state, detail };
    }
    if (result) return { ...stage, ...stageOutcome(stage.key, result) };
    return { ...stage, state: "stopped" as StageState, detail: "Not completed" };
  });

  const succeeded = result?.runs.filter((r) => r.status === "SUCCEEDED").length ?? 0;
  const failed = result ? result.runs.length - succeeded : 0;

  return (
    <div className="rounded-md border border-violet-300 bg-white px-3 py-2" data-testid="investigation-progress">
      <p role="status" aria-live="polite" className="text-sm font-semibold text-violet-950">
        {running
          ? `AI investigation running (${elapsed}s)…`
          : result
            ? `AI investigation finished: ${succeeded} agent run(s) succeeded${failed ? `, ${failed} failed` : ""}. Proposals await human review.`
            : "AI investigation did not complete."}
      </p>
      {running ? (
        <p className="text-xs text-slate-600">
          Stages are shown in workflow order while the server runs them; the outcome of each appears when the run
          finishes. A live AI provider can take a few minutes.
        </p>
      ) : null}
      <ol aria-label="Investigation stages" className="mt-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-4">
        {rows.map((row, i) => (
          <li key={row.key} className="flex items-start gap-1.5 text-xs" data-state={row.state}>
            <span className="mt-0.5">
              <StageIcon state={row.state} />
            </span>
            <span>
              <span className="font-semibold text-slate-900">
                {i + 1}. {row.label}
              </span>
              <span className="block text-slate-600">
                {row.key === "risk" && result?.risk && !running ? (
                  <RiskBadge band={result.risk.band} score={result.risk.score} />
                ) : (
                  row.detail
                )}
              </span>
            </span>
          </li>
        ))}
        <li className="flex items-start gap-1.5 text-xs" data-state="human">
          <span className="mt-0.5">
            <RingIcon size={14} className="text-sky-700" />
          </span>
          <span>
            <span className="font-semibold text-slate-900">{STAGES.length + 1}. Human review</span>
            <span className="block text-slate-600">Approve, modify or reject each proposal</span>
          </span>
        </li>
      </ol>
      {result && result.flags.length > 0 ? (
        <div className="mt-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950">
          <p className="font-semibold">Conflicts flagged for human review</p>
          <ul className="list-disc pl-5">
            {result.flags.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
