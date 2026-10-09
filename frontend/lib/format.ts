// Display helpers. The API returns UTC timestamps; SQLite deployments omit the offset, so a bare timestamp is
// read as UTC rather than local time.

const HAS_ZONE = /(Z|[+-]\d{2}:?\d{2})$/i;

export function parseTimestamp(value: string | null | undefined): Date | null {
  if (!value) return null;
  const iso = /^\d{4}-\d{2}-\d{2}$/.test(value) || HAS_ZONE.test(value) ? value : `${value}Z`;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

const dateTimeFormat = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const dateFormat = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" });

export function formatDateTime(value: string | null | undefined): string {
  const date = parseTimestamp(value);
  return date ? dateTimeFormat.format(date) : "—";
}

/** Calendar dates (due dates) carry no time zone; format them without shifting the day. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (match) {
    const [, y, m, d] = match;
    return dateFormat.format(new Date(Date.UTC(Number(y), Number(m) - 1, Number(d), 12)));
  }
  const date = parseTimestamp(value);
  return date ? dateFormat.format(date) : "—";
}

export function isOverdue(dueDate: string | null | undefined, today: Date = new Date()): boolean {
  if (!dueDate) return false;
  const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  return dueDate < todayIso;
}

/** "PENDING_APPROVAL" -> "Pending approval" */
export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  const words = value.replace(/[_-]+/g, " ").trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const ROLE_LABELS: Record<string, string> = {
  SUPER_ADMIN: "Super admin",
  ORG_ADMIN: "Organization admin",
  HSE_MANAGER: "HSE manager",
  PROJECT_MANAGER: "Project manager",
  SAFETY_ENGINEER: "Safety engineer",
  QA_QC_ENGINEER: "QA/QC engineer",
  SITE_ENGINEER: "Site engineer",
  AUDITOR: "Auditor",
  VIEWER: "Viewer",
};

export function roleLabel(role: string | null | undefined): string {
  if (!role) return "—";
  return ROLE_LABELS[role] ?? humanize(role);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

export function shortId(id: string | null | undefined, length = 8): string {
  if (!id) return "—";
  return id.length > length ? id.slice(0, length) : id;
}

/** Convert a datetime-local input value (local time, no zone) to an ISO string with offset. */
export function localInputToIso(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** Current local time formatted for a datetime-local input. */
export function nowForInput(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}
