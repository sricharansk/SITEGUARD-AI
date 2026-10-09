// Turn evidence refs from agent output ("incident:<id>", "evidence:<id>", "chunk:<id>") into readable citations.
import type { AgentRun, Evidence, Incident } from "@/lib/types";
import { shortId } from "@/lib/format";

export interface Citation {
  ref: string;
  kind: "incident" | "evidence" | "chunk" | "unknown";
  label: string;
  /** Evidence id when the citation points to an uploaded file the user can download. */
  evidenceId?: string;
}

export interface RefIndex {
  incident?: Pick<Incident, "id" | "reference">;
  evidence: Map<string, Evidence>;
  chunkTitles: Map<string, string>;
}

export function buildRefIndex(incident: Pick<Incident, "id" | "reference"> | undefined, evidence: Evidence[], runs: AgentRun[]): RefIndex {
  const chunkTitles = new Map<string, string>();
  for (const run of runs) {
    const findings = (run.output as { findings?: unknown } | null)?.findings;
    if (!Array.isArray(findings)) continue;
    for (const f of findings) {
      if (f && typeof f === "object" && typeof f.source_ref === "string" && typeof f.source_title === "string") {
        chunkTitles.set(f.source_ref, f.source_title);
      }
    }
  }
  return { incident, evidence: new Map(evidence.map((e) => [e.id, e])), chunkTitles };
}

export function describeRef(ref: string, index: RefIndex): Citation {
  const sep = ref.indexOf(":");
  const kind = sep > 0 ? ref.slice(0, sep) : "";
  const id = sep > 0 ? ref.slice(sep + 1) : ref;
  if (kind === "incident") {
    const label =
      index.incident && index.incident.id === id ? `Incident report ${index.incident.reference}` : `Incident ${shortId(id)}`;
    return { ref, kind: "incident", label };
  }
  if (kind === "evidence") {
    const ev = index.evidence.get(id);
    return { ref, kind: "evidence", label: ev ? `Evidence: ${ev.filename}` : `Evidence ${shortId(id)}`, evidenceId: ev?.id };
  }
  if (kind === "chunk") {
    const title = index.chunkTitles.get(ref);
    return { ref, kind: "chunk", label: title ? `Document: ${title}` : `Document excerpt ${shortId(id)}` };
  }
  return { ref, kind: "unknown", label: ref };
}

/** Review reasons recorded by the agent framework (low confidence, removed citations, suspicious sources...). */
export function reviewReasons(run: AgentRun): string[] {
  const entry = run.trace.find((t) => t.type === "review_reasons");
  return Array.isArray(entry?.reasons) ? entry.reasons.filter((r): r is string => typeof r === "string") : [];
}

export function isFallback(provider: string): boolean {
  return provider.includes("fallback");
}
