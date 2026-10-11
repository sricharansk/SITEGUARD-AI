// In-app notifications: a browser event lets the notifications page tell the header bell to refresh its unread count
// after marking items read, without a shared store. The API remains the source of the count.

export const NOTIFICATIONS_CHANGED_EVENT = "siteguard:notifications-changed";

export function announceNotificationsChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED_EVENT));
}

/** How often the bell refreshes the unread count while a page is open. */
export const UNREAD_POLL_MS = 60_000;

/** "Notifications, 3 unread" for the bell's accessible name. */
export function bellLabel(unread: number | undefined): string {
  if (unread === undefined) return "Notifications";
  if (unread === 0) return "Notifications, none unread";
  return `Notifications, ${unread} unread`;
}

export function unreadBadgeText(unread: number): string {
  return unread > 99 ? "99+" : String(unread);
}
