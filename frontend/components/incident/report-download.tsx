"use client";

// Incident report download (GET /incidents/{id}/report?format=md|docx|pdf&include_ai=...). The report is built from
// stored records only; AI analysis is optional and labelled AI-GENERATED inside the file. Every generation is audited
// with its SHA-256, which the API returns in X-Report-SHA256 and is shown here so the file can be matched to the log.
import { useId, useState, type FormEvent } from "react";
import { downloadReport, saveFile, type DownloadedFile } from "@/lib/api";
import { useMutation } from "@/lib/hooks";
import type { ReportFormat } from "@/lib/types";
import { DownloadIcon, ShieldIcon, SparkleIcon } from "../icons";
import { InlineError } from "../states";

export const REPORT_FORMATS: readonly { value: ReportFormat; label: string }[] = [
  { value: "pdf", label: "PDF (.pdf)" },
  { value: "docx", label: "Word (.docx)" },
  { value: "md", label: "Markdown (.md)" },
];

interface Downloaded {
  filename: string;
  sha256: string | null;
  includeAi: boolean;
}

export function ReportDownload({
  incidentId,
  save = saveFile,
}: {
  incidentId: string;
  /** Hands the file to the browser; replaced in tests. */
  save?: (file: DownloadedFile) => void;
}) {
  const id = useId();
  const mutation = useMutation();
  const [format, setFormat] = useState<ReportFormat>("pdf");
  const [includeAi, setIncludeAi] = useState(true);
  const [last, setLast] = useState<Downloaded | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLast(null);
    const file = await mutation.run(() => downloadReport(incidentId, format, includeAi));
    if (file) {
      save(file);
      setLast({ filename: file.filename, sha256: file.sha256, includeAi });
    }
  }

  return (
    <form onSubmit={onSubmit} aria-label="Download incident report" className="space-y-2">
      <p className="text-sm text-slate-700">
        Built only from the stored record: facts, lifecycle, evidence hashes, risk, actions, approvals, verification and
        cited sources.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor={`${id}-format`} className="field-label">
            Format
          </label>
          <select id={`${id}-format`} className="input" value={format} onChange={(e) => setFormat(e.target.value as ReportFormat)}>
            {REPORT_FORMATS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
        <label className="flex items-center gap-1.5 pb-1.5 text-sm">
          <input type="checkbox" checked={includeAi} onChange={(e) => setIncludeAi(e.target.checked)} />
          <span>
            Include the AI analysis <span className="text-xs text-violet-900">(labelled AI-GENERATED)</span>
          </span>
        </label>
        <button type="submit" className="btn-primary btn-sm" disabled={mutation.pending}>
          <DownloadIcon size={12} /> {mutation.pending ? "Preparing report…" : "Download report"}
        </button>
      </div>
      {includeAi ? (
        <p className="flex items-center gap-1 text-xs text-violet-900">
          <SparkleIcon size={12} /> AI sections are decision support that needs human review, never findings.
        </p>
      ) : null}
      <InlineError error={mutation.error} />
      <div role="status" aria-live="polite">
        {last ? (
          <div className="rounded border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-950" data-testid="report-result">
            <p className="font-medium">
              Downloaded {last.filename}
              {last.includeAi ? " (with labelled AI analysis)" : " (without AI analysis)"}.
            </p>
            {last.sha256 ? (
              <p className="mt-0.5 flex flex-wrap items-center gap-1 text-xs">
                <ShieldIcon size={12} /> SHA-256 recorded in the audit log:
                <code className="mono break-all select-all" data-testid="report-sha256">
                  {last.sha256}
                </code>
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </form>
  );
}
