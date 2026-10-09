"use client";

// Manual lifecycle control (works when AI is unavailable) and closure with the server's close blockers.
import { useId, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useMutation } from "@/lib/hooks";
import { can, canCloseIncident, manualTransitionTargets, type PermissionList } from "@/lib/permissions";
import type { Incident } from "@/lib/types";
import { AlertIcon, CheckIcon, LockIcon } from "../icons";
import { InlineError, SuccessNote } from "../states";

export function TransitionControl({
  incident,
  permissions,
  onChanged,
}: {
  incident: Incident;
  permissions: PermissionList;
  onChanged: () => void;
}) {
  const id = useId();
  const mutation = useMutation();
  const targets = manualTransitionTargets(permissions, incident.status);
  const [target, setTarget] = useState("");
  const [note, setNote] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  if (!can(permissions, "EDIT_INCIDENT")) {
    return <p className="text-xs text-slate-600">Your role cannot change the incident status.</p>;
  }
  if (targets.length === 0) {
    return (
      <p className="text-xs text-slate-600">
        No manual transitions from {humanize(incident.status)}
        {incident.status === "CLOSED" ? " (reopening needs the close permission)" : ""}.
      </p>
    );
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLocalError(null);
    if (!target) return setLocalError("Choose the new status.");
    if (!note.trim()) return setLocalError("A note is required for every status change.");
    const done = await mutation.run(
      () => api(`/incidents/${incident.id}/transition`, { method: "POST", body: { to_status: target, note: note.trim() } }),
      `Moved to ${humanize(target)}.`,
    );
    if (done) {
      setTarget("");
      setNote("");
      onChanged();
    }
  }

  return (
    <form onSubmit={onSubmit} aria-label="Manual status change">
      <div className="grid gap-2 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-target`} className="field-label">
            Move to
          </label>
          <select id={`${id}-target`} className="input" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value="">Choose…</option>
            {targets.map((t) => (
              <option key={t} value={t}>
                {humanize(t)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-note`} className="field-label">
            Note (required)
          </label>
          <input id={`${id}-note`} className="input" maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
      </div>
      <button type="submit" className="btn-secondary btn-sm mt-2" disabled={mutation.pending}>
        Apply status change
      </button>
      <p className="field-hint">Manual changes keep the workflow moving when AI is unavailable. Closing uses the control below.</p>
      {localError ? (
        <p role="alert" className="mt-2 text-sm font-medium text-red-800">
          {localError}
        </p>
      ) : null}
      <InlineError error={mutation.error} />
      <SuccessNote message={mutation.success} />
    </form>
  );
}

export function CloseControl({
  incident,
  blockers,
  permissions,
  onChanged,
}: {
  incident: Incident;
  blockers: string[];
  permissions: PermissionList;
  onChanged: () => void;
}) {
  const id = useId();
  const mutation = useMutation();
  const [note, setNote] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  if (incident.status === "CLOSED") {
    return (
      <p className="flex items-center gap-1.5 text-sm font-semibold text-emerald-800">
        <CheckIcon size={14} /> Closed after verification.
      </p>
    );
  }

  const allowed = canCloseIncident(permissions, incident);
  const criticalBlocked = can(permissions, "CLOSE_INCIDENT") && !allowed;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLocalError(null);
    if (!note.trim()) return setLocalError("A closure note is required.");
    const done = await mutation.run(
      () => api(`/incidents/${incident.id}/close`, { method: "POST", body: { note: note.trim() } }),
      "Incident closed.",
    );
    if (done) {
      setNote("");
      onChanged();
    }
  }

  return (
    <div className="space-y-2">
      {blockers.length > 0 ? (
        <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-amber-950" data-testid="close-blockers">
          <p className="flex items-center gap-1.5 text-sm font-semibold">
            <LockIcon size={14} /> Closure blocked
          </p>
          <ul className="mt-1 list-disc pl-5 text-sm">
            {blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="flex items-center gap-1.5 text-sm font-semibold text-emerald-800">
          <CheckIcon size={14} /> Ready to close: every approved action is verified effective.
        </p>
      )}
      {criticalBlocked ? (
        <p className="flex items-center gap-1.5 text-xs text-slate-700">
          <AlertIcon size={12} /> Closing a CRITICAL incident needs HSE manager approval (APPROVE_CRITICAL).
        </p>
      ) : null}
      {allowed ? (
        <form onSubmit={onSubmit} aria-label="Close incident">
          <label htmlFor={`${id}-note`} className="field-label">
            Closure note (required)
          </label>
          <textarea
            id={`${id}-note`}
            className="input min-h-14"
            maxLength={5000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            disabled={blockers.length > 0}
          />
          <button type="submit" className="btn-primary btn-sm mt-2" disabled={mutation.pending || blockers.length > 0}>
            Close incident
          </button>
          {localError ? (
            <p role="alert" className="mt-2 text-sm font-medium text-red-800">
              {localError}
            </p>
          ) : null}
          <InlineError error={mutation.error} />
          <SuccessNote message={mutation.success} />
        </form>
      ) : !criticalBlocked ? (
        <p className="text-xs text-slate-600">Closing needs the close permission (project manager or HSE manager).</p>
      ) : null}
    </div>
  );
}
