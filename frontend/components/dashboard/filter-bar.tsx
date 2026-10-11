"use client";

// One row of filters above the dashboard: scope (this project or every project the user can read), period of
// incident occurrence and trend interval. Changes are staged and applied together, so every tile, chart and table
// below always shows the same slice.
import { useId, useState, type FormEvent } from "react";
import { PRESETS, presetRange, validateFilters, type DashboardFilters, type PeriodPreset } from "@/lib/dashboard";
import type { Project, TrendInterval } from "@/lib/types";

export function DashboardFilterBar({
  value,
  project,
  projectCount,
  onApply,
  busy = false,
}: {
  value: DashboardFilters;
  project: Pick<Project, "code" | "name">;
  /** Projects the user can read; the "all" scope is offered only when there is more than one. */
  projectCount: number;
  onApply: (filters: DashboardFilters) => void;
  busy?: boolean;
}) {
  const id = useId();
  const [draft, setDraft] = useState<DashboardFilters>(value);
  const [error, setError] = useState<string | null>(null);

  function choosePreset(preset: PeriodPreset) {
    const range = presetRange(preset);
    setDraft((d) => ({ ...d, preset, ...(range ?? {}) }));
    setError(null);
  }

  function setDay(key: "from" | "to", day: string) {
    setDraft((d) => ({ ...d, [key]: day, preset: "custom" }));
    setError(null);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const problem = validateFilters(draft);
    setError(problem);
    if (!problem) onApply(draft);
  }

  return (
    <form
      onSubmit={onSubmit}
      aria-label="Dashboard filters"
      className="flex flex-wrap items-end gap-3 rounded-md border border-slate-200 bg-white px-3 py-2.5 shadow-xs"
      noValidate
    >
      <div>
        <label htmlFor={`${id}-period`} className="field-label">
          Period (date occurred, UTC)
        </label>
        <select
          id={`${id}-period`}
          className="input"
          value={draft.preset}
          onChange={(e) => choosePreset(e.target.value as PeriodPreset)}
        >
          {PRESETS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor={`${id}-from`} className="field-label">
          From
        </label>
        <input
          id={`${id}-from`}
          type="date"
          className="input"
          value={draft.from}
          max={draft.to || undefined}
          onChange={(e) => setDay("from", e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
        />
      </div>
      <div>
        <label htmlFor={`${id}-to`} className="field-label">
          To
        </label>
        <input
          id={`${id}-to`}
          type="date"
          className="input"
          value={draft.to}
          min={draft.from || undefined}
          onChange={(e) => setDay("to", e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
        />
      </div>
      <div>
        <label htmlFor={`${id}-interval`} className="field-label">
          Trend by
        </label>
        <select
          id={`${id}-interval`}
          className="input"
          value={draft.interval}
          onChange={(e) => setDraft((d) => ({ ...d, interval: e.target.value as TrendInterval }))}
        >
          <option value="month">Month</option>
          <option value="week">Week (ISO)</option>
        </select>
      </div>
      {projectCount > 1 ? (
        <div>
          <label htmlFor={`${id}-scope`} className="field-label">
            Projects
          </label>
          <select
            id={`${id}-scope`}
            className="input"
            value={draft.scope}
            onChange={(e) => setDraft((d) => ({ ...d, scope: e.target.value as DashboardFilters["scope"] }))}
          >
            <option value="project">
              {project.code} · {project.name}
            </option>
            <option value="all">All my projects ({projectCount})</option>
          </select>
        </div>
      ) : null}
      <div className="flex gap-2">
        <button type="submit" className="btn-primary" disabled={busy}>
          Apply filters
        </button>
      </div>
      {error ? (
        <p id={`${id}-error`} role="alert" className="w-full text-sm font-medium text-red-800">
          {error}
        </p>
      ) : null}
    </form>
  );
}
