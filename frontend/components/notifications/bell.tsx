"use client";

// Header bell with the unread count (GET /notifications?unread_only=true&limit=1 returns the count without the list).
// It refreshes on navigation, every minute, and when the notifications page marks items read.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { useApi } from "@/lib/hooks";
import { NOTIFICATIONS_CHANGED_EVENT, UNREAD_POLL_MS, bellLabel, unreadBadgeText } from "@/lib/notifications";
import type { NotificationList } from "@/lib/types";
import { BellIcon } from "../icons";

export function NotificationBell() {
  const pathname = usePathname();
  const unread = useApi<NotificationList>("/notifications", { unread_only: true, limit: 1 });
  const { reload } = unread;
  const lastPath = useRef(pathname);

  useEffect(() => {
    if (lastPath.current === pathname) return;
    lastPath.current = pathname;
    reload();
  }, [pathname, reload]);

  useEffect(() => {
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, reload);
    const timer = window.setInterval(reload, UNREAD_POLL_MS);
    return () => {
      window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, reload);
      window.clearInterval(timer);
    };
  }, [reload]);

  const count = unread.data?.unread;
  const active = pathname === "/notifications";
  return (
    <Link
      href="/notifications"
      aria-label={bellLabel(count)}
      aria-current={active ? "page" : undefined}
      title={unread.status === "error" && count === undefined ? "Notifications (unread count unavailable)" : bellLabel(count)}
      className={`relative inline-flex items-center rounded border px-2 py-1 text-white hover:bg-slate-800 ${
        active ? "border-brand-400" : "border-slate-500"
      }`}
      data-testid="notification-bell"
    >
      <BellIcon size={16} />
      {count ? (
        <span
          aria-hidden="true"
          className="ml-1 min-w-5 rounded-full bg-brand-400 px-1.5 text-center text-xs leading-5 font-bold text-slate-900 tabular-nums"
        >
          {unreadBadgeText(count)}
        </span>
      ) : null}
    </Link>
  );
}
