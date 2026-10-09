"use client";

// CAPA board and review queue (GET /projects/{id}/capa). The first tab is the human review queue.
import { useMemo, useState, type KeyboardEvent } from "react";
import { useAppContext } from "@/components/app-context";
import { CapaActionCard } from "@/components/incident/capa";
import { peopleIndex } from "@/components/incident/people";
import { PageHeader } from "@/components/layout";
import { EmptyState, ErrorState, LoadingState, PartialNotice, SuccessNote } from "@/components/states";
import { useApi } from "@/lib/hooks";
import type { Query } from "@/lib/api";
import type { CapaBoardRow, Member } from "@/lib/types";

const TABS: { key: string; label: string; query: Query; empty: string }[] = [
  { key: "review", label: "Pending review", query: { approval_status: "PENDING_REVIEW" }, empty: "Nothing is waiting for review." },
  { key: "approved", label: "Approved", query: { approval_status: "APPROVED" }, empty: "No approved actions." },
  { key: "modified", label: "Modified", query: { approval_status: "MODIFIED" }, empty: "No modified actions." },
  { key: "progress", label: "In progress", query: { work_status: "IN_PROGRESS" }, empty: "No actions in progress." },
  { key: "verify", label: "Awaiting verification", query: { work_status: "COMPLETED" }, empty: "No completed actions awaiting verification." },
  { key: "failed", label: "Verification failed", query: { work_status: "VERIFICATION_FAILED" }, empty: "No failed verifications." },
  { key: "verified", label: "Verified", query: { work_status: "VERIFIED" }, empty: "No verified actions yet." },
  { key: "rejected", label: "Rejected", query: { approval_status: "REJECTED" }, empty: "No rejected proposals." },
  { key: "superseded", label: "Superseded", query: { approval_status: "SUPERSEDED" }, empty: "No superseded proposals." },
  { key: "all", label: "All", query: {}, empty: "No actions on this project yet." },
];

export default function ReviewPage() {
  const { project, me } = useAppContext();
  const [tabKey, setTabKey] = useState("review");
  const [notice, setNotice] = useState<string | null>(null);
  const tab = TABS.find((t) => t.key === tabKey) ?? TABS[0]!;
  const rows = useApi<CapaBoardRow[]>(project ? `/projects/${project.id}/capa` : null, tab.query);
  const members = useApi<Member[]>(project ? `/projects/${project.id}/members` : null);
  const people = useMemo(() => peopleIndex(members.data), [members.data]);

  if (!project) return null;

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = TABS.findIndex((t) => t.key === tabKey);
    const next = event.key === "ArrowRight" ? index + 1 : event.key === "ArrowLeft" ? index - 1 : null;
    if (next === null) return;
    event.preventDefault();
    const target = TABS[(next + TABS.length) % TABS.length]!;
    setTabKey(target.key);
    document.getElementById(`tab-${target.key}`)?.focus();
  }

  return (
    <>
      <PageHeader
        kicker={`${project.code} · ${project.name}`}
        title="CAPA board and review queue"
        subtitle="Every corrective and preventive action on this project. AI proposals start in the review queue; nothing is worked until a person approves it."
      />
      <div role="tablist" aria-label="Action status" className="mb-3 flex flex-wrap gap-1" onKeyDown={onKeyDown}>
        {TABS.map((t) => {
          const selected = t.key === tabKey;
          return (
            <button
              key={t.key}
              id={`tab-${t.key}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls="capa-tabpanel"
              tabIndex={selected ? 0 : -1}
              onClick={() => {
                setTabKey(t.key);
                setNotice(null);
              }}
              className={`rounded border px-2.5 py-1 text-sm font-medium ${
                selected ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {t.label}
              {selected && rows.data ? ` (${rows.data.length})` : ""}
            </button>
          );
        })}
      </div>
      <div id="capa-tabpanel" role="tabpanel" aria-labelledby={`tab-${tab.key}`} className="space-y-3">
        <SuccessNote message={notice} />
        {members.status === "error" ? (
          <PartialNotice items={["People on the project could not be loaded; assignees show as IDs."]} />
        ) : null}
        {rows.status === "error" && rows.error ? (
          <ErrorState error={rows.error} onRetry={rows.reload} what="actions on this project" />
        ) : !rows.data ? (
          <LoadingState label="Loading actions…" />
        ) : rows.data.length === 0 ? (
          <div className="card">
            <EmptyState title={tab.empty} />
          </div>
        ) : (
          rows.data.map((row) => (
            <CapaActionCard
              key={row.id}
              action={row}
              incident={row.incident}
              permissions={project.permissions}
              meId={me?.id}
              members={members.data}
              people={people}
              onChanged={(message) => {
                setNotice(message ?? null);
                rows.reload();
              }}
            />
          ))
        )}
      </div>
    </>
  );
}
