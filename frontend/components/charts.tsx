// Minimal, accessible charts for the dashboard. Each chart is a single series in one hue with the value printed
// as text, so the bars are an aid, not the only carrier of meaning, and each one is also a readable table.
import type { ReactNode } from "react";

export interface BarItem {
  key: string;
  label: ReactNode;
  /** Plain-text label for tooltips and screen readers. */
  text: string;
  value: number;
}

export function StatTile({
  label,
  value,
  hint,
  emphasis,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  /** Draw attention (for example open critical incidents above zero). Text says why; color only reinforces. */
  emphasis?: boolean;
  icon?: ReactNode;
}) {
  return (
    <div
      className={`rounded-md border bg-white px-3 py-2.5 shadow-xs ${
        emphasis ? "border-red-400 border-l-4 border-l-red-700" : "border-slate-200"
      }`}
    >
      <dt className="kicker flex items-center gap-1">
        {icon}
        {label}
      </dt>
      <dd className={`mt-0.5 text-2xl font-bold tabular-nums ${emphasis ? "text-red-800" : "text-slate-900"}`}>
        {value}
      </dd>
      {hint ? <dd className="text-xs text-slate-600">{hint}</dd> : null}
    </div>
  );
}

/** Horizontal bars, largest first unless `keepOrder`. Rendered as a table: label, bar, value. */
export function BarList({
  items,
  caption,
  keepOrder = false,
  emptyText = "No data yet.",
}: {
  items: BarItem[];
  caption: string;
  keepOrder?: boolean;
  emptyText?: string;
}) {
  const rows = keepOrder ? items : [...items].sort((a, b) => b.value - a.value);
  const max = Math.max(1, ...rows.map((r) => r.value));
  const total = rows.reduce((sum, r) => sum + r.value, 0);
  if (rows.length === 0 || total === 0) return <p className="px-1 py-2 text-slate-600">{emptyText}</p>;
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">{caption}</caption>
      <thead className="sr-only">
        <tr>
          <th scope="col">Category</th>
          <th scope="col">Share</th>
          <th scope="col">Count</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} title={`${row.text}: ${row.value}`}>
            <th scope="row" className="w-2/5 py-1 pr-2 text-left font-normal text-slate-800">
              {row.label}
            </th>
            <td className="py-1" aria-hidden="true">
              <div className="h-3 w-full rounded-sm bg-slate-100">
                <div
                  className="h-3 rounded-r bg-slate-600"
                  style={{ width: `${Math.max(2, (row.value / max) * 100)}%` }}
                />
              </div>
            </td>
            <td className="w-12 py-1 pl-2 text-right font-semibold tabular-nums">{row.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Columns over time (one series). Values are printed above each column. */
export function ColumnChart({ items, caption }: { items: BarItem[]; caption: string }) {
  const max = Math.max(1, ...items.map((i) => i.value));
  if (items.length === 0) return <p className="px-1 py-2 text-slate-600">No data yet.</p>;
  return (
    <figure>
      <div className="flex h-36 items-end gap-2 border-b border-slate-300 px-1" aria-hidden="true">
        {items.map((item) => (
          <div key={item.key} className="flex h-full min-w-8 flex-1 flex-col items-center justify-end" title={`${item.text}: ${item.value}`}>
            <span className="text-xs font-semibold tabular-nums">{item.value}</span>
            <div className="w-full max-w-10 rounded-t bg-slate-600" style={{ height: `${(item.value / max) * 85}%` }} />
          </div>
        ))}
      </div>
      <div className="flex gap-2 px-1 pt-1" aria-hidden="true">
        {items.map((item) => (
          <span key={item.key} className="min-w-8 flex-1 text-center text-xs text-slate-600">
            {item.label}
          </span>
        ))}
      </div>
      <table className="sr-only">
        <caption>{caption}</caption>
        <tbody>
          {items.map((item) => (
            <tr key={item.key}>
              <th scope="row">{item.text}</th>
              <td>{item.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
