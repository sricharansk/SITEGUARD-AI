"use client";

import { useState } from "react";
import type { AgentRun } from "@/lib/types";
import { AiBlock, label } from "./ui";

const HIDDEN = new Set(["confidence", "evidence_refs"]);

function Value({ v }: { v: unknown }) {
  if (v === null || v === undefined || v === "") return <span className="text-ink-faint">—</span>;
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return <span>{String(v)}</span>;
  if (Array.isArray(v)) {
    if (!v.length) return <span className="text-ink-faint">None</span>;
    return (
      <ul className="list-disc space-y-0.5 pl-5">
        {v.map((x, i) => <li key={i}><Value v={x} /></li>)}
      </ul>
    );
  }
  return (
    <dl className="space-y-1">
      {Object.entries(v as Record<string, unknown>).map(([k, x]) => (
        <div key={k}><dt className="inline font-medium">{label(k)}: </dt><dd className="inline"><Value v={x} /></dd></div>
      ))}
    </dl>
  );
}

export default function AgentOutput({ run }: { run: AgentRun }) {
  const [trace, setTrace] = useState(false);
  const out = run.output ?? {};
  const entries = Object.entries(out).filter(([k]) => !HIDDEN.has(k));
  const confidence = typeof out.confidence === "number" ? out.confidence : null;
  const refs = Array.isArray(out.evidence_refs) ? (out.evidence_refs as string[]) : [];

  return (
    <AiBlock title={`${label(run.agent)} agent`}>
      <div className="mb-2 flex flex-wrap gap-2 text-xs text-ink-soft">
        <span>Provider: {run.provider}</span>
        <span>Status: {label(run.status)}</span>
        {confidence !== null && <span>Confidence: {Math.round(confidence * 100)}%</span>}
        {run.needs_human_review && <span className="font-semibold text-red-800">Flagged for human review</span>}
      </div>
      {run.error && <p role="alert" className="mb-2 text-sm text-red-800">{run.error}</p>}
      <dl className="space-y-2 text-sm">
        {entries.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs font-semibold uppercase tracking-wide text-ai">{label(k)}</dt>
            <dd><Value v={v} /></dd>
          </div>
        ))}
      </dl>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-ink-soft">
        <span>{refs.length} evidence reference{refs.length === 1 ? "" : "s"}</span>
        <button onClick={() => setTrace((t) => !t)} aria-expanded={trace} className="text-ai underline">
          {trace ? "Hide" : "Show"} tool trace ({run.trace.length})
        </button>
      </div>
      {trace && (
        <ol className="mt-2 space-y-1 rounded bg-white/70 p-2 font-mono text-xs">
          {run.trace.map((t, i) => (
            <li key={i}>{String(t.type)}{t.tool ? `: ${String(t.tool)}` : ""}{typeof t.ms === "number" ? ` (${t.ms} ms)` : ""}</li>
          ))}
        </ol>
      )}
    </AiBlock>
  );
}
