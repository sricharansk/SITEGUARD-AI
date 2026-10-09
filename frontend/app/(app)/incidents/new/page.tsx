"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { useAppContext } from "@/components/app-context";
import { AlertIcon } from "@/components/icons";
import { PageHeader } from "@/components/layout";
import { InlineError, UnauthorizedState } from "@/components/states";
import { api } from "@/lib/api";
import { humanize, nowForInput } from "@/lib/format";
import { useMutation } from "@/lib/hooks";
import { toIncidentBody, validateIncident, type IncidentForm } from "@/lib/incident-form";
import { can } from "@/lib/permissions";
import { DOMAINS, SEVERITIES, type Incident } from "@/lib/types";

export default function NewIncidentPage() {
  const { project } = useAppContext();
  const router = useRouter();
  const mutation = useMutation();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [form, setForm] = useState<IncidentForm>(() => ({
    title: "",
    description: "",
    domain: "SAFETY",
    severity: "MEDIUM",
    occurred_at: nowForInput(),
    site_id: "",
    category: "",
    location: "",
    activity: "",
    people_involved: "0",
    immediate_actions: "",
  }));

  if (!project) return null;
  if (!can(project.permissions, "CREATE_INCIDENT")) {
    return (
      <>
        <PageHeader title="Report incident" />
        <UnauthorizedState what="incidents in this project (CREATE_INCIDENT is required)" />
      </>
    );
  }

  const set = (key: keyof IncidentForm) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!project) return;
    const found = validateIncident(form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    const body = toIncidentBody(form);
    const created = await mutation.run(
      () => api<Incident>(`/projects/${project.id}/incidents`, { method: "POST", body }),
      "Incident reported.",
    );
    if (created) router.push(`/incidents/${created.id}`);
  }

  const fieldError = (key: string) =>
    errors[key] ? (
      <p id={`${key}-error`} className="mt-1 text-xs font-medium text-red-800">
        {errors[key]}
      </p>
    ) : null;
  const describedBy = (key: string, hint?: boolean) =>
    [errors[key] ? `${key}-error` : null, hint ? `${key}-hint` : null].filter(Boolean).join(" ") || undefined;

  return (
    <>
      <PageHeader
        kicker={`${project.code} · ${project.name}`}
        title="Report an incident or quality observation"
        actions={
          <Link href="/incidents" className="btn-secondary">
            Cancel
          </Link>
        }
      />
      <div
        role="note"
        className="mb-4 flex gap-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900"
      >
        <AlertIcon size={16} className="mt-0.5 shrink-0" />
        <p>
          <strong>Emergency?</strong> Follow your site emergency procedure and escalate to the HSE manager first. This
          platform records and supports the investigation; it does not replace emergency response.
        </p>
      </div>
      <form onSubmit={onSubmit} noValidate className="card" aria-label="New incident">
        <div className="card-body grid gap-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <label htmlFor="title" className="field-label">
              Title (required)
            </label>
            <input
              id="title"
              className="input"
              value={form.title}
              onChange={set("title")}
              maxLength={300}
              required
              aria-invalid={Boolean(errors.title)}
              aria-describedby={describedBy("title")}
            />
            {fieldError("title")}
          </div>
          <div className="md:col-span-2">
            <label htmlFor="description" className="field-label">
              What happened (required)
            </label>
            <textarea
              id="description"
              className="input min-h-28"
              value={form.description}
              onChange={set("description")}
              maxLength={20000}
              required
              aria-invalid={Boolean(errors.description)}
              aria-describedby={describedBy("description", true)}
            />
            <p id="description-hint" className="field-hint">
              Facts only: what was seen, where, who was involved (no names needed) and the conditions.
            </p>
            {fieldError("description")}
          </div>
          <div>
            <label htmlFor="domain" className="field-label">
              Domain
            </label>
            <select id="domain" className="input" value={form.domain} onChange={set("domain")}>
              {DOMAINS.map((d) => (
                <option key={d} value={d}>
                  {humanize(d)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="severity" className="field-label">
              Reported severity
            </label>
            <select id="severity" className="input" value={form.severity} onChange={set("severity")}>
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {humanize(s)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="occurred_at" className="field-label">
              When it happened (required)
            </label>
            <input
              id="occurred_at"
              type="datetime-local"
              className="input"
              value={form.occurred_at}
              onChange={set("occurred_at")}
              required
              aria-invalid={Boolean(errors.occurred_at)}
              aria-describedby={describedBy("occurred_at")}
            />
            {fieldError("occurred_at")}
          </div>
          <div>
            <label htmlFor="site_id" className="field-label">
              Site
            </label>
            <select id="site_id" className="input" value={form.site_id} onChange={set("site_id")}>
              <option value="">Not specified</option>
              {project.sites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="location" className="field-label">
              Location on site
            </label>
            <input
              id="location"
              className="input"
              value={form.location}
              onChange={set("location")}
              maxLength={300}
              aria-describedby={describedBy("location")}
            />
            {fieldError("location")}
          </div>
          <div>
            <label htmlFor="activity" className="field-label">
              Activity under way
            </label>
            <input
              id="activity"
              className="input"
              value={form.activity}
              onChange={set("activity")}
              maxLength={200}
              aria-describedby={describedBy("activity")}
            />
            {fieldError("activity")}
          </div>
          <div>
            <label htmlFor="category" className="field-label">
              Category
            </label>
            <input
              id="category"
              className="input"
              value={form.category}
              onChange={set("category")}
              maxLength={80}
              aria-describedby={describedBy("category")}
            />
            {fieldError("category")}
          </div>
          <div>
            <label htmlFor="people_involved" className="field-label">
              People involved
            </label>
            <input
              id="people_involved"
              type="number"
              min={0}
              max={10000}
              step={1}
              className="input"
              value={form.people_involved}
              onChange={set("people_involved")}
              aria-invalid={Boolean(errors.people_involved)}
              aria-describedby={describedBy("people_involved")}
            />
            {fieldError("people_involved")}
          </div>
          <div className="md:col-span-2">
            <label htmlFor="immediate_actions" className="field-label">
              Immediate actions taken
            </label>
            <textarea
              id="immediate_actions"
              className="input min-h-20"
              value={form.immediate_actions}
              onChange={set("immediate_actions")}
              maxLength={5000}
              aria-describedby={describedBy("immediate_actions")}
            />
            {fieldError("immediate_actions")}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 px-4 py-3">
          <button type="submit" className="btn-primary" disabled={mutation.pending}>
            {mutation.pending ? "Saving…" : "Save incident"}
          </button>
          <p className="text-xs text-slate-600">
            After saving, add evidence and run the AI investigation from the incident workspace.
          </p>
        </div>
        <div className="px-4 pb-3">
          {Object.keys(errors).length > 0 ? (
            <p role="alert" className="text-sm font-medium text-red-800">
              Fix the highlighted fields and save again.
            </p>
          ) : null}
          <InlineError error={mutation.error} />
        </div>
      </form>
    </>
  );
}
