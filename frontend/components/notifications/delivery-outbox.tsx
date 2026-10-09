"use client";

// Email delivery outbox for administrators (GET /notifications/deliveries, organization-wide VIEW_AUDIT) with retry of
// FAILED (dead letter) and SKIPPED deliveries (POST /notifications/deliveries/{id}/retry, organization-wide
// MANAGE_PROJECTS). The page shows this section only when /me grants the permission; the API checks it again and a
// 403 renders the unauthorized state.
import { useId, useState } from "react";
import { api } from "@/lib/api";
import { formatDateTime, humanize } from "@/lib/format";
import { useApi, useMutation } from "@/lib/hooks";
import { DELIVERY_STATUSES, type DeliveryStatus, type NotificationDelivery } from "@/lib/types";
import { DeliveryStatusBadge } from "../badges";
import { personName, type People } from "../incident/people";
import { EmptyState, ErrorState, InlineError, LoadingState, PartialNotice, SuccessNote } from "../states";

export const OUTBOX_PAGE_SIZE = 100;
const RETRYABLE: readonly DeliveryStatus[] = ["FAILED", "SKIPPED"];

export function isRetryable(status: DeliveryStatus | string): boolean {
  return RETRYABLE.includes(status as DeliveryStatus);
}

export function DeliveryOutbox({
  organizationId,
  organizationName,
  canRetry,
  people,
}: {
  organizationId: string;
  organizationName?: string | null;
  /** Organization-wide MANAGE_PROJECTS: shows the Retry buttons. */
  canRetry: boolean;
  people: People;
}) {
  const id = useId();
  const [status, setStatus] = useState<DeliveryStatus | "">("");
  const rows = useApi<NotificationDelivery[]>("/notifications/deliveries", {
    organization_id: organizationId,
    status,
    limit: OUTBOX_PAGE_SIZE,
  });
  const mutation = useMutation();

  async function retry(d: NotificationDelivery) {
    const done = await mutation.run(
      () => api<NotificationDelivery>(`/notifications/deliveries/${encodeURIComponent(d.id)}/retry`, { method: "POST" }),
      `Delivery of “${d.title}” queued again.`,
    );
    if (done) rows.reload();
  }

  return (
    <section className="card" aria-labelledby={`${id}-title`} data-testid="delivery-outbox">
      <div className="card-header">
        <h2 id={`${id}-title`} className="card-title">
          Email delivery outbox{organizationName ? ` · ${organizationName}` : ""}
        </h2>
        <div>
          <label htmlFor={`${id}-status`} className="sr-only">
            Delivery status
          </label>
          <select
            id={`${id}-status`}
            className="input py-1 text-xs"
            value={status}
            onChange={(e) => setStatus(e.target.value as DeliveryStatus | "")}
          >
            <option value="">All statuses</option>
            {DELIVERY_STATUSES.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="px-4 pt-2 text-xs text-slate-600">
        <p>
          In-app notifications always arrive. Email is sent by the scheduled delivery job; failed deliveries are retried
          with backoff and end as dead letters. Skipped means external delivery is turned off here.
          {canRetry ? "" : " Retrying a delivery needs an organization-wide project manager or administrator role."}
        </p>
        <InlineError error={mutation.error} />
        <SuccessNote message={mutation.success} />
      </div>
      {rows.status === "error" && rows.error && !rows.data ? (
        <ErrorState error={rows.error} onRetry={rows.reload} what="the delivery outbox" />
      ) : !rows.data ? (
        <LoadingState label="Loading deliveries…" />
      ) : rows.data.length === 0 ? (
        <EmptyState title={status ? `No ${humanize(status).toLowerCase()} deliveries` : "No deliveries yet"} />
      ) : (
        <div className="overflow-x-auto">
          {rows.data.length >= OUTBOX_PAGE_SIZE ? (
            <div className="px-4 pt-2">
              <PartialNotice items={[`Showing the latest ${OUTBOX_PAGE_SIZE} deliveries; filter by status to see others.`]} />
            </div>
          ) : null}
          <table className="table" aria-label="Email deliveries">
            <thead>
              <tr>
                <th scope="col">Notification</th>
                <th scope="col">Recipient</th>
                <th scope="col">Status</th>
                <th scope="col">Attempts</th>
                <th scope="col">Last error</th>
                <th scope="col">Next attempt / sent</th>
                {canRetry ? <th scope="col">Action</th> : null}
              </tr>
            </thead>
            <tbody>
              {rows.data.map((d) => (
                <tr key={d.id} data-testid="delivery">
                  <td>
                    <span className="text-xs text-slate-600">{humanize(d.kind)}</span>
                    <div>{d.title}</div>
                    <div className="text-xs text-slate-500">{formatDateTime(d.created_at)}</div>
                  </td>
                  <td className="whitespace-nowrap">{personName(people, d.recipient_id)}</td>
                  <td>
                    <DeliveryStatusBadge status={d.status} />
                  </td>
                  <td className="tabular-nums">{d.attempts}</td>
                  <td className="max-w-64 text-xs break-words text-slate-700">{d.last_error ?? "—"}</td>
                  <td className="text-xs whitespace-nowrap text-slate-700">
                    {d.sent_at ? `Sent ${formatDateTime(d.sent_at)}` : d.next_attempt_at ? formatDateTime(d.next_attempt_at) : "—"}
                  </td>
                  {canRetry ? (
                    <td>
                      {isRetryable(d.status) ? (
                        <button
                          type="button"
                          className="btn-secondary btn-sm"
                          disabled={mutation.pending}
                          onClick={() => retry(d)}
                          aria-label={`Retry delivery of ${d.title}`}
                        >
                          Retry
                        </button>
                      ) : null}
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
