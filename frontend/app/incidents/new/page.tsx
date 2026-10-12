"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import type { Incident } from "@/lib/types";
import { useSession } from "@/components/Shell";
import { Button, Card, ErrorBanner, Field, inputCls } from "@/components/ui";

function localNow() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export default function NewIncidentPage() {
  const { project, can } = useSession();
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({
    title: "",
    description: "",
    domain: "SAFETY",
    severity: "MEDIUM",
    occurred_at: localNow(),
    site_id: "",
    location: "",
    activity: "",
    people_involved: 0,
    immediate_actions: "",
  });
  if (!project) return null;
  if (!can("CREATE_INCIDENT")) return <ErrorBanner error={{ code: "FORBIDDEN", message: "Your role cannot report incidents on this project." }} />;

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: k === "people_involved" ? Number(e.target.value) : e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        ...form,
        occurred_at: new Date(form.occurred_at).toISOString(),
        site_id: form.site_id || null,
        location: form.location || null,
        activity: form.activity || null,
        immediate_actions: form.immediate_actions || null,
      };
      const inc = await api.post<Incident>(`/projects/${project!.id}/incidents`, body);
      if (file) {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("description", "Uploaded with the incident report");
        await api.upload(`/incidents/${inc.id}/evidence`, fd);
      }
      router.push(`/incident/?id=${inc.id}`);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-xl font-semibold">Report an incident</h1>
      <p className="text-sm text-ink-2">
        Injuries, near misses, dangerous occurrences and quality non-conformances. Describe what happened, the conditions and the
        people involved; the AI investigation reads exactly what you write here.
      </p>
      <Card>
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field label="Title">
              <input className={inputCls} value={form.title} onChange={set("title")} required minLength={3} maxLength={300} />
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="What happened" hint="Sequence of events, equipment, conditions, controls in place or missing.">
              <textarea className={`${inputCls} min-h-32`} value={form.description} onChange={set("description")} required minLength={10} />
            </Field>
          </div>
          <Field label="Domain">
            <select className={inputCls} value={form.domain} onChange={set("domain")}>
              <option value="SAFETY">Safety</option>
              <option value="QUALITY">Quality</option>
              <option value="BOTH">Both</option>
            </select>
          </Field>
          <Field label="Severity (your assessment)">
            <select className={inputCls} value={form.severity} onChange={set("severity")}>
              {["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => (
                <option key={s} value={s}>
                  {s.charAt(0) + s.slice(1).toLowerCase()}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Occurred at">
            <input type="datetime-local" className={inputCls} value={form.occurred_at} onChange={set("occurred_at")} required />
          </Field>
          <Field label="Site">
            <select className={inputCls} value={form.site_id} onChange={set("site_id")}>
              <option value="">Not specified</option>
              {project.sites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Exact location">
            <input className={inputCls} value={form.location} onChange={set("location")} placeholder="Level, grid, area" />
          </Field>
          <Field label="Activity">
            <input className={inputCls} value={form.activity} onChange={set("activity")} placeholder="Task being done" />
          </Field>
          <Field label="People involved">
            <input type="number" min={0} className={inputCls} value={form.people_involved} onChange={set("people_involved")} />
          </Field>
          <Field label="Evidence (photo, PDF or text, up to 10 MB)">
            <input type="file" accept=".jpg,.jpeg,.png,.pdf,.txt" className="text-sm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Immediate actions taken">
              <textarea className={inputCls} value={form.immediate_actions} onChange={set("immediate_actions")} />
            </Field>
          </div>
          <div className="sm:col-span-2 space-y-2">
            <ErrorBanner error={error} />
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Report incident"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
