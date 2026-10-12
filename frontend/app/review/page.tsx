"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fmtDate, label, qs } from "@/lib/api";
import type { Capa } from "@/lib/types";
import { useSession } from "@/components/Shell";
import { Card, Empty, ErrorBanner, Loading, StatusBadge } from "@/components/ui";

const TABS = [
  { key: "review", label: "Awaiting review", params: { approval_status: "PENDING_REVIEW" } },
  { key: "mine", label: "Assigned to me", params: { mine: true } },
  { key: "progress", label: "In progress", params: { work_status: "IN_PROGRESS" } },
  { key: "verify", label: "Awaiting verification", params: { work_status: "COMPLETED" } },
] as const;

export default function ActionsPage() {
  const { project } = useSession();
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("review");
  const [rows, setRows] = useState<Capa[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!project) return;
    let current = true; // ignore a slower response from a tab the user already left
    setRows(null);
    const t = TABS.find((x) => x.key === tab)!;
    api
      .get<Capa[]>(`/capa${qs({ project_id: project.id, ...t.params })}`)
      .then((r) => current && setRows(r))
      .catch((e) => current && setError(e));
    return () => {
      current = false;
    };
  }, [project, tab]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Corrective and preventive actions</h1>
      <div role="tablist" className="flex flex-wrap gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-1.5 text-sm ${tab === t.key ? "border-accent font-semibold text-ink" : "border-transparent text-ink-2 hover:text-ink"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <ErrorBanner error={error} />
      <Card>
        {!rows ? (
          <Loading />
        ) : rows.length === 0 ? (
          <Empty>Nothing here.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-1.5 font-medium">Action</th>
                  <th className="py-1.5 font-medium">Incident</th>
                  <th className="py-1.5 font-medium">Status</th>
                  <th className="py-1.5 font-medium">Due</th>
                  <th className="py-1.5 font-medium">Reviewer</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr key={a.id} className="border-t border-line align-top">
                    <td className="py-2 pr-2">
                      <span className="mr-1 rounded bg-surface-2 px-1 text-xs">{label(a.action_type)}</span>
                      {a.title}
                      {a.ai_generated && <span className="ml-1 text-[11px] font-semibold uppercase text-ai">AI-proposed</span>}
                    </td>
                    <td className="py-2 pr-2">
                      <Link className="text-accent hover:underline" href={`/incident/?id=${a.incident_id}`}>
                        {a.incident_reference}
                      </Link>
                      <div className="text-xs text-muted">{a.incident_title}</div>
                    </td>
                    <td className="py-2 pr-2">
                      <StatusBadge value={a.approval_status === "PENDING_REVIEW" ? a.approval_status : a.work_status} />
                    </td>
                    <td className="tabular py-2 pr-2 text-xs">{fmtDate(a.due_date)}</td>
                    <td className="py-2 text-xs">
                      {a.approval_status === "PENDING_REVIEW" ? (a.can_review ? "You can review" : a.critical ? "HSE manager" : "PM / HSE manager") : ""}
                    </td>
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
