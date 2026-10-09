"use client";

// Evidence list (download through the BFF) and upload (multipart to POST /incidents/{id}/evidence). The server
// validates extension, MIME type, magic bytes and size and records a SHA-256; the client checks are a courtesy.
import { useId, useRef, useState, type FormEvent } from "react";
import { api, evidenceDownloadUrl } from "@/lib/api";
import { formatBytes, formatDateTime } from "@/lib/format";
import { useMutation } from "@/lib/hooks";
import type { Evidence } from "@/lib/types";
import { DownloadIcon, FileIcon, ShieldIcon } from "../icons";
import { EmptyState, InlineError, SuccessNote } from "../states";
import { personName, type People } from "./people";

export const ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".pdf", ".txt"];
export const MAX_EVIDENCE_BYTES = 10 * 1024 * 1024; // SITEGUARD_EVIDENCE_MAX_BYTES default

export function checkEvidenceFile(file: Pick<File, "name" | "size">): string | null {
  const dot = file.name.lastIndexOf(".");
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!ALLOWED_EXTENSIONS.includes(ext)) return `Allowed file types: ${ALLOWED_EXTENSIONS.join(", ")}.`;
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_EVIDENCE_BYTES) return `The file is larger than ${formatBytes(MAX_EVIDENCE_BYTES)}.`;
  return null;
}

export function EvidencePanel({
  incidentId,
  evidence,
  people,
  canUpload,
  onChanged,
}: {
  incidentId: string;
  evidence: Evidence[];
  people: People;
  canUpload: boolean;
  onChanged: () => void;
}) {
  const id = useId();
  const mutation = useMutation();
  const fileRef = useRef<HTMLInputElement>(null);
  const [description, setDescription] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLocalError(null);
    const file = fileRef.current?.files?.[0];
    if (!file) return setLocalError("Choose a file to upload.");
    const problem = checkEvidenceFile(file);
    if (problem) return setLocalError(problem);
    const body = new FormData();
    body.append("file", file);
    if (description.trim()) body.append("description", description.trim());
    const saved = await mutation.run(
      () => api<Evidence>(`/incidents/${incidentId}/evidence`, { method: "POST", body }),
      `Uploaded ${file.name}; SHA-256 recorded.`,
    );
    if (saved) {
      setDescription("");
      if (fileRef.current) fileRef.current.value = "";
      onChanged();
    }
  }

  return (
    <div className="space-y-3">
      {evidence.length === 0 ? (
        <EmptyState title="No evidence attached yet">Photos, PDFs and text notes strengthen the investigation.</EmptyState>
      ) : (
        <ul className="divide-y divide-slate-100" aria-label="Evidence files">
          {evidence.map((e) => (
            <li key={e.id} className="py-2">
              <div className="flex flex-wrap items-center gap-2">
                <FileIcon size={14} className="text-emerald-700" />
                <a className="link" href={evidenceDownloadUrl(e.id)} download={e.filename}>
                  {e.filename}
                </a>
                <a className="btn-secondary btn-sm" href={evidenceDownloadUrl(e.id)} download={e.filename} aria-label={`Download ${e.filename}`}>
                  <DownloadIcon size={12} /> Download
                </a>
                <span className="text-xs text-slate-600">
                  {e.content_type} · {formatBytes(e.size_bytes)}
                </span>
              </div>
              {e.description ? <p className="mt-0.5 text-sm text-slate-800">{e.description}</p> : null}
              <p className="mt-0.5 flex flex-wrap items-center gap-1 text-xs text-slate-600">
                <ShieldIcon size={12} className="text-emerald-700" />
                <span>SHA-256</span>
                <code className="mono break-all text-slate-700" title={e.sha256}>
                  {e.sha256.slice(0, 16)}…
                </code>
                <span>
                  · uploaded {formatDateTime(e.created_at)} by {personName(people, e.uploaded_by)}
                </span>
              </p>
            </li>
          ))}
        </ul>
      )}
      {canUpload ? (
        <form onSubmit={onSubmit} className="rounded border border-slate-200 bg-slate-50 p-3" aria-label="Upload evidence">
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <label htmlFor={`${id}-file`} className="field-label">
                Evidence file
              </label>
              <input
                id={`${id}-file`}
                ref={fileRef}
                type="file"
                accept={ALLOWED_EXTENSIONS.join(",")}
                className="block w-full text-sm file:mr-2 file:rounded file:border file:border-slate-300 file:bg-white file:px-2 file:py-1"
                aria-describedby={`${id}-hint`}
              />
              <p id={`${id}-hint`} className="field-hint">
                JPG, PNG, PDF or UTF-8 text, up to {formatBytes(MAX_EVIDENCE_BYTES)}.
              </p>
            </div>
            <div>
              <label htmlFor={`${id}-description`} className="field-label">
                Description (optional)
              </label>
              <input
                id={`${id}-description`}
                className="input"
                maxLength={2000}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>
          <button type="submit" className="btn-primary btn-sm mt-2" disabled={mutation.pending}>
            {mutation.pending ? "Uploading…" : "Upload evidence"}
          </button>
          {localError ? (
            <p role="alert" className="mt-2 text-sm font-medium text-red-800">
              {localError}
            </p>
          ) : null}
          <InlineError error={mutation.error} />
          <SuccessNote message={mutation.success} />
        </form>
      ) : null}
    </div>
  );
}
