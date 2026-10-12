"use client";

import { useCallback, useEffect, useState } from "react";
import { api, fmtDate, label, qs } from "@/lib/api";
import { useSession } from "@/components/Shell";
import { Button, Card, Empty, ErrorBanner, Loading } from "@/components/ui";

interface Delivery {
  id: string;
  notification_id: string;
  channel: string;
  status: "PENDING" | "SENT" | "FAILED" | "SKIPPED";
  attempts: number;
  last_error: string | null;
  next_attempt_at: string | null;
  sent_at: string | null;
  created_at: string;
  kind: string;
  recipient: string;
  incident_id: string | null;
}

const FILTERS = ["", "PENDING", "SENT", "FAILED", "SKIPPED"] as const;

/** Email outbox for one organization: what was sent, what is waiting, and dead letters an admin can retry. */
export default function OutboxPage() {
  const { project, me } = useSession();
  const [status, setStatus] = useState<(typeof FILTERS)[number]>("");
  const [rows, setRows] = useState<Delivery[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const org = project?.organization_id;
  const orgWide = (perm: string) => !!org && me.memberships.some((m) => m.organization_id === org && !m.project_id && m.permissions.includes(perm));
  const canView = orgWide("VIEW_AUDIT");
  const canManage = orgWide("MANAGE_PROJECTS");

  const load = useCallback(() => {
    if (!org || !canView) return;
    let current = true;
    setRows(null);
    api
      .get<Delivery[]>(`/notifications/deliveries${qs({ organization_id: org, status })}`)
      .then((r) => current && setRows(r))
      .catch((e) => current && setError(e));
    return () => {
      current = false;
    };
  }, [org, status, canView]);
  useEffect(load, [load]);

  async function run(name: string, fn: () => Promise<string>) {
    setBusy(name);
    setError(null);
    setNotice(null);
    try {
      setNotice(await fn());
      load();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  }

  if (!canView) return <ErrorBanner error={{ code: "FORBIDDEN", message: "The email outbox needs an organization-wide role that can view the audit trail." }} />;
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Email outbox</h1>
      <p className="text-sm text-ink-2">
        Every notification is queued for email. A failed send is retried with increasing waits and then kept as failed until an
        administrator retries it; when email is turned off on this server, deliveries are marked skipped. Recipients are shown
        by name only.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <div role="tablist" aria-label="Delivery status" className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f || "all"}
              role="tab"
              aria-selected={status === f}
              className={`rounded px-2.5 py-1 text-sm ${status === f ? "bg-surface-2 font-semibold" : "text-ink-2 hover:bg-surface-2"}`}
              onClick={() => setStatus(f)}
            >
              {f ? label(f) : "All"}
            </button>
          ))}
        </div>
        {canManage && (
          <Button
            className="ml-auto"
            disabled={!!busy}
            onClick={() =>
              run("deliver", async () => {
                const r = await api.post<Record<string, number>>(`/notifications/deliver${qs({ organization_id: org })}`, {});
                return `Delivery run: ${r.sent} sent, ${r.retrying} to retry, ${r.failed} failed, ${r.skipped} skipped.`;
              })
            }
          >
            {busy === "deliver" ? "Sending…" : "Send due emails now"}
          </Button>
        )}
      </div>
      <ErrorBanner error={error} />
      {notice && (
        <p role="status" className="text-sm text-good-ink">
          {notice}
        </p>
      )}
      <Card>
        {!rows ? (
          <Loading what="Loading deliveries" />
        ) : rows.length === 0 ? (
          <Empty>No deliveries{status ? ` with status ${label(status).toLowerCase()}` : ""}.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="py-1.5 font-medium">Queued</th>
                  <th className="py-1.5 font-medium">Notification</th>
                  <th className="py-1.5 font-medium">Recipient</th>
                  <th className="py-1.5 font-medium">Status</th>
                  <th className="py-1.5 font-medium">Attempts</th>
                  <th className="py-1.5 font-medium">Last error / next try</th>
                  <th className="py-1.5 font-medium" />
                </tr>
              </thead>
              <tbody>
                {rows.map((d) => (
                  <tr key={d.id} className="border-t border-line align-top">
                    <td className="tabular py-1.5 pr-2 text-xs">{fmtDate(d.created_at, true)}</td>
                    <td className="py-1.5 pr-2 text-xs">{label(d.kind)}</td>
                    <td className="py-1.5 pr-2 text-xs">{d.recipient}</td>
                    <td className={`py-1.5 pr-2 text-xs ${d.status === "FAILED" ? "text-critical-ink" : d.status === "SENT" ? "text-good-ink" : ""}`}>
                      {label(d.status)}
                      {d.sent_at ? ` ${fmtDate(d.sent_at, true)}` : ""}
                    </td>
                    <td className="tabular py-1.5 pr-2 text-xs">{d.attempts}</td>
                    <td className="py-1.5 pr-2 text-xs text-ink-2">
                      {d.last_error}
                      {d.next_attempt_at ? ` · next try ${fmtDate(d.next_attempt_at, true)}` : ""}
                    </td>
                    <td className="py-1.5 text-right">
                      {canManage && (d.status === "FAILED" || d.status === "SKIPPED") && (
                        <Button
                          variant="secondary"
                          disabled={!!busy}
                          onClick={() =>
                            run(d.id, async () => {
                              await api.post(`/notifications/deliveries/${d.id}/retry`, {});
                              return "Queued again; the next delivery run sends it.";
                            })
                          }
                        >
                          Retry
                        </Button>
                      )}
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
