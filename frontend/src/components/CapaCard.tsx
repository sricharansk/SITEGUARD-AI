"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Capa } from "@/lib/types";
import { AiBlock, StatusPill, fmtDate, label } from "./ui";

// Review is a human decision with a mandatory reason. The server re-checks permissions (critical actions need APPROVE_CRITICAL).
export default function CapaCard({ capa, permissions, onChanged }: { capa: Capa; permissions: string[]; onChanged: () => void }) {
  const [decision, setDecision] = useState<"APPROVE" | "REJECT" | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pending = capa.approval_status === "PENDING_REVIEW";
  const needed = capa.critical ? "APPROVE_CRITICAL" : "APPROVE_CAPA";
  const canReview = permissions.includes(needed);

  async function submit() {
    if (!decision) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/capa/${capa.id}/review`, { method: "POST", body: { decision, reason } });
      setDecision(null);
      setReason("");
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const body = (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-surface-alt px-1.5 py-0.5 text-xs font-semibold">{label(capa.action_type)}</span>
        {capa.critical && <span className="rounded bg-red-700 px-1.5 py-0.5 text-xs font-semibold text-white">Critical: HSE manager approval</span>}
        <StatusPill value={capa.approval_status} />
        {!pending && <span className="text-xs text-ink-soft">Work: {label(capa.work_status)}</span>}
      </div>
      <h4 className="mt-2 font-semibold">{capa.title}</h4>
      <p className="mt-1 text-sm text-ink-soft">{capa.description}</p>
      <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
        <div><dt className="inline text-ink-soft">Owner: </dt><dd className="inline">{capa.owner_role ? label(capa.owner_role) : "Unassigned"}</dd></div>
        <div><dt className="inline text-ink-soft">Due: </dt><dd className="inline">{fmtDate(capa.due_date)}</dd></div>
        <div className="sm:col-span-2"><dt className="inline text-ink-soft">Verification: </dt><dd className="inline">{capa.verification_criteria}</dd></div>
      </dl>
      {pending && (
        <div className="mt-3 border-t border-ai-line pt-3">
          {!canReview ? (
            <p className="text-xs text-ink-soft">You do not have permission to review this action ({needed.replace("_", " ").toLowerCase()} required).</p>
          ) : decision === null ? (
            <div className="flex gap-2">
              <button onClick={() => setDecision("APPROVE")} className="rounded bg-brand px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-dark">Approve…</button>
              <button onClick={() => setDecision("REJECT")} className="rounded border border-surface-line bg-surface px-3 py-1.5 text-sm font-semibold hover:bg-surface-alt">Reject…</button>
            </div>
          ) : (
            <div className="space-y-2">
              <label className="block text-sm font-medium">
                Reason for {decision === "APPROVE" ? "approving" : "rejecting"} (recorded in the audit trail)
                <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
                  className="mt-1 w-full rounded border border-surface-line px-2 py-1.5 text-sm" />
              </label>
              {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
              <div className="flex gap-2">
                <button disabled={busy || !reason.trim()} onClick={submit}
                  className="rounded bg-brand px-3 py-1.5 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-50">
                  {busy ? "Saving…" : `Confirm ${decision === "APPROVE" ? "approval" : "rejection"}`}
                </button>
                <button onClick={() => { setDecision(null); setError(null); }} className="rounded px-3 py-1.5 text-sm hover:bg-surface-alt">Cancel</button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );

  return capa.ai_generated && pending ? (
    <AiBlock title="Proposed action — needs human review">{body}</AiBlock>
  ) : (
    <div className="rounded-md border border-surface-line p-3">{body}</div>
  );
}
