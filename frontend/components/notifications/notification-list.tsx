"use client";

// The signed-in user's notifications (GET /notifications) with mark read (POST /notifications/{id}/read) and mark all
// read (POST /notifications/read-all). The API only ever returns the caller's own notifications.
import Link from "next/link";
import { useId, useState } from "react";
import { api } from "@/lib/api";
import { formatDateTime, humanize } from "@/lib/format";
import { useApi, useMutation } from "@/lib/hooks";
import { announceNotificationsChanged } from "@/lib/notifications";
import type { AppNotification, NotificationList as NotificationListData } from "@/lib/types";
import { Badge, PriorityBadge } from "../badges";
import { DotIcon } from "../icons";
import { EmptyState, ErrorState, InlineError, LoadingState, PartialNotice, SuccessNote } from "../states";

export const NOTIFICATION_PAGE_SIZE = 100;

function NotificationItem({
  n,
  pending,
  onMarkRead,
}: {
  n: AppNotification;
  pending: boolean;
  onMarkRead: (n: AppNotification) => void;
}) {
  const unread = n.read_at === null;
  return (
    <li
      data-testid="notification"
      data-unread={unread || undefined}
      className={`flex flex-col gap-2 border-l-4 px-3 py-2.5 sm:flex-row sm:items-start sm:gap-3 ${unread ? "border-l-brand-500 bg-brand-50/60" : "border-l-transparent"}`}
    >
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-1.5">
          {unread ? (
            <Badge tone="amber" icon={<DotIcon size={12} />}>
              Unread
            </Badge>
          ) : null}
          <PriorityBadge priority={n.priority} />
          <span className="text-xs text-slate-600">{humanize(n.kind)}</span>
        </p>
        <p className={`mt-1 ${unread ? "font-semibold text-slate-900" : "text-slate-800"}`}>{n.title}</p>
        <p className="text-sm text-slate-700">{n.body}</p>
        <p className="mt-0.5 text-xs text-slate-600">
          {formatDateTime(n.created_at)}
          {n.read_at ? ` · read ${formatDateTime(n.read_at)}` : ""}
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        {n.incident_id ? (
          <Link className="btn-secondary btn-sm" href={`/incidents/${n.incident_id}${n.entity_type === "capa" ? "#capa" : ""}`}>
            Open incident
          </Link>
        ) : null}
        {unread ? (
          <button type="button" className="btn-secondary btn-sm" disabled={pending} onClick={() => onMarkRead(n)}>
            Mark as read
          </button>
        ) : null}
      </div>
    </li>
  );
}

export function NotificationList() {
  const id = useId();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const list = useApi<NotificationListData>("/notifications", { unread_only: unreadOnly, limit: NOTIFICATION_PAGE_SIZE });
  const mutation = useMutation();

  async function markRead(n: AppNotification) {
    const done = await mutation.run(() => api<AppNotification>(`/notifications/${encodeURIComponent(n.id)}/read`, { method: "POST" }), "Marked as read.");
    if (done) {
      list.reload();
      announceNotificationsChanged();
    }
  }

  async function markAll() {
    const done = await mutation.run(
      () => api<{ marked: number }>("/notifications/read-all", { method: "POST" }),
      "All notifications marked as read.",
    );
    if (done) {
      list.reload();
      announceNotificationsChanged();
    }
  }

  const unread = list.data?.unread ?? 0;
  return (
    <section className="card" aria-labelledby={`${id}-title`}>
      <div className="card-header">
        <h2 id={`${id}-title`} className="card-title">
          {list.data ? `Your notifications (${unread} unread)` : "Your notifications"}
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-sm">
            <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} />
            Unread only
          </label>
          <button type="button" className="btn-secondary btn-sm" onClick={markAll} disabled={mutation.pending || unread === 0}>
            Mark all as read
          </button>
        </div>
      </div>
      <div className="px-4">
        <InlineError error={mutation.error} />
        <SuccessNote message={mutation.success} />
      </div>
      {list.status === "error" && list.error && !list.data ? (
        <ErrorState error={list.error} onRetry={list.reload} what="your notifications" />
      ) : !list.data ? (
        <LoadingState label="Loading notifications…" />
      ) : list.data.items.length === 0 ? (
        <EmptyState title={unreadOnly ? "No unread notifications" : "No notifications yet"}>
          Workflow events that need you (critical incidents, reviews, assignments, verifications) appear here.
        </EmptyState>
      ) : (
        <>
          {list.data.items.length >= NOTIFICATION_PAGE_SIZE ? (
            <div className="px-4 pt-3">
              <PartialNotice items={[`Showing the latest ${NOTIFICATION_PAGE_SIZE} notifications.`]} />
            </div>
          ) : null}
          <ul className="divide-y divide-slate-100" aria-label="Notifications">
            {list.data.items.map((n) => (
              <NotificationItem key={n.id} n={n} pending={mutation.pending} onMarkRead={markRead} />
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
