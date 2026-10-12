"use client";

import { ReactNode, useId, useState } from "react";
import { label } from "@/lib/api";

export function Card({ title, actions, children, className = "" }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-line bg-surface p-4 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

const SEVERITY: Record<string, { color: string; icon: string }> = {
  LOW: { color: "var(--good)", icon: "▽" },
  MEDIUM: { color: "var(--warning)", icon: "◇" },
  HIGH: { color: "var(--serious)", icon: "△" },
  CRITICAL: { color: "var(--critical)", icon: "▲" },
};

/** Severity or risk band: status color + icon + text label, never color alone. */
export function SeverityBadge({ value, prefix }: { value: string | null | undefined; prefix?: string }) {
  if (!value) return null;
  const s = SEVERITY[value] ?? { color: "var(--muted)", icon: "•" };
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2 py-0.5 text-xs font-medium text-ink">
      <span aria-hidden style={{ color: s.color }}>{s.icon}</span>
      {prefix ? `${prefix} ` : ""}
      {label(value)}
    </span>
  );
}

const STATUS_TONE: Record<string, string> = {
  REPORTED: "bg-surface-2 text-ink",
  TRIAGED: "bg-surface-2 text-ink",
  UNDER_INVESTIGATION: "bg-surface-2 text-ink",
  PENDING_APPROVAL: "bg-ai-wash text-ink",
  ACTION_IN_PROGRESS: "bg-surface-2 text-ink",
  PENDING_VERIFICATION: "bg-surface-2 text-ink",
  CLOSED: "bg-surface-2 text-good-ink",
  PENDING_REVIEW: "bg-ai-wash text-ink",
  APPROVED: "bg-surface-2 text-good-ink",
  MODIFIED: "bg-surface-2 text-good-ink",
  REJECTED: "bg-surface-2 text-muted line-through",
  SUPERSEDED: "bg-surface-2 text-muted",
  VERIFIED: "bg-surface-2 text-good-ink",
  VERIFICATION_FAILED: "bg-surface-2 text-critical-ink",
};

export function StatusBadge({ value }: { value: string }) {
  return (
    <span className={`inline-block whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium ${STATUS_TONE[value] ?? "bg-surface-2 text-ink"}`}>
      {label(value)}
    </span>
  );
}

/** Wrapper that keeps AI-generated content visually distinct (docs/DESIGN_SYSTEM.md). */
export function AiPanel({ title, provider, flagged, reasons, children }: { title: string; provider?: string; flagged?: boolean; reasons?: string[]; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-line border-l-4 border-l-ai bg-surface p-4" aria-label={`${title} (AI-generated)`}>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="rounded bg-ai-wash px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-ink">AI-generated</span>
        <h3 className="text-sm font-semibold">{title}</h3>
        {provider && <span className="text-xs text-muted">provider: {provider}</span>}
        {flagged && <span className="text-xs font-medium text-critical-ink">⚑ flagged for human review</span>}
      </div>
      {flagged && reasons && reasons.length > 0 && (
        <ul className="mb-2 list-disc pl-5 text-xs text-ink-2">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      <div className="text-sm text-ink">{children}</div>
    </section>
  );
}

export function StatTile({ label: l, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <div className="text-xs text-ink-2">{l}</div>
      <div className="mt-1 text-2xl font-semibold text-ink">{value ?? "–"}</div>
      {note && <div className="mt-0.5 text-xs text-muted">{note}</div>}
    </div>
  );
}

/** Single-series horizontal bars: one hue, value at the tip, hover tooltip, and a table view. */
export function BarList({ title, rows, unit = "" }: { title: string; rows: [string, number][]; unit?: string }) {
  const [asTable, setAsTable] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const id = useId();
  const max = Math.max(1, ...rows.map(([, v]) => v));
  return (
    <Card
      title={title}
      actions={
        <button type="button" onClick={() => setAsTable(!asTable)} className="text-xs text-accent underline-offset-2 hover:underline" aria-controls={id}>
          {asTable ? "Show chart" : "Show table"}
        </button>
      }
    >
      <div id={id}>
        {rows.length === 0 ? (
          <p className="text-sm text-muted">No data yet.</p>
        ) : asTable ? (
          <table className="w-full text-sm">
            <tbody>
              {rows.map(([k, v]) => (
                <tr key={k} className="border-t border-line">
                  <td className="py-1 pr-2">{label(k)}</td>
                  <td className="tabular py-1 text-right">
                    {v}
                    {unit}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <ul className="space-y-0.5" role="list">
            {rows.map(([k, v], i) => (
              <li
                key={k}
                className="relative grid grid-cols-[minmax(7rem,55%)_1fr] items-center gap-2 py-0.5"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                tabIndex={0}
                aria-label={`${label(k)}: ${v}${unit}`}
              >
                <span className="truncate text-xs text-ink-2" title={label(k)}>
                  {label(k)}
                </span>
                <span className="flex items-center gap-1.5">
                  <span
                    className="h-3.5 rounded-r-[4px]"
                    style={{ width: `${Math.max(2, (v / max) * 85)}%`, background: "var(--series-1)", opacity: hover === null || hover === i ? 1 : 0.55 }}
                  />
                  <span className="tabular text-xs text-ink">{v}</span>
                </span>
                {hover === i && (
                  <span role="tooltip" className="pointer-events-none absolute -top-7 left-1/3 z-10 whitespace-nowrap rounded border border-line bg-surface px-2 py-1 text-xs text-ink shadow">
                    {label(k)}: <strong>{v}{unit}</strong>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

export function Button({ children, variant = "primary", ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "bg-accent text-accent-ink hover:opacity-90",
    secondary: "border border-line bg-surface text-ink hover:bg-surface-2",
    danger: "border border-critical bg-surface text-critical-ink hover:bg-surface-2",
  }[variant];
  return (
    <button {...rest} className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${rest.className ?? ""}`}>
      {children}
    </button>
  );
}

export function Field({ label: l, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-ink">{l}</span>
      {children}
      {hint && <span className="mt-0.5 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export const inputCls = "w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink placeholder:text-muted";

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as { message?: string; code?: string; correlationId?: string };
  return (
    <div role="alert" className="rounded-md border border-critical bg-surface px-3 py-2 text-sm text-critical-ink">
      <strong>{e.code ?? "Error"}:</strong> {e.message ?? String(error)}
      {e.correlationId && <span className="block text-xs text-muted">Correlation ID {e.correlationId}</span>}
    </div>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <p className="py-6 text-sm text-muted" role="status">
      {what}…
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-sm text-muted">{children}</p>;
}
