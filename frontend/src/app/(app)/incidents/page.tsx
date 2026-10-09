"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Incident } from "@/lib/types";
import { useApp } from "@/components/Shell";
import { Empty, ErrorBox, Loading, SeverityBadge, StatusPill, fmtDate, label } from "@/components/ui";

const STATUSES = ["REPORTED", "TRIAGED", "UNDER_INVESTIGATION", "PENDING_APPROVAL", "ACTION_IN_PROGRESS", "PENDING_VERIFICATION", "CLOSED"];

export default function IncidentsPage() {
  const { project } = useApp();
  const [rows, setRows] = useState<Incident[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [domain, setDomain] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (severity) params.set("severity", severity);
    if (domain) params.set("domain", domain);
    if (q.trim()) params.set("q", q.trim());
    const handle = setTimeout(() => {
      setError(null);
      api<Incident[]>(`/projects/${project.id}/incidents?${params}`).then(setRows).catch((e: Error) => setError(e.message));
    }, 200);
    return () => clearTimeout(handle);
  }, [project.id, status, severity, domain, q]);

  const sel = "rounded border border-surface-line bg-surface px-2 py-1.5 text-sm";
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Incidents</h1>
      <div className="flex flex-wrap gap-2">
        <input aria-label="Search incidents" placeholder="Search title or description" value={q} onChange={(e) => setQ(e.target.value)} className={`${sel} min-w-64`} />
        <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className={sel}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select>
        <select aria-label="Severity" value={severity} onChange={(e) => setSeverity(e.target.value)} className={sel}>
          <option value="">All severities</option>
          {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select>
        <select aria-label="Domain" value={domain} onChange={(e) => setDomain(e.target.value)} className={sel}>
          <option value="">Safety and quality</option>
          <option value="SAFETY">Safety</option>
          <option value="QUALITY">Quality</option>
        </select>
      </div>
      {error && <ErrorBox message={error} />}
      {!rows && !error && <Loading what="incidents" />}
      {rows && rows.length === 0 && <Empty>No incidents match these filters.</Empty>}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-surface-line bg-surface shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-alt text-xs uppercase tracking-wide text-ink-soft">
              <tr><th className="p-3">Reference</th><th className="p-3">Title</th><th className="p-3">Domain</th><th className="p-3">Severity</th><th className="p-3">Status</th><th className="p-3">Reported</th></tr>
            </thead>
            <tbody className="divide-y divide-surface-line">
              {rows.map((i) => (
                <tr key={i.id} className="hover:bg-surface-alt">
                  <td className="p-3 font-mono text-xs">{i.reference}</td>
                  <td className="p-3"><Link href={`/incidents/${i.id}`} className="font-medium text-brand hover:underline">{i.title}</Link></td>
                  <td className="p-3">{label(i.domain)}</td>
                  <td className="p-3"><SeverityBadge value={i.severity} /></td>
                  <td className="p-3"><StatusPill value={i.status} /></td>
                  <td className="p-3 whitespace-nowrap">{fmtDate(i.reported_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
