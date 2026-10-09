"use client";

// Current risk assessment, the 5x5 matrix and the human risk assessment form (POST /incidents/{id}/risk).
// The band always comes from the server's matrix; the preview here only reads the same matrix.
import { useId, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useMutation } from "@/lib/hooks";
import type { RiskAssessment, RiskMatrix as Matrix } from "@/lib/types";
import { RiskBadge } from "../badges";
import { SparkleIcon, UserIcon } from "../icons";
import { bandFor, RiskMatrix, type Cell } from "../risk-matrix";
import { InlineError, SuccessNote } from "../states";
import { personName, type People } from "./people";

export function RiskPanel({
  incidentId,
  risk,
  matrix,
  people,
  canAssess,
  onChanged,
}: {
  incidentId: string;
  risk: RiskAssessment | null;
  matrix: Matrix | undefined;
  people: People;
  canAssess: boolean;
  onChanged: () => void;
}) {
  const id = useId();
  const mutation = useMutation();
  const [cell, setCell] = useState<Cell | null>(null);
  const [rationale, setRationale] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const current = risk ? { likelihood: risk.likelihood, consequence: risk.consequence } : null;
  const human = risk?.inputs_source === "HUMAN";

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLocalError(null);
    if (!cell) return setLocalError("Choose likelihood and consequence.");
    if (!rationale.trim()) return setLocalError("Explain the basis for your assessment.");
    const saved = await mutation.run(
      () =>
        api<RiskAssessment>(`/incidents/${incidentId}/risk`, {
          method: "POST",
          body: { likelihood: cell.likelihood, consequence: cell.consequence, rationale: rationale.trim() },
        }),
      "Human risk assessment recorded.",
    );
    if (saved) {
      setRationale("");
      setCell(null);
      onChanged();
    }
  }

  const preview = cell && matrix ? bandFor(matrix, cell.likelihood, cell.consequence) : undefined;
  const select = (key: keyof Cell, label: string, labels: Record<string, string> | undefined) => (
    <div>
      <label htmlFor={`${id}-${key}`} className="field-label">
        {label}
      </label>
      <select
        id={`${id}-${key}`}
        className="input"
        value={cell?.[key] ?? ""}
        onChange={(e) => {
          const value = Number(e.target.value);
          setCell((c) => ({ likelihood: c?.likelihood ?? 1, consequence: c?.consequence ?? 1, [key]: value }));
        }}
      >
        {!cell ? <option value="">Choose…</option> : null}
        {[1, 2, 3, 4, 5].map((n) => (
          <option key={n} value={n}>
            {n} · {labels?.[String(n)] ?? ""}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
      <div className="min-w-0 space-y-3">
      {risk ? (
        <div className={`rounded border-l-4 px-3 py-2 ${human ? "border-sky-600 bg-sky-50" : "border-violet-500 bg-violet-50"}`}>
          <p className="flex flex-wrap items-center gap-2">
            <RiskBadge band={risk.band} score={risk.score} />
            <span className="text-sm">
              Likelihood {risk.likelihood} × consequence {risk.consequence} on matrix {risk.matrix_version}
            </span>
          </p>
          <p className="mt-1 flex items-center gap-1 text-xs font-semibold">
            {human ? (
              <>
                <UserIcon size={12} /> Human assessment by {personName(people, risk.assessed_by)}
              </>
            ) : (
              <>
                <SparkleIcon size={12} className="text-violet-700" /> Inputs suggested by AI (decision support, needs
                human review); scored by the deterministic matrix
              </>
            )}
            <span className="font-normal text-slate-600">· {formatDateTime(risk.created_at)}</span>
          </p>
          <p className="mt-1 text-xs text-slate-700">{risk.rationale}</p>
        </div>
      ) : (
        <p className="text-slate-600">No risk assessment yet. Run the AI investigation or record a human assessment.</p>
      )}
      {canAssess ? (
        <form onSubmit={onSubmit} className="rounded border border-sky-300 bg-sky-50/60 p-3" aria-label="Human risk assessment">
          <p className="mb-2 flex items-center gap-1 text-xs font-semibold text-sky-950">
            <UserIcon size={12} /> Record a human risk assessment (pick a matrix cell or use the lists)
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {select("likelihood", "Likelihood", matrix?.likelihood)}
            {select("consequence", "Consequence", matrix?.consequence)}
          </div>
          {preview && cell ? (
            <p className="mt-2 flex items-center gap-2 text-xs">
              Matrix result: <RiskBadge band={preview} score={cell.likelihood * cell.consequence} />
            </p>
          ) : null}
          <label htmlFor={`${id}-rationale`} className="field-label mt-2">
            Rationale (required)
          </label>
          <textarea
            id={`${id}-rationale`}
            className="input min-h-14"
            maxLength={2000}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
          />
          <button type="submit" className="btn-primary btn-sm mt-2" disabled={mutation.pending}>
            Record assessment
          </button>
          {localError ? (
            <p role="alert" className="mt-2 text-sm font-medium text-red-800">
              {localError}
            </p>
          ) : null}
          <InlineError error={mutation.error} />
          <SuccessNote message={mutation.success} />
        </form>
      ) : null}
      </div>
      {matrix ? (
        <div className="min-w-0 overflow-x-auto">
          <RiskMatrix matrix={matrix} current={current} selected={canAssess ? cell : null} onSelect={canAssess ? setCell : undefined} />
        </div>
      ) : null}
    </div>
  );
}
