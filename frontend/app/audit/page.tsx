"use client";

import { useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { personName, useSession } from "@/components/Shell";
import { Card, ErrorBanner, Loading } from "@/components/ui";

interface AuditEvent {
  id: string;
  actor_id: string | null;
  actor_type: string;
  action: string;
  entity_type: string;
  entity_id: string;
  details: Record<string, unknown>;
  correlation_id: string | null;
  created_at: string;
}

export default function AuditPage() {
  const { can, people } = useSession();
  const [rows, setRows] = useState<AuditEvent[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    api.get<AuditEvent[]>("/audit?limit=200").then(setRows).catch(setError);
  }, []);
  if (!can("VIEW_AUDIT")) return <ErrorBanner error={{ code: "FORBIDDEN", message: "Your role cannot view the audit trail." }} />;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Audit trail</h1>
      <p className="text-sm text-ink-2">Append-only record of every human and agent action, with correlation IDs. Latest 200 events.</p>
      <ErrorBanner error={error} />
      <Card>
        {!rows ? (
          <Loading />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-1.5 font-medium">When</th>
                  <th className="py-1.5 font-medium">Actor</th>
                  <th className="py-1.5 font-medium">Action</th>
                  <th className="py-1.5 font-medium">Entity</th>
                  <th className="py-1.5 font-medium">Correlation ID</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-line align-top">
                    <td className="tabular py-1.5 pr-2 text-xs">{fmtDate(r.created_at, true)}</td>
                    <td className="py-1.5 pr-2 text-xs">
                      {r.actor_type === "USER" ? personName(people, r.actor_id) : `${r.actor_type.toLowerCase()} (${personName(people, r.actor_id)})`}
                    </td>
                    <td className="py-1.5 pr-2">
                      <code className="text-xs">{r.action}</code>
                    </td>
                    <td className="py-1.5 pr-2 text-xs">
                      {r.entity_type} {r.entity_id.slice(0, 8)}
                    </td>
                    <td className="py-1.5 font-mono text-[11px] text-muted">{r.correlation_id?.slice(0, 13)}</td>
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
