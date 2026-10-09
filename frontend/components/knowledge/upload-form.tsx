"use client";

// Upload a knowledge document (multipart POST /documents/upload). The API parses, chunks and indexes the file in the
// same request and returns its processing status: READY, or FAILED with the reason (the original is kept), or the
// existing document when the same content, version and scope is already in the library. The browser checks are a
// courtesy; the API validates type, declared type, size and scope again.
import { useId, useRef, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { formatBytes, humanize } from "@/lib/format";
import { useMutation } from "@/lib/hooks";
import { DOMAINS, type KnowledgeDocument, type Project } from "@/lib/types";
import { DocumentStatusBadge } from "../badges";
import { SpinnerIcon } from "../icons";
import { InlineError } from "../states";

export const DOCUMENT_EXTENSIONS = [".pdf", ".docx", ".md", ".markdown", ".txt"];
export const MAX_DOCUMENT_BYTES = 25 * 1024 * 1024; // SITEGUARD_DOCUMENT_MAX_BYTES default

export function checkDocumentFile(file: Pick<File, "name" | "size">): string | null {
  const dot = file.name.lastIndexOf(".");
  const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : "";
  if (!DOCUMENT_EXTENSIONS.includes(ext)) return `Allowed file types: ${DOCUMENT_EXTENSIONS.join(", ")}.`;
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_DOCUMENT_BYTES) return `The file is larger than ${formatBytes(MAX_DOCUMENT_BYTES)}.`;
  return null;
}

function titleFromFile(name: string): string {
  const dot = name.lastIndexOf(".");
  return (dot > 0 ? name.slice(0, dot) : name).replace(/[_-]+/g, " ").trim();
}

/** What happened to the uploaded document, in words: the processing status the API returned. */
export function ProcessingResult({ doc }: { doc: KnowledgeDocument }) {
  return (
    <div role="status" className="mt-2 rounded border border-slate-200 bg-white px-3 py-2 text-sm" data-testid="upload-result">
      <p className="flex flex-wrap items-center gap-1.5">
        <span className="font-semibold">{doc.title}</span>
        <span className="text-slate-600">v{doc.version}</span>
        <DocumentStatusBadge status={doc.status} />
      </p>
      {doc.duplicate ? (
        <p className="mt-1 text-slate-700">
          Already in the library with the same content, version and scope. Nothing new was added.
        </p>
      ) : doc.status === "READY" ? (
        <p className="mt-1 text-slate-700">
          Parsed{doc.page_count ? ` ${doc.page_count} page(s)` : ""} and indexed {doc.chunks} section chunk(s); it is now
          searchable.
          {doc.suspicious_chunks > 0 ? ` ${doc.suspicious_chunks} chunk(s) contain instruction-like text and are never cited.` : ""}
        </p>
      ) : doc.status === "FAILED" ? (
        <p className="mt-1 text-red-900">
          Processing failed: {doc.error ?? "the file could not be read"}. The original file is kept; it is not searchable.
        </p>
      ) : (
        <p className="mt-1 text-slate-700">Processing has not finished; reload the list to see the result.</p>
      )}
    </div>
  );
}

export function UploadDocumentForm({
  project,
  canUseOrganizationScope,
  onUploaded,
  onCancel,
}: {
  project: Project;
  /** Organization-wide MANAGE_DOCUMENTS (from /me); the API checks it again. */
  canUseOrganizationScope: boolean;
  onUploaded: (doc: KnowledgeDocument) => void;
  onCancel?: () => void;
}) {
  const id = useId();
  const mutation = useMutation();
  const fileRef = useRef<HTMLInputElement>(null);
  const empty = { title: "", doc_type: "PROCEDURE", source: "", version: "1", domain: "BOTH", effective_date: "", tags: "", scope: "project" };
  const [form, setForm] = useState(empty);
  const [localError, setLocalError] = useState<string | null>(null);
  const [result, setResult] = useState<KnowledgeDocument | null>(null);

  function onFileChosen() {
    const file = fileRef.current?.files?.[0];
    if (file && !form.title.trim()) setForm((f) => ({ ...f, title: titleFromFile(file.name) }));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLocalError(null);
    setResult(null);
    const file = fileRef.current?.files?.[0];
    if (!file) return setLocalError("Choose a file to upload.");
    const problem = checkDocumentFile(file);
    if (problem) return setLocalError(problem);
    if (!form.title.trim() || !form.doc_type.trim() || !form.source.trim()) {
      return setLocalError("Title, document type and source are required.");
    }
    const body = new FormData();
    body.append("file", file);
    body.append("organization_id", project.organization_id);
    if (form.scope === "project") body.append("project_id", project.id);
    body.append("title", form.title.trim());
    body.append("doc_type", form.doc_type.trim());
    body.append("source", form.source.trim());
    body.append("version", form.version.trim() || "1");
    body.append("domain", form.domain);
    if (form.effective_date) body.append("effective_date", form.effective_date);
    if (form.tags.trim()) body.append("tags", form.tags.trim());
    const saved = await mutation.run(() => api<KnowledgeDocument>("/documents/upload", { method: "POST", body }), "Upload finished.");
    if (saved) {
      setResult(saved);
      setForm(empty);
      if (fileRef.current) fileRef.current.value = "";
      onUploaded(saved);
    }
  }

  const text = (key: "title" | "doc_type" | "source" | "version" | "tags", label: string, hint?: string) => (
    <div>
      <label htmlFor={`${id}-${key}`} className="field-label">
        {label}
      </label>
      <input id={`${id}-${key}`} className="input" value={form[key]} onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))} />
      {hint ? <p className="field-hint">{hint}</p> : null}
    </div>
  );

  return (
    <form onSubmit={onSubmit} className="rounded border border-slate-200 bg-slate-50 p-3" aria-label="Upload a document">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <div className="sm:col-span-2 lg:col-span-3">
          <label htmlFor={`${id}-file`} className="field-label">
            Document file
          </label>
          <input
            id={`${id}-file`}
            ref={fileRef}
            type="file"
            accept={DOCUMENT_EXTENSIONS.join(",")}
            onChange={onFileChosen}
            className="block w-full text-sm file:mr-2 file:rounded file:border file:border-slate-300 file:bg-white file:px-2 file:py-1"
            aria-describedby={`${id}-file-hint`}
          />
          <p id={`${id}-file-hint`} className="field-hint">
            PDF, Word (.docx), Markdown or text, up to {formatBytes(MAX_DOCUMENT_BYTES)}. Scanned PDFs without a text layer
            cannot be read.
          </p>
        </div>
        {text("title", "Title")}
        {text("doc_type", "Document type (e.g. PROCEDURE, ITP)")}
        {text("source", "Source (where the official copy lives)")}
        {text("version", "Version")}
        <div>
          <label htmlFor={`${id}-effective`} className="field-label">
            Effective date (optional)
          </label>
          <input
            id={`${id}-effective`}
            type="date"
            className="input"
            value={form.effective_date}
            onChange={(e) => setForm((f) => ({ ...f, effective_date: e.target.value }))}
          />
        </div>
        {text("tags", "Tags (optional, comma-separated)")}
        <div>
          <label htmlFor={`${id}-domain`} className="field-label">
            Domain
          </label>
          <select id={`${id}-domain`} className="input" value={form.domain} onChange={(e) => setForm((f) => ({ ...f, domain: e.target.value }))}>
            {DOMAINS.map((d) => (
              <option key={d} value={d}>
                {humanize(d)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-scope`} className="field-label">
            Visible to
          </label>
          <select id={`${id}-scope`} className="input" value={form.scope} onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value }))}>
            <option value="project">This project only ({project.code})</option>
            {canUseOrganizationScope ? <option value="organization">Whole organization</option> : null}
          </select>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="submit" className="btn-primary btn-sm" disabled={mutation.pending}>
          {mutation.pending ? (
            <>
              <SpinnerIcon size={12} /> Uploading and processing…
            </>
          ) : (
            "Upload document"
          )}
        </button>
        {onCancel ? (
          <button type="button" className="btn-secondary btn-sm" onClick={onCancel}>
            Close
          </button>
        ) : null}
      </div>
      <p className="field-hint">
        Uploaded text is treated as reference data, never as instructions. Do not upload licensed standards unless your
        organization holds the rights.
      </p>
      {localError ? (
        <p role="alert" className="mt-2 text-sm font-medium text-red-800">
          {localError}
        </p>
      ) : null}
      <InlineError error={mutation.error} />
      {result ? <ProcessingResult doc={result} /> : null}
    </form>
  );
}
