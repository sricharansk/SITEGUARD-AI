"use client";

// Corrective and preventive actions: review (approve / modify / reject with a reason), progress (start /
// complete, assignee) and independent verification. Buttons appear only when the caller's permissions allow
// the step; the API checks every call again and its refusal is shown inline.
import Link from "next/link";
import { useId, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { formatDate, formatDateTime, humanize, isOverdue, roleLabel } from "@/lib/format";
import { useMutation } from "@/lib/hooks";
import {
  canReviewAction,
  canUpdateProgress,
  canVerify,
  isActiveAction,
  reviewPermissionFor,
  type PermissionList,
} from "@/lib/permissions";
import type { ApprovalEvent, CapaAction, CapaBoardRow, Evidence, Member, VerificationRecord } from "@/lib/types";
import { AiBadge, ApprovalBadge, Badge, CriticalBadge, HumanBadge, SeverityBadge, StatusBadge, WorkBadge } from "../badges";
import { AlertIcon, UserIcon } from "../icons";
import { InlineError } from "../states";
import { describeRef, type RefIndex } from "../ai/refs";
import { personName, ROLES, type People } from "./people";

type ActionFields = Pick<CapaAction, "title" | "description" | "owner_role" | "due_date" | "verification_criteria">;

/** Fields a reviewer changed, in the shape POST /capa/{id}/review expects for MODIFY. */
export function changedFields(original: ActionFields, edited: ActionFields): Partial<ActionFields> {
  const changes: Partial<ActionFields> = {};
  (Object.keys(edited) as (keyof ActionFields)[]).forEach((key) => {
    const before = original[key] ?? "";
    const after = (edited[key] ?? "").trim();
    if (after !== before && !(after === "" && before === "")) {
      (changes as Record<string, string | null>)[key] = after === "" ? null : after;
    }
  });
  return changes;
}

function ReviewForm({ action, onChanged }: { action: CapaAction; onChanged: (message?: string) => void }) {
  const id = useId();
  const mutation = useMutation();
  const [reason, setReason] = useState("");
  const [modifying, setModifying] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [edit, setEdit] = useState<ActionFields>({
    title: action.title,
    description: action.description,
    owner_role: action.owner_role ?? "",
    due_date: action.due_date ?? "",
    verification_criteria: action.verification_criteria,
  });

  async function submit(decision: "APPROVE" | "MODIFY" | "REJECT") {
    setLocalError(null);
    if (!reason.trim()) {
      setLocalError("A reason is required for every review decision.");
      return;
    }
    const body: { decision: string; reason: string; changes?: Partial<ActionFields> } = { decision, reason: reason.trim() };
    if (decision === "MODIFY") {
      const changes = changedFields(
        {
          title: action.title,
          description: action.description,
          owner_role: action.owner_role ?? "",
          due_date: action.due_date ?? "",
          verification_criteria: action.verification_criteria,
        },
        edit,
      );
      if (Object.keys(changes).length === 0) {
        setLocalError("Change at least one field, or approve the action as proposed.");
        return;
      }
      body.changes = changes;
    }
    const verb = decision === "APPROVE" ? "approved" : decision === "MODIFY" ? "modified and approved" : "rejected";
    const message = `“${action.title}” ${verb}.`;
    const done = await mutation.run(() => api(`/capa/${action.id}/review`, { method: "POST", body }), message);
    if (done) onChanged(message);
  }

  const field = (key: keyof ActionFields, label: string, type: "text" | "date" | "textarea" = "text") => (
    <div>
      <label htmlFor={`${id}-${key}`} className="field-label">
        {label}
      </label>
      {type === "textarea" ? (
        <textarea
          id={`${id}-${key}`}
          className="input min-h-16"
          value={edit[key] ?? ""}
          onChange={(e) => setEdit((s) => ({ ...s, [key]: e.target.value }))}
        />
      ) : (
        <input
          id={`${id}-${key}`}
          type={type}
          className="input"
          value={edit[key] ?? ""}
          onChange={(e) => setEdit((s) => ({ ...s, [key]: e.target.value }))}
        />
      )}
    </div>
  );

  return (
    <form
      className="mt-3 rounded border border-sky-300 bg-sky-50/60 p-3"
      onSubmit={(e: FormEvent) => e.preventDefault()}
      aria-label={`Review: ${action.title}`}
    >
      <p className="mb-2 flex items-center gap-1 text-xs font-semibold text-sky-950">
        <UserIcon size={12} /> Human review decision
        {action.critical ? " (critical: HSE manager approval)" : ""}
      </p>
      {modifying ? (
        <div className="mb-3 grid gap-2 sm:grid-cols-2">
          <div className="sm:col-span-2">{field("title", "Title")}</div>
          <div className="sm:col-span-2">{field("description", "Description", "textarea")}</div>
          <div>
            <label htmlFor={`${id}-owner_role`} className="field-label">
              Owner role
            </label>
            <select
              id={`${id}-owner_role`}
              className="input"
              value={edit.owner_role ?? ""}
              onChange={(e) => setEdit((s) => ({ ...s, owner_role: e.target.value }))}
            >
              <option value="">Not set</option>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {roleLabel(r)}
                </option>
              ))}
            </select>
          </div>
          {field("due_date", "Due date", "date")}
          <div className="sm:col-span-2">{field("verification_criteria", "Verification criteria", "textarea")}</div>
        </div>
      ) : null}
      <label htmlFor={`${id}-reason`} className="field-label">
        Review reason (required)
      </label>
      <textarea
        id={`${id}-reason`}
        className="input min-h-14"
        value={reason}
        maxLength={2000}
        onChange={(e) => setReason(e.target.value)}
        aria-describedby={localError ? `${id}-local-error` : undefined}
      />
      <div className="mt-2 flex flex-wrap gap-2">
        {modifying ? (
          <>
            <button type="button" className="btn-primary btn-sm" disabled={mutation.pending} onClick={() => submit("MODIFY")}>
              Save changes and approve
            </button>
            <button type="button" className="btn-secondary btn-sm" onClick={() => setModifying(false)}>
              Cancel changes
            </button>
          </>
        ) : (
          <>
            <button type="button" className="btn-approve btn-sm" disabled={mutation.pending} onClick={() => submit("APPROVE")}>
              Approve
            </button>
            <button type="button" className="btn-secondary btn-sm" onClick={() => setModifying(true)}>
              Modify…
            </button>
            <button type="button" className="btn-danger btn-sm" disabled={mutation.pending} onClick={() => submit("REJECT")}>
              Reject
            </button>
          </>
        )}
      </div>
      {localError ? (
        <p id={`${id}-local-error`} role="alert" className="mt-2 text-sm font-medium text-red-800">
          {localError}
        </p>
      ) : null}
      <InlineError error={mutation.error} />
    </form>
  );
}

function ProgressForm({
  action,
  members,
  onChanged,
}: {
  action: CapaAction;
  members: Member[] | undefined;
  onChanged: (message?: string) => void;
}) {
  const id = useId();
  const mutation = useMutation();
  const [assignee, setAssignee] = useState(action.assignee_id ?? "");
  const [note, setNote] = useState("");

  async function send(workStatus: "IN_PROGRESS" | "COMPLETED" | null) {
    const body: Record<string, string> = {};
    if (workStatus) body.work_status = workStatus;
    if (assignee && assignee !== action.assignee_id) body.assignee_id = assignee;
    if (note.trim()) body.note = note.trim();
    const message = workStatus === "IN_PROGRESS" ? "Work started." : workStatus === "COMPLETED" ? "Marked complete; awaiting verification." : "Assignee saved.";
    const done = await mutation.run(() => api(`/capa/${action.id}/progress`, { method: "PATCH", body }), message);
    if (done) {
      setNote("");
      onChanged(`“${action.title}”: ${message}`);
    }
  }

  const canStart = action.work_status === "NOT_STARTED" || action.work_status === "VERIFICATION_FAILED";
  return (
    <form className="mt-3 rounded border border-slate-300 bg-slate-50 p-3" onSubmit={(e) => e.preventDefault()} aria-label={`Progress: ${action.title}`}>
      <p className="mb-2 text-xs font-semibold text-slate-800">Work progress</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-assignee`} className="field-label">
            Assignee
          </label>
          <select id={`${id}-assignee`} className="input" value={assignee} onChange={(e) => setAssignee(e.target.value)}>
            {!action.assignee_id ? <option value="">Unassigned</option> : null}
            {(members ?? []).map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.full_name}
              </option>
            ))}
          </select>
          {!members ? <p className="field-hint">People could not be loaded; you can still update the status.</p> : null}
        </div>
        <div>
          <label htmlFor={`${id}-note`} className="field-label">
            Progress note (optional)
          </label>
          <input id={`${id}-note`} className="input" value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {canStart ? (
          <button type="button" className="btn-secondary btn-sm" disabled={mutation.pending} onClick={() => send("IN_PROGRESS")}>
            Start work
          </button>
        ) : null}
        <button type="button" className="btn-primary btn-sm" disabled={mutation.pending} onClick={() => send("COMPLETED")}>
          Mark complete
        </button>
        <button
          type="button"
          className="btn-secondary btn-sm"
          disabled={mutation.pending || !assignee || assignee === action.assignee_id}
          onClick={() => send(null)}
        >
          Save assignee
        </button>
      </div>
      <InlineError error={mutation.error} />
    </form>
  );
}

function VerifyForm({
  action,
  meId,
  evidence,
  onChanged,
}: {
  action: CapaAction;
  meId: string | undefined;
  evidence: Evidence[] | undefined;
  onChanged: (message?: string) => void;
}) {
  const id = useId();
  const mutation = useMutation();
  const [effective, setEffective] = useState<"yes" | "no" | "">("");
  const [notes, setNotes] = useState("");
  const [evidenceId, setEvidenceId] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const isAssignee = Boolean(meId && action.assignee_id === meId);

  if (isAssignee) {
    return (
      <p className="mt-3 flex items-center gap-1.5 rounded border border-slate-300 bg-slate-50 px-3 py-2 text-xs text-slate-700">
        <AlertIcon size={12} /> You are the assignee, so someone else must verify this action.
      </p>
    );
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLocalError(null);
    if (!effective) return setLocalError("Choose whether the action was effective.");
    if (!notes.trim()) return setLocalError("Verification notes are required.");
    const body = { effective: effective === "yes", notes: notes.trim(), evidence_id: evidenceId || null };
    const message =
      effective === "yes" ? "Verified effective." : "Recorded as not effective; the action reopens for more work.";
    const done = await mutation.run(() => api(`/capa/${action.id}/verify`, { method: "POST", body }), message);
    if (done) onChanged(`“${action.title}”: ${message}`);
  }

  return (
    <form className="mt-3 rounded border border-sky-300 bg-sky-50/60 p-3" onSubmit={onSubmit} aria-label={`Verify: ${action.title}`}>
      <fieldset>
        <legend className="mb-1 flex items-center gap-1 text-xs font-semibold text-sky-950">
          <UserIcon size={12} /> Independent verification against: {action.verification_criteria}
        </legend>
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-1.5">
            <input type="radio" name={`${id}-effective`} value="yes" checked={effective === "yes"} onChange={() => setEffective("yes")} />
            Effective
          </label>
          <label className="flex items-center gap-1.5">
            <input type="radio" name={`${id}-effective`} value="no" checked={effective === "no"} onChange={() => setEffective("no")} />
            Not effective
          </label>
        </div>
      </fieldset>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-notes`} className="field-label">
            Verification notes (required)
          </label>
          <textarea id={`${id}-notes`} className="input min-h-14" value={notes} maxLength={5000} onChange={(e) => setNotes(e.target.value)} />
        </div>
        {evidence && evidence.length > 0 ? (
          <div>
            <label htmlFor={`${id}-evidence`} className="field-label">
              Supporting evidence (optional)
            </label>
            <select id={`${id}-evidence`} className="input" value={evidenceId} onChange={(e) => setEvidenceId(e.target.value)}>
              <option value="">None</option>
              {evidence.map((ev) => (
                <option key={ev.id} value={ev.id}>
                  {ev.filename}
                </option>
              ))}
            </select>
          </div>
        ) : null}
      </div>
      <button type="submit" className="btn-primary btn-sm mt-2" disabled={mutation.pending}>
        Record verification
      </button>
      {localError ? (
        <p role="alert" className="mt-2 text-sm font-medium text-red-800">
          {localError}
        </p>
      ) : null}
      <InlineError error={mutation.error} />
    </form>
  );
}

const DECISION_TEXT: Record<string, string> = {
  APPROVE: "Approved",
  MODIFY: "Modified and approved",
  REJECT: "Rejected",
};

function History({
  approvals,
  verifications,
  people,
}: {
  approvals: ApprovalEvent[];
  verifications: VerificationRecord[];
  people: People;
}) {
  if (approvals.length === 0 && verifications.length === 0) return null;
  const items = [
    ...approvals.map((a) => ({
      key: a.id,
      at: a.created_at,
      text: `${DECISION_TEXT[a.decision] ?? humanize(a.decision)} by ${personName(people, a.reviewer_id)}`,
      detail: a.reason,
    })),
    ...verifications.map((v) => ({
      key: v.id,
      at: v.created_at,
      text: `Verified ${v.effective ? "effective" : "NOT effective"} by ${personName(people, v.verifier_id)}`,
      detail: v.notes,
    })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  return (
    <div className="mt-3 border-l-4 border-sky-600 pl-3">
      <p className="kicker text-sky-900">Human decisions</p>
      <ul className="mt-1 space-y-1">
        {items.map((item) => (
          <li key={item.key} className="text-xs">
            <span className="font-semibold text-slate-900">{item.text}</span>{" "}
            <span className="text-slate-500">{formatDateTime(item.at)}</span>
            <span className="block text-slate-700">“{item.detail}”</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CapaActionCard({
  action,
  permissions,
  meId,
  members,
  people,
  approvals = [],
  verifications = [],
  evidence,
  refIndex,
  incident,
  onChanged,
}: {
  action: CapaAction;
  permissions: PermissionList;
  meId: string | undefined;
  members: Member[] | undefined;
  people: People;
  approvals?: ApprovalEvent[];
  verifications?: VerificationRecord[];
  evidence?: Evidence[];
  refIndex?: RefIndex;
  incident?: CapaBoardRow["incident"];
  onChanged: (message?: string) => void;
}) {
  const titleId = useId();
  const overdue = isActiveAction(action) && isOverdue(action.due_date) && !["COMPLETED", "VERIFIED"].includes(action.work_status);
  const reviewable = canReviewAction(permissions, action);
  const refs = action.evidence_refs ?? [];
  return (
    <article
      aria-labelledby={titleId}
      data-testid="capa-action"
      className={`rounded-md border bg-white p-3 ${action.ai_generated && action.approval_status === "PENDING_REVIEW" ? "border-2 border-dashed border-violet-400" : "border-slate-200"}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          {incident ? (
            <p className="mb-0.5 flex flex-wrap items-center gap-1.5 text-xs">
              <Link className="link mono" href={`/incidents/${incident.id}#capa`}>
                {incident.reference}
              </Link>
              <span className="text-slate-700">{incident.title}</span>
              <SeverityBadge severity={incident.severity} />
              <StatusBadge status={incident.status} />
            </p>
          ) : null}
          <h3 id={titleId} className="font-semibold text-slate-900">
            {action.title}
          </h3>
        </div>
        <div className="flex flex-wrap items-center gap-1">
          <Badge>{humanize(action.action_type)}</Badge>
          {action.ai_generated ? <AiBadge /> : <HumanBadge />}
          {action.critical ? <CriticalBadge /> : null}
          <ApprovalBadge status={action.approval_status} />
          {isActiveAction(action) ? <WorkBadge status={action.work_status} /> : null}
        </div>
      </div>
      {action.ai_generated && action.approval_status === "PENDING_REVIEW" ? (
        <p className="mt-1 text-xs font-medium text-violet-900">AI decision support, needs human review before any work starts.</p>
      ) : null}
      <p className="mt-1.5 text-slate-800">{action.description}</p>
      <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
        <div>
          <dt className="kicker">Owner role</dt>
          <dd>{roleLabel(action.owner_role)}</dd>
        </div>
        <div>
          <dt className="kicker">Assignee</dt>
          <dd>{personName(people, action.assignee_id)}</dd>
        </div>
        <div>
          <dt className="kicker">Due</dt>
          <dd className={overdue ? "font-semibold text-red-800" : undefined}>
            {overdue ? <AlertIcon size={12} className="mr-1 inline" /> : null}
            {formatDate(action.due_date)}
            {overdue ? " (overdue)" : ""}
          </dd>
        </div>
        <div className="sm:col-span-1">
          <dt className="kicker">Verification criteria</dt>
          <dd>{action.verification_criteria}</dd>
        </div>
      </dl>
      {action.ai_generated && refs.length > 0 && refIndex ? (
        <p className="mt-2 text-xs text-slate-600">
          Based on:{" "}
          {refs.map((r) => describeRef(r, refIndex).label).join("; ")}
        </p>
      ) : null}

      {action.approval_status === "PENDING_REVIEW" && !reviewable ? (
        <p className="mt-3 text-xs text-slate-600">
          Awaiting review by someone with {reviewPermissionFor(action) === "APPROVE_CRITICAL" ? "HSE manager (critical) approval" : "CAPA approval"} rights.
        </p>
      ) : null}
      {reviewable ? <ReviewForm action={action} onChanged={onChanged} /> : null}
      {canUpdateProgress(permissions, action) ? <ProgressForm action={action} members={members} onChanged={onChanged} /> : null}
      {canVerify(permissions, action) ? <VerifyForm action={action} meId={meId} evidence={evidence} onChanged={onChanged} /> : null}
      <History approvals={approvals} verifications={verifications} people={people} />
    </article>
  );
}

export function ProposeActionForm({
  incidentId,
  members,
  onChanged,
}: {
  incidentId: string;
  members: Member[] | undefined;
  onChanged: (message?: string) => void;
}) {
  const id = useId();
  const mutation = useMutation();
  const [open, setOpen] = useState(false);
  const empty = {
    action_type: "CORRECTIVE",
    title: "",
    description: "",
    owner_role: "",
    assignee_id: "",
    due_date: "",
    verification_criteria: "",
    critical: false,
  };
  const [form, setForm] = useState(empty);
  const [localError, setLocalError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLocalError(null);
    if (form.title.trim().length < 3 || form.description.trim().length < 3 || form.verification_criteria.trim().length < 3) {
      setLocalError("Title, description and verification criteria need at least 3 characters each.");
      return;
    }
    const body = {
      action_type: form.action_type,
      title: form.title.trim(),
      description: form.description.trim(),
      owner_role: form.owner_role || null,
      assignee_id: form.assignee_id || null,
      due_date: form.due_date || null,
      verification_criteria: form.verification_criteria.trim(),
      critical: form.critical,
    };
    const done = await mutation.run(
      () => api(`/incidents/${incidentId}/capa`, { method: "POST", body }),
      "Action added; it now awaits review.",
    );
    if (done) {
      setForm(empty);
      setOpen(false);
      onChanged("Action added; it now awaits review.");
    }
  }

  if (!open) {
    return (
      <div>
        <button type="button" className="btn-secondary btn-sm" onClick={() => setOpen(true)}>
          Add a human-authored action
        </button>
        </div>
    );
  }
  const text = (key: "title" | "description" | "verification_criteria", label: string, area = false) => (
    <div className={area ? "sm:col-span-2" : undefined}>
      <label htmlFor={`${id}-${key}`} className="field-label">
        {label}
      </label>
      {area ? (
        <textarea id={`${id}-${key}`} className="input min-h-14" value={form[key]} onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))} />
      ) : (
        <input id={`${id}-${key}`} className="input" value={form[key]} onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))} />
      )}
    </div>
  );
  return (
    <form onSubmit={onSubmit} className="rounded border border-sky-300 bg-sky-50/60 p-3" aria-label="New human-authored action">
      <p className="mb-2 text-xs font-semibold text-sky-950">New action (goes to review like AI proposals)</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-type`} className="field-label">
            Type
          </label>
          <select id={`${id}-type`} className="input" value={form.action_type} onChange={(e) => setForm((f) => ({ ...f, action_type: e.target.value }))}>
            <option value="CORRECTIVE">Corrective</option>
            <option value="PREVENTIVE">Preventive</option>
          </select>
        </div>
        {text("title", "Title")}
        {text("description", "Description", true)}
        <div>
          <label htmlFor={`${id}-owner`} className="field-label">
            Owner role
          </label>
          <select id={`${id}-owner`} className="input" value={form.owner_role} onChange={(e) => setForm((f) => ({ ...f, owner_role: e.target.value }))}>
            <option value="">Not set</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {roleLabel(r)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-assignee`} className="field-label">
            Assignee
          </label>
          <select id={`${id}-assignee`} className="input" value={form.assignee_id} onChange={(e) => setForm((f) => ({ ...f, assignee_id: e.target.value }))}>
            <option value="">Unassigned</option>
            {(members ?? []).map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.full_name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-due`} className="field-label">
            Due date
          </label>
          <input id={`${id}-due`} type="date" className="input" value={form.due_date} onChange={(e) => setForm((f) => ({ ...f, due_date: e.target.value }))} />
        </div>
        <label className="flex items-center gap-2 self-end pb-1.5 text-sm">
          <input type="checkbox" checked={form.critical} onChange={(e) => setForm((f) => ({ ...f, critical: e.target.checked }))} />
          Critical (needs HSE manager approval)
        </label>
        {text("verification_criteria", "Verification criteria", true)}
      </div>
      <div className="mt-2 flex gap-2">
        <button type="submit" className="btn-primary btn-sm" disabled={mutation.pending}>
          Add action
        </button>
        <button type="button" className="btn-secondary btn-sm" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      {localError ? (
        <p role="alert" className="mt-2 text-sm font-medium text-red-800">
          {localError}
        </p>
      ) : null}
      <InlineError error={mutation.error} />
    </form>
  );
}

