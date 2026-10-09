// Notifications: the header bell shows the unread count and refreshes when the list marks items read; the list marks
// one or all read through the API; the delivery outbox offers Retry only for FAILED or SKIPPED deliveries and only to
// users allowed to retry, and shows the unauthorized state when the API refuses.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { peopleIndex } from "@/components/incident/people";
import { NotificationBell } from "@/components/notifications/bell";
import { DeliveryOutbox, isRetryable } from "@/components/notifications/delivery-outbox";
import { NotificationList } from "@/components/notifications/notification-list";
import { NOTIFICATIONS_CHANGED_EVENT, announceNotificationsChanged, bellLabel, unreadBadgeText } from "@/lib/notifications";
import type { AppNotification, NotificationDelivery } from "@/lib/types";
import { ASSIGNEE_ID, INCIDENT_ID, MEMBERS, envelopeResponse, errorEnvelopeResponse } from "../fixtures";

vi.mock("next/navigation", () => ({ usePathname: () => "/dashboard" }));

function makeNotification(overrides: Partial<AppNotification> = {}): AppNotification {
  return {
    id: "n1",
    organization_id: "o1",
    project_id: "p1",
    incident_id: INCIDENT_ID,
    kind: "CRITICAL_INCIDENT",
    priority: "CRITICAL",
    title: "Critical incident SG-2026-0001",
    body: "Fall from height at Level 4.",
    entity_type: "incident",
    entity_id: INCIDENT_ID,
    created_at: "2026-10-09T08:00:00",
    read_at: null,
    ...overrides,
  };
}

function makeDelivery(overrides: Partial<NotificationDelivery> = {}): NotificationDelivery {
  return {
    id: "d1",
    notification_id: "n1",
    kind: "CRITICAL_INCIDENT",
    title: "Critical incident SG-2026-0001",
    recipient_id: ASSIGNEE_ID,
    channel: "email",
    status: "FAILED",
    attempts: 5,
    last_error: "SMTP refused",
    next_attempt_at: null,
    sent_at: null,
    created_at: "2026-10-09T08:00:00",
    ...overrides,
  };
}

const urls = (mock: ReturnType<typeof vi.fn>) => mock.mock.calls.map(([url]) => url as string);

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

describe("bell helpers", () => {
  it("names the count for screen readers and caps the badge", () => {
    expect(bellLabel(undefined)).toBe("Notifications");
    expect(bellLabel(0)).toBe("Notifications, none unread");
    expect(bellLabel(3)).toBe("Notifications, 3 unread");
    expect(unreadBadgeText(7)).toBe("7");
    expect(unreadBadgeText(150)).toBe("99+");
  });
});

describe("NotificationBell", () => {
  it("shows the unread count and reloads when notifications change", async () => {
    fetchMock
      .mockResolvedValueOnce(envelopeResponse({ unread: 3, items: [] }))
      .mockResolvedValueOnce(envelopeResponse({ unread: 0, items: [] }));
    render(<NotificationBell />);
    const bell = await screen.findByRole("link", { name: "Notifications, 3 unread" });
    expect(bell).toHaveAttribute("href", "/notifications");
    expect(bell).toHaveTextContent("3");
    expect(urls(fetchMock)[0]).toBe("/api/backend/notifications?unread_only=true&limit=1");

    act(() => announceNotificationsChanged());
    await screen.findByRole("link", { name: "Notifications, none unread" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("notification-bell")).not.toHaveTextContent(/\d/);
  });

  it("stays usable when the count cannot be loaded", async () => {
    fetchMock.mockResolvedValue(errorEnvelopeResponse(500, "INTERNAL_ERROR", "boom"));
    render(<NotificationBell />);
    const bell = screen.getByRole("link", { name: "Notifications" });
    await waitFor(() => expect(bell).toHaveAttribute("title", "Notifications (unread count unavailable)"));
  });
});

describe("NotificationList", () => {
  it("marks one notification read, reloads and tells the bell", async () => {
    const changed = vi.fn();
    window.addEventListener(NOTIFICATIONS_CHANGED_EVENT, changed);
    const unread = makeNotification();
    const read = makeNotification({ id: "n2", title: "Action assigned", priority: "INFO", read_at: "2026-10-09T09:00:00", incident_id: null });
    fetchMock
      .mockResolvedValueOnce(envelopeResponse({ unread: 1, items: [unread, read] }))
      .mockResolvedValueOnce(envelopeResponse({ ...unread, read_at: "2026-10-09T10:00:00" }))
      .mockResolvedValueOnce(envelopeResponse({ unread: 0, items: [{ ...unread, read_at: "2026-10-09T10:00:00" }, read] }));
    render(<NotificationList />);

    expect(await screen.findByRole("heading", { name: "Your notifications (1 unread)" })).toBeVisible();
    expect(urls(fetchMock)[0]).toBe("/api/backend/notifications?unread_only=false&limit=100");
    const [first, second] = screen.getAllByTestId("notification");
    expect(within(first!).getByText("Unread")).toBeVisible();
    expect(within(first!).getByRole("link", { name: "Open incident" })).toHaveAttribute("href", `/incidents/${INCIDENT_ID}`);
    expect(within(second!).queryByRole("button", { name: "Mark as read" })).toBeNull();

    fireEvent.click(within(first!).getByRole("button", { name: "Mark as read" }));
    expect(await screen.findByRole("heading", { name: "Your notifications (0 unread)" })).toBeVisible();
    const [, markCall] = fetchMock.mock.calls as [string, RequestInit][];
    expect(markCall![0]).toBe("/api/backend/notifications/n1/read");
    expect(markCall![1].method).toBe("POST");
    expect(changed).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Mark all as read" })).toBeDisabled();
    window.removeEventListener(NOTIFICATIONS_CHANGED_EVENT, changed);
  });

  it("marks all read through the API", async () => {
    fetchMock
      .mockResolvedValueOnce(envelopeResponse({ unread: 2, items: [makeNotification(), makeNotification({ id: "n3", title: "Review needed" })] }))
      .mockResolvedValueOnce(envelopeResponse({ marked: 2 }))
      .mockResolvedValueOnce(envelopeResponse({ unread: 0, items: [] }));
    render(<NotificationList />);
    fireEvent.click(await screen.findByRole("button", { name: "Mark all as read" }));
    expect(await screen.findByText("All notifications marked as read.")).toBeVisible();
    const [, call] = fetchMock.mock.calls as [string, RequestInit][];
    expect(call![0]).toBe("/api/backend/notifications/read-all");
    expect(call![1].method).toBe("POST");
    expect(await screen.findByText("No notifications yet")).toBeVisible();
  });

  it("filters to unread only", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(envelopeResponse({ unread: 0, items: [] })));
    render(<NotificationList />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Unread only" }));
    expect(await screen.findByText("No unread notifications")).toBeVisible();
    expect(urls(fetchMock)).toContain("/api/backend/notifications?unread_only=true&limit=100");
  });
});

describe("DeliveryOutbox", () => {
  const people = peopleIndex(MEMBERS);
  const rows = [
    makeDelivery(),
    makeDelivery({ id: "d2", title: "Review needed", status: "SKIPPED", attempts: 0, last_error: "Email delivery is turned off." }),
    makeDelivery({ id: "d3", title: "Action assigned", status: "SENT", attempts: 1, last_error: null, sent_at: "2026-10-09T08:01:00" }),
    makeDelivery({ id: "d4", title: "Verify action", status: "PENDING", attempts: 1, next_attempt_at: "2026-10-09T08:05:00" }),
  ];

  it("offers Retry only for failed or skipped deliveries", async () => {
    expect(["FAILED", "SKIPPED", "SENT", "PENDING"].map(isRetryable)).toEqual([true, true, false, false]);
    fetchMock.mockResolvedValue(envelopeResponse(rows));
    render(<DeliveryOutbox organizationId="o1" organizationName="Demo Org" canRetry people={people} />);
    expect(await screen.findAllByTestId("delivery")).toHaveLength(4);
    expect(urls(fetchMock)[0]).toBe("/api/backend/notifications/deliveries?organization_id=o1&limit=100");
    expect(screen.getByRole("heading", { name: "Email delivery outbox · Demo Org" })).toBeVisible();
    expect(screen.getAllByRole("button", { name: /^Retry delivery of / }).map((b) => b.getAttribute("aria-label"))).toEqual([
      "Retry delivery of Critical incident SG-2026-0001",
      "Retry delivery of Review needed",
    ]);
    expect(screen.getAllByText("Sid Site")).toHaveLength(4);
  });

  it("retries through the API and reloads", async () => {
    fetchMock
      .mockResolvedValueOnce(envelopeResponse(rows))
      .mockResolvedValueOnce(envelopeResponse({ ...rows[0], status: "PENDING", attempts: 0 }))
      .mockResolvedValueOnce(envelopeResponse([{ ...rows[0], status: "PENDING", attempts: 0 }]));
    render(<DeliveryOutbox organizationId="o1" canRetry people={people} />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry delivery of Critical incident SG-2026-0001" }));
    expect(await screen.findByText("Delivery of “Critical incident SG-2026-0001” queued again.")).toBeVisible();
    const [, call] = fetchMock.mock.calls as [string, RequestInit][];
    expect(call![0]).toBe("/api/backend/notifications/deliveries/d1/retry");
    expect(call![1].method).toBe("POST");
    await waitFor(() => expect(screen.getAllByTestId("delivery")).toHaveLength(1));
  });

  it("hides Retry from users who may only view, and filters by status", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(envelopeResponse(rows)));
    render(<DeliveryOutbox organizationId="o1" canRetry={false} people={people} />);
    expect(await screen.findAllByTestId("delivery")).toHaveLength(4);
    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();
    expect(screen.getByText(/Retrying a delivery needs an organization-wide/)).toBeVisible();
    fireEvent.change(screen.getByRole("combobox", { name: "Delivery status" }), { target: { value: "FAILED" } });
    await waitFor(() => expect(urls(fetchMock)).toContain("/api/backend/notifications/deliveries?organization_id=o1&status=FAILED&limit=100"));
  });

  it("shows the unauthorized state when the API refuses", async () => {
    fetchMock.mockResolvedValue(errorEnvelopeResponse(403, "FORBIDDEN", "Organization-wide VIEW_AUDIT required.", "cid-outbox-403"));
    render(<DeliveryOutbox organizationId="o1" canRetry people={people} />);
    expect(await screen.findByText("Not authorized")).toBeVisible();
    expect(screen.queryByTestId("delivery")).toBeNull();
  });
});
