// Dashboard filters (GET /dashboard): scope, date range of incident occurrence and trend interval. The browser checks
// the range only to give quick feedback; the API validates every value again (400 INVALID_REQUEST).
import type { Query } from "./api";
import type { TrendInterval } from "./types";

export type DashboardScope = "project" | "all";
export type PeriodPreset = "all" | "30d" | "90d" | "12m" | "custom";

export interface DashboardFilters {
  scope: DashboardScope;
  preset: PeriodPreset;
  /** YYYY-MM-DD (UTC calendar day), or "" for no bound. */
  from: string;
  to: string;
  interval: TrendInterval;
}

export const DEFAULT_FILTERS: DashboardFilters = { scope: "project", preset: "all", from: "", to: "", interval: "month" };

export const PRESETS: readonly { id: PeriodPreset; label: string }[] = [
  { id: "all", label: "All dates" },
  { id: "30d", label: "Last 30 days" },
  { id: "90d", label: "Last 90 days" },
  { id: "12m", label: "Last 12 months" },
  { id: "custom", label: "Custom range" },
];

// Same bounds as backend/app/services/analytics.py (MIN_DATE, MAX_DATE).
const MIN_DATE = "1970-01-01";
const MAX_DATE = "2999-12-31";
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

export function utcDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function addDays(day: string, days: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return utcDay(d);
}

/** The from/to days for a preset, ending today (UTC). "all" and "custom" leave the range to the user. */
export function presetRange(preset: PeriodPreset, today: Date = new Date()): { from: string; to: string } | null {
  const end = utcDay(today);
  if (preset === "30d") return { from: addDays(end, -29), to: end };
  if (preset === "90d") return { from: addDays(end, -89), to: end };
  if (preset === "12m") {
    const start = new Date(`${end}T00:00:00Z`);
    start.setUTCFullYear(start.getUTCFullYear() - 1);
    return { from: addDays(utcDay(start), 1), to: end };
  }
  if (preset === "all") return { from: "", to: "" };
  return null;
}

export function isValidDay(value: string): boolean {
  const m = ISO_DATE.exec(value);
  if (!m) return false;
  const d = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && utcDay(d) === value;
}

/** A message for the first problem in the range, or null when the API would accept it. */
export function validateFilters(filters: Pick<DashboardFilters, "from" | "to">): string | null {
  for (const [label, value] of [
    ["From", filters.from],
    ["To", filters.to],
  ] as const) {
    if (!value) continue;
    if (!isValidDay(value)) return `${label} is not a valid date (use YYYY-MM-DD).`;
    if (value < MIN_DATE || value > MAX_DATE) return `${label} must be between ${MIN_DATE} and ${MAX_DATE}.`;
  }
  if (filters.from && filters.to && filters.from > filters.to) return "From must be on or before To.";
  return null;
}

export function dashboardQuery(filters: DashboardFilters, projectId: string): Query {
  return {
    project_id: filters.scope === "project" ? projectId : undefined,
    date_from: filters.from || undefined,
    date_to: filters.to || undefined,
    interval: filters.interval,
  };
}

/** Hours as a short duration: "45 min", "6.0 h", "2.5 days". */
export function formatHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || Number.isNaN(hours)) return "—";
  if (hours < 1) return `${Math.round(hours * 60)} min`;
  if (hours < 48) return `${hours.toFixed(1)} h`;
  return `${(hours / 24).toFixed(1)} days`;
}

export function formatDays(days: number | null | undefined): string {
  if (days === null || days === undefined || Number.isNaN(days)) return "—";
  return `${days.toFixed(1)} ${days === 1 ? "day" : "days"}`;
}

/** "2026-10" -> "Oct 2026" (short "Oct 26"); "2026-W41" -> "Week 41, 2026" (short "W41"). */
export function periodLabel(period: string, short = false): string {
  const week = /^(\d{4})-W(\d{2})$/.exec(period);
  if (week) return short ? `W${week[2]}` : `Week ${Number(week[2])}, ${week[1]}`;
  const month = /^(\d{4})-(\d{2})$/.exec(period);
  if (!month) return period;
  const name = MONTHS[Number(month[2]) - 1];
  if (!name) return period;
  return `${name} ${short ? month[1]!.slice(2) : month[1]}`;
}

// Fixed names rather than Intl: ICU versions differ ("Sep" or "Sept"), which would change labels between the server
// render and the browser.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
