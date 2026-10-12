"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fmtDate, label, qs } from "@/lib/api";
import type { Incident } from "@/lib/types";
import { useSession } from "@/components/Shell";
import { Card, Empty, ErrorBanner, inputCls, Loading, SeverityBadge, StatusBadge } from "@/components/ui";

export default function IncidentsPage() {
  const { project, can } = useSession();
  const [rows, setRows] = useState<Incident[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [f, setF] = useState({ q: "", status: "", severity: "", domain: "" });

  useEffect(() => {
    if (!project) return;
    let current = true; // ignore responses for filters the user has since changed
    const t = setTimeout(() => {
      api
        .get<Incident[]>(`/projects/${project.id}/incidents${qs(f)}`)
        .then((r) => current && setRows(r))
        .catch((e) => current && setError(e));
    }, 200);
    return () => {
      current = false;
      clearTimeout(t);
    };
  }, [project, f]);

  if (!project) return null;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Incidents</h1>
        {can("CREATE_INCIDENT") && (
          <Link href="/incidents/new/" className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-ink">
            Report incident
          </Link>
        )}
      </div>
      <div className="flex flex-wrap gap-2" role="search">
        <input aria-label="Search" placeholder="Search title, description or reference" className={`${inputCls} max-w-xs`} value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} />
        {(
          [
            ["status", ["REPORTED", "TRIAGED", "UNDER_INVESTIGATION", "PENDING_APPROVAL", "ACTION_IN_PROGRESS", "PENDING_VERIFICATION", "CLOSED"]],
            ["severity", ["CRITICAL", "HIGH", "MEDIUM", "LOW"]],
            ["domain", ["SAFETY", "QUALITY", "BOTH"]],
          ] as const
        ).map(([key, opts]) => (
          <select key={key} aria-label={label(key)} className={`${inputCls} w-auto`} value={f[key]} onChange={(e) => setF({ ...f, [key]: e.target.value })}>
            <option value="">All {key === "status" ? "statuses" : key === "severity" ? "severities" : "domains"}</option>
            {opts.map((o) => (
              <option key={o} value={o}>
                {label(o)}
              </option>
            ))}
          </select>
        ))}
      </div>
      <ErrorBanner error={error} />
      <Card>
        {!rows ? (
          <Loading />
        ) : rows.length === 0 ? (
          <Empty>No incidents match these filters.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-1.5 font-medium">Ref</th>
                  <th className="py-1.5 font-medium">Incident</th>
                  <th className="py-1.5 font-medium">Domain</th>
                  <th className="py-1.5 font-medium">Severity</th>
                  <th className="py-1.5 font-medium">Status</th>
                  <th className="py-1.5 font-medium">Occurred</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((i) => (
                  <tr key={i.id} className="border-t border-line align-top">
                    <td className="tabular whitespace-nowrap py-2 pr-2 text-xs">{i.reference}</td>
                    <td className="py-2 pr-2">
                      <Link href={`/incident/?id=${i.id}`} className="font-medium text-accent hover:underline">
                        {i.title}
                      </Link>
                      <div className="text-xs text-muted">{i.location}{i.is_synthetic ? " · synthetic demo data" : ""}</div>
                    </td>
                    <td className="py-2 pr-2 text-xs">{label(i.domain)}</td>
                    <td className="py-2 pr-2"><SeverityBadge value={i.severity} /></td>
                    <td className="py-2 pr-2"><StatusBadge value={i.status} /></td>
                    <td className="tabular py-2 text-xs">{fmtDate(i.occurred_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
