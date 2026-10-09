"use client";

// Run the bounded AI investigation and show each agent's output as decision support.
import { useState } from "react";
import { api, toApiError, type ApiError } from "@/lib/api";
import { agentsRunnableFrom, can, type PermissionList } from "@/lib/permissions";
import type { AgentRun, IncidentStatus, InvestigationResult } from "@/lib/types";
import { AGENT_TITLES, AiPanel } from "../ai/ai-panel";
import { InvestigationProgress } from "../ai/investigation-progress";
import type { RefIndex } from "../ai/refs";
import { SparkleIcon } from "../icons";
import { EmptyState, InlineError, PartialNotice } from "../states";
import { humanize } from "@/lib/format";

const ORDER = ["triage", "safety", "quality", "rca", "compliance", "capa"];

export function InvestigationPanel({
  incidentId,
  status,
  runs,
  refIndex,
  permissions,
  onChanged,
}: {
  incidentId: string;
  status: IncidentStatus;
  runs: AgentRun[];
  refIndex: RefIndex;
  permissions: PermissionList;
  onChanged: () => void;
}) {
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [result, setResult] = useState<InvestigationResult | undefined>();
  const [error, setError] = useState<ApiError | undefined>();
  const mayRun = can(permissions, "RUN_AGENTS");
  const runnable = agentsRunnableFrom(status);

  async function run() {
    setError(undefined);
    setResult(undefined);
    setStartedAt(Date.now());
    try {
      const data = await api<InvestigationResult>(`/incidents/${incidentId}/investigate`, { method: "POST" });
      setResult(data);
      onChanged();
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setStartedAt(null);
    }
  }

  const sorted = [...runs].sort((a, b) => ORDER.indexOf(a.agent) - ORDER.indexOf(b.agent));
  const failed = sorted.filter((r) => r.status !== "SUCCEEDED");
  const flagged = sorted.filter((r) => r.needs_human_review && r.status === "SUCCEEDED");

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        {mayRun ? (
          <button type="button" className="btn-ai" onClick={run} disabled={startedAt !== null || !runnable}>
            <SparkleIcon size={14} />
            {startedAt !== null ? "Investigation running…" : runs.length > 0 ? "Re-run AI investigation" : "Run AI investigation"}
          </button>
        ) : null}
        <p className="text-xs text-slate-600">
          {!mayRun
            ? "Your role can read AI output but not run agents."
            : !runnable
              ? `Agents run only before actions are under way; this incident is ${humanize(status)}.`
              : runs.length > 0
                ? "Re-running replaces AI proposals nobody has reviewed yet."
                : "Six bounded agents propose; people approve. Output appears below."}
        </p>
      </div>
      <InvestigationProgress startedAt={startedAt} result={result} error={error} />
      <InlineError error={error} />

      {sorted.length === 0 ? (
        startedAt === null ? (
          <EmptyState title="No AI investigation yet">
            The manual workflow is always available: record a human risk assessment, add actions and move the incident
            through its lifecycle.
          </EmptyState>
        ) : null
      ) : (
        <>
          <PartialNotice
            title="Partial AI result"
            items={failed.map((r) => `${AGENT_TITLES[r.agent] ?? r.agent} failed; continue manually for that part.`)}
          />
          {flagged.length > 0 ? (
            <p className="text-xs text-amber-900">
              {flagged.length} output(s) flagged for extra human review (low confidence, removed citations or suspicious
              sources).
            </p>
          ) : null}
          <div className="space-y-3">
            {sorted.map((r) => (
              <AiPanel key={r.id} run={r} refIndex={refIndex} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
