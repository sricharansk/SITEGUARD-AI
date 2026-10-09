"use client";

// Audit log (GET /audit), for roles with VIEW_AUDIT. The page is hidden from navigation otherwise, and the API
// answers 403 to anyone without the permission, which is shown as the unauthorized state.
import Link from "next/link";
import { useId, useMemo, useState, type FormEvent } from "react";
import { useAppContext } from "@/components/app-context";
import { Badge } from "@/components/badges";
import { peopleIndex, personName } from "@/components/incident/people";
import { PageHeader } from "@/components/layout";
import { EmptyState, ErrorState, LoadingState, UnauthorizedState } from "@/components/states";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { meCan } from "@/lib/permissions";
import type { AuditEvent, Member } from "@/lib/types";

const LIMITS = [50, 100, 200, 500];

function Details({ details }: { details: Record<string, unknown> | null }) {
  if (!details || Object.keys(details).length === 0) return <span className="text-slate-400">—</span>;
  return (
    <details>
      <summary className="cursor-pointer text-xs text-slate-700">{Object.keys(details).join(", ")}</summary>
      <pre className="mono mt-1 max-w-md overflow-x-auto rounded bg-slate-50 p-2 whitespace-pre-wrap">
        {JSON.stringify(details, null, 2)}
      </pre>
    </details>
  );
}

export default function AuditPage() {
  const id = useId();
  const { me, project } = useAppContext();
  const allowed = meCan(me, "VIEW_AUDIT");
  const [entity, setEntity] = useState("");
  const [filter, setFilter] = useState({ entity_id: "", limit: 100 });
  const log = useApi<AuditEvent[]>(me && allowed ? "/audit" : null, filter);
  const members = useApi<Member[]>(project && allowed ? `/projects/${project.id}/members` : null);
  const people = useMemo(() => peopleIndex(members.data), [members.data]);

  const header = <PageHeader title="Audit log" subtitle="Every state change, approval, upload and agent run, with correlation IDs." />;
  if (!me) return <LoadingState />;
  if (!allowed) {
    return (
      <>
        {header}
        <UnauthorizedState what="the audit log (VIEW_AUDIT is required)" />
      </>
    );
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFilter((f) => ({ ...f, entity_id: entity.trim() }));
  }

  return (
    <>
      {header}
      <form onSubmit={onSubmit} className="card mb-4" aria-label="Audit filters">
        <div className="card-body flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1">
            <label htmlFor={`${id}-entity`} className="field-label">
              Entity ID (incident, action, evidence, document or user)
            </label>
            <input id={`${id}-entity`} className="input mono" value={entity} onChange={(e) => setEntity(e.target.value)} />
          </div>
          <div>
            <label htmlFor={`${id}-limit`} className="field-label">
              Show
            </label>
            <select
              id={`${id}-limit`}
              className="input"
              value={filter.limit}
              onChange={(e) => setFilter((f) => ({ ...f, limit: Number(e.target.value) }))}
            >
              {LIMITS.map((l) => (
                <option key={l} value={l}>
                  Latest {l}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" className="btn-primary">
            Apply
          </button>
          {filter.entity_id ? (
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setEntity("");
                setFilter((f) => ({ ...f, entity_id: "" }));
              }}
            >
              Clear
            </button>
          ) : null}
        </div>
      </form>
      <section className="card overflow-x-auto" aria-label="Audit events">
        {log.status === "error" && log.error ? (
          <ErrorState error={log.error} onRetry={log.reload} what="the audit log" />
        ) : !log.data ? (
          <LoadingState label="Loading audit events…" />
        ) : log.data.length === 0 ? (
          <EmptyState title="No audit events match" />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col">Actor</th>
                <th scope="col">Action</th>
                <th scope="col">Entity</th>
                <th scope="col">Details</th>
                <th scope="col">Correlation ID</th>
              </tr>
            </thead>
            <tbody>
              {log.data.map((a) => (
                <tr key={a.id}>
                  <td className="whitespace-nowrap">{formatDateTime(a.created_at)}</td>
                  <td>
                    {personName(people, a.actor_id)}
                    {a.actor_type !== "USER" ? (
                      <span className="ml-1">
                        <Badge tone="violet">{a.actor_type}</Badge>
                      </span>
                    ) : null}
                  </td>
                  <td className="mono">{a.action}</td>
                  <td>
                    <span className="text-xs text-slate-600">{a.entity_type}</span>{" "}
                    {a.entity_type === "incident" && a.entity_id ? (
                      <Link className="link mono" href={`/incidents/${a.entity_id}`}>
                        {a.entity_id.slice(0, 8)}
                      </Link>
                    ) : (
                      <code className="mono">{a.entity_id?.slice(0, 8) ?? "—"}</code>
                    )}
                  </td>
                  <td>
                    <Details details={a.details} />
                  </td>
                  <td>
                    <code className="mono text-slate-600">{a.correlation_id ?? "—"}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
