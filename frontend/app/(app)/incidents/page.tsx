"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useAppContext } from "@/components/app-context";
import { DomainBadge, SeverityBadge, StatusBadge, SyntheticBadge } from "@/components/badges";
import { PageHeader } from "@/components/layout";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { formatDateTime, humanize } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { can } from "@/lib/permissions";
import { DOMAINS, INCIDENT_STATUSES, SEVERITIES, type Incident } from "@/lib/types";

interface Filters {
  status: string;
  severity: string;
  domain: string;
  q: string;
}

const EMPTY: Filters = { status: "", severity: "", domain: "", q: "" };

export default function IncidentsPage() {
  const { project } = useAppContext();
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [text, setText] = useState("");
  const list = useApi<Incident[]>(project ? `/projects/${project.id}/incidents` : null, {
    status: filters.status,
    severity: filters.severity,
    domain: filters.domain,
    q: filters.q,
  });

  if (!project) return null;
  const filtered = Object.values(filters).some(Boolean);

  function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFilters((f) => ({ ...f, q: text.trim() }));
  }
  function clear() {
    setText("");
    setFilters(EMPTY);
  }

  const select = (key: keyof Filters, label: string, options: readonly string[]) => (
    <div>
      <label htmlFor={`filter-${key}`} className="field-label">
        {label}
      </label>
      <select
        id={`filter-${key}`}
        className="input"
        value={filters[key]}
        onChange={(e) => setFilters((f) => ({ ...f, [key]: e.target.value }))}
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {humanize(o)}
          </option>
        ))}
      </select>
    </div>
  );

  return (
    <>
      <PageHeader
        kicker={`${project.code} · ${project.name}`}
        title="Incidents"
        subtitle="Safety incidents, near misses and quality observations for this project."
        actions={
          can(project.permissions, "CREATE_INCIDENT") ? (
            <Link href="/incidents/new" className="btn-primary">
              Report incident
            </Link>
          ) : null
        }
      />
      <section className="card mb-4" aria-label="Filters">
        <div className="card-body grid gap-3 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_auto]">
          <form onSubmit={onSearch} role="search" className="flex items-end gap-2">
            <div className="flex-1">
              <label htmlFor="filter-q" className="field-label">
                Search title, description or reference
              </label>
              <input
                id="filter-q"
                type="search"
                className="input"
                maxLength={200}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </div>
            <button type="submit" className="btn-secondary">
              Search
            </button>
          </form>
          {select("status", "Status", INCIDENT_STATUSES)}
          {select("severity", "Severity", SEVERITIES)}
          {select("domain", "Domain", DOMAINS)}
          <div className="flex items-end">
            <button type="button" className="btn-secondary" onClick={clear} disabled={!filtered && !text}>
              Clear filters
            </button>
          </div>
        </div>
      </section>

      <section className="card overflow-x-auto" aria-labelledby="incident-list-title">
        <div className="card-header">
          <h2 id="incident-list-title" className="card-title">
            {list.data ? `${list.data.length} incident${list.data.length === 1 ? "" : "s"}` : "Incidents"}
            {filtered ? " matching filters" : ""}
          </h2>
          {list.refreshing ? (
            <span role="status" className="text-xs text-slate-500">
              Updating…
            </span>
          ) : null}
        </div>
        {list.status === "error" && list.error ? (
          <ErrorState error={list.error} onRetry={list.reload} what="incidents in this project" />
        ) : !list.data ? (
          <LoadingState label="Loading incidents…" />
        ) : list.data.length === 0 ? (
          <EmptyState
            title={filtered ? "No incidents match these filters" : "No incidents reported yet"}
            action={
              filtered ? (
                <button type="button" className="btn-secondary btn-sm" onClick={clear}>
                  Clear filters
                </button>
              ) : null
            }
          />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Reference</th>
                <th scope="col">Title</th>
                <th scope="col">Severity</th>
                <th scope="col">Status</th>
                <th scope="col">Domain</th>
                <th scope="col">Occurred</th>
                <th scope="col">Location</th>
              </tr>
            </thead>
            <tbody>
              {list.data.map((i) => (
                <tr key={i.id} className="hover:bg-slate-50">
                  <td className="whitespace-nowrap">
                    <Link className="link mono" href={`/incidents/${i.id}`}>
                      {i.reference}
                    </Link>
                  </td>
                  <td>
                    <Link href={`/incidents/${i.id}`} className="font-medium text-slate-900 hover:underline">
                      {i.title}
                    </Link>
                    {i.is_synthetic ? (
                      <span className="ml-1">
                        <SyntheticBadge />
                      </span>
                    ) : null}
                  </td>
                  <td>
                    <SeverityBadge severity={i.severity} />
                  </td>
                  <td>
                    <StatusBadge status={i.status} />
                  </td>
                  <td>
                    <DomainBadge domain={i.domain} />
                  </td>
                  <td className="whitespace-nowrap text-slate-700">{formatDateTime(i.occurred_at)}</td>
                  <td className="text-slate-700">{i.location ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
