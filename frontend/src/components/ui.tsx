import type { ReactNode } from "react";

// Severity/risk always shows a text label, never colour alone (docs/DESIGN_SYSTEM.md).
const SEVERITY_STYLE: Record<string, string> = {
  CRITICAL: "bg-red-700 text-white",
  HIGH: "bg-orange-100 text-orange-900 ring-1 ring-orange-400",
  MEDIUM: "bg-amber-50 text-amber-900 ring-1 ring-amber-300",
  LOW: "bg-emerald-50 text-emerald-900 ring-1 ring-emerald-300",
};

export function SeverityBadge({ value, prefix }: { value: string; prefix?: string }) {
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold ${SEVERITY_STYLE[value] ?? "bg-surface-alt text-ink-soft ring-1 ring-surface-line"}`}>
      {prefix ? `${prefix} ` : ""}
      {value}
    </span>
  );
}

export function StatusPill({ value }: { value: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-brand-tint px-2.5 py-0.5 text-xs font-medium text-brand-dark">
      {label(value)}
    </span>
  );
}

export function label(v: string) {
  return v.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

export function Card({ title, children, action }: { title?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="rounded-lg border border-surface-line bg-surface p-4 shadow-sm">
      {(title || action) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-soft">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

// AI-generated content is always wrapped so it is visually distinct from human-entered data.
export function AiBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-ai-line bg-ai-tint p-3">
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded bg-ai px-1.5 py-0.5 text-[11px] font-bold uppercase tracking-wide text-white">AI draft</span>
        <h3 className="text-sm font-semibold text-ai">{title}</h3>
      </div>
      {children}
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <p role="status" className="p-6 text-sm text-ink-soft">
      Loading {what}…
    </p>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
      {message}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-md border border-dashed border-surface-line p-4 text-center text-sm text-ink-soft">{children}</p>;
}

export function fmtDate(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
