"use client";

// Authorized knowledge search (GET /search) and the document register (GET /documents). Results are scoped by
// the API to the caller's organization and project. Retrieved text is untrusted data: it is rendered as plain
// text, and chunks flagged as suspicious (instruction-like content) are marked and never cited by agents.
import { useId, useState, type FormEvent } from "react";
import { useAppContext } from "@/components/app-context";
import { Badge, DomainBadge } from "@/components/badges";
import { AlertIcon, FileIcon } from "@/components/icons";
import { Card, PageHeader } from "@/components/layout";
import { EmptyState, ErrorState, InlineError, LoadingState, SuccessNote } from "@/components/states";
import { api } from "@/lib/api";
import { humanize } from "@/lib/format";
import { useApi, useMutation } from "@/lib/hooks";
import { can } from "@/lib/permissions";
import { DOMAINS, type KnowledgeDocument, type Project, type SearchHit } from "@/lib/types";

function SuspiciousFlag({ count }: { count?: number }) {
  return (
    <Badge tone="red" icon={<AlertIcon size={12} />} label="Warning">
      {count === undefined ? "Suspicious content" : `${count} suspicious`}
    </Badge>
  );
}

function scopeLabel(doc: KnowledgeDocument, project: Project): string {
  if (!doc.project_id) return "Organization-wide";
  return doc.project_id === project.id ? `This project (${project.code})` : "Another project";
}

function SearchSection({ project }: { project: Project }) {
  const id = useId();
  const [text, setText] = useState("");
  const [domain, setDomain] = useState("");
  const [query, setQuery] = useState<{ q: string; domain: string } | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const hits = useApi<SearchHit[]>(query ? "/search" : null, {
    q: query?.q,
    project_id: project.id,
    domain: query?.domain,
    limit: 10,
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const q = text.trim();
    if (q.length < 2) {
      setLocalError("Enter at least 2 characters.");
      return;
    }
    setLocalError(null);
    setQuery({ q, domain });
  }

  return (
    <Card title="Search procedures, ITPs and references" id="search">
      <form role="search" onSubmit={onSubmit} className="grid gap-2 sm:grid-cols-[3fr_1fr_auto]">
        <div>
          <label htmlFor={`${id}-q`} className="field-label">
            Search text
          </label>
          <input id={`${id}-q`} type="search" className="input" maxLength={500} value={text} onChange={(e) => setText(e.target.value)} />
        </div>
        <div>
          <label htmlFor={`${id}-domain`} className="field-label">
            Domain
          </label>
          <select id={`${id}-domain`} className="input" value={domain} onChange={(e) => setDomain(e.target.value)}>
            <option value="">All</option>
            {DOMAINS.map((d) => (
              <option key={d} value={d}>
                {humanize(d)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-end">
          <button type="submit" className="btn-primary">
            Search
          </button>
        </div>
      </form>
      {localError ? (
        <p role="alert" className="mt-2 text-sm font-medium text-red-800">
          {localError}
        </p>
      ) : null}
      <div className="mt-3" aria-live="polite">
        {!query ? (
          <p className="text-slate-600">
            Search runs over organization-wide documents and documents for {project.code}. Every result shows its
            source and citation ID.
          </p>
        ) : hits.status === "error" && hits.error ? (
          <ErrorState error={hits.error} onRetry={hits.reload} what="knowledge search" />
        ) : !hits.data ? (
          <LoadingState label="Searching…" />
        ) : hits.data.length === 0 ? (
          <EmptyState title={`No results for “${query.q}”`}>Try different wording or remove the domain filter.</EmptyState>
        ) : (
          <>
            <p className="mb-2 text-xs text-slate-600">
              {hits.data.length} result(s), ranked by BM25 relevance. Retrieved text is reference material, not an
              instruction; confirm against the controlled document.
            </p>
            <ol className="space-y-2">
              {hits.data.map((h) => (
                <li key={h.ref} className={`rounded border p-3 ${h.suspicious ? "border-red-300 bg-red-50/50" : "border-slate-200 bg-white"}`}>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <FileIcon size={14} className="text-slate-600" />
                    <span className="font-semibold">{h.document_title}</span>
                    <span className="text-slate-600">· {h.section}</span>
                    <Badge>{h.doc_type}</Badge>
                    <DomainBadge domain={h.domain} />
                    {h.suspicious ? <SuspiciousFlag /> : null}
                    <span className="ml-auto text-xs text-slate-500 tabular-nums">score {h.score.toFixed(2)}</span>
                  </div>
                  {h.suspicious ? (
                    <p className="mt-1 text-xs font-medium text-red-900">
                      This excerpt contains instruction-like text. It is shown for review only; agents never cite it.
                    </p>
                  ) : null}
                  <p className="mt-1.5 whitespace-pre-line text-slate-800">{h.text}</p>
                  <p className="mt-1 text-xs text-slate-600">
                    Source: {h.source} · Citation <code className="mono">{h.ref}</code>
                  </p>
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </Card>
  );
}

function AddDocumentForm({ project, onAdded }: { project: Project; onAdded: () => void }) {
  const id = useId();
  const mutation = useMutation();
  const [open, setOpen] = useState(false);
  const empty = { title: "", doc_type: "PROCEDURE", source: "", domain: "BOTH", version: "1", scope: "project", text: "" };
  const [form, setForm] = useState(empty);
  const [localError, setLocalError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLocalError(null);
    if (!form.title.trim() || !form.source.trim() || !form.doc_type.trim() || !form.text.trim()) {
      setLocalError("Title, document type, source and text are required.");
      return;
    }
    const body = {
      organization_id: project.organization_id,
      project_id: form.scope === "project" ? project.id : null,
      title: form.title.trim(),
      doc_type: form.doc_type.trim(),
      source: form.source.trim(),
      domain: form.domain,
      version: form.version.trim() || "1",
      text: form.text,
    };
    const saved = await mutation.run(
      () => api<KnowledgeDocument>("/documents", { method: "POST", body }),
      "Document ingested and chunked.",
    );
    if (saved) {
      setForm(empty);
      setOpen(false);
      onAdded();
    }
  }

  if (!open) {
    return (
      <div>
        <button type="button" className="btn-secondary btn-sm" onClick={() => setOpen(true)}>
          Add a document
        </button>
        <SuccessNote message={mutation.success} />
      </div>
    );
  }
  const input = (key: "title" | "doc_type" | "source" | "version", label: string) => (
    <div>
      <label htmlFor={`${id}-${key}`} className="field-label">
        {label}
      </label>
      <input id={`${id}-${key}`} className="input" value={form[key]} onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))} />
    </div>
  );
  return (
    <form onSubmit={onSubmit} className="rounded border border-slate-200 bg-slate-50 p-3" aria-label="Add a document">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {input("title", "Title")}
        {input("doc_type", "Document type (e.g. PROCEDURE, ITP)")}
        {input("source", "Source (where the official copy lives)")}
        {input("version", "Version")}
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
            <option value="project">This project only</option>
            <option value="organization">Whole organization</option>
          </select>
        </div>
        <div className="sm:col-span-2 lg:col-span-3">
          <label htmlFor={`${id}-text`} className="field-label">
            Text or Markdown (headings become sections)
          </label>
          <textarea id={`${id}-text`} className="input mono min-h-40" value={form.text} onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))} />
        </div>
      </div>
      <div className="mt-2 flex gap-2">
        <button type="submit" className="btn-primary btn-sm" disabled={mutation.pending}>
          Ingest document
        </button>
        <button type="button" className="btn-secondary btn-sm" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      <p className="field-hint">Do not paste licensed standards text unless your organization holds the rights.</p>
      {localError ? (
        <p role="alert" className="mt-2 text-sm font-medium text-red-800">
          {localError}
        </p>
      ) : null}
      <InlineError error={mutation.error} />
    </form>
  );
}

export default function KnowledgePage() {
  const { project } = useAppContext();
  const docs = useApi<KnowledgeDocument[]>(project ? "/documents" : null);
  if (!project) return null;
  const suspiciousDocs = docs.data?.filter((d) => d.suspicious_chunks > 0).length ?? 0;

  return (
    <>
      <PageHeader
        kicker={`${project.code} · ${project.name}`}
        title="Knowledge"
        subtitle="Procedures, inspection and test plans and regulatory pointers the agents retrieve from."
      />
      <div className="space-y-4">
        <SearchSection project={project} />
        <Card
          title={docs.data ? `Documents (${docs.data.length})` : "Documents"}
          id="documents"
          bodyClassName="overflow-x-auto"
          actions={
            suspiciousDocs > 0 ? (
              <span className="text-xs font-semibold text-red-800">{suspiciousDocs} with suspicious content</span>
            ) : null
          }
        >
          {can(project.permissions, "MANAGE_DOCUMENTS") ? (
            <div className="px-4 pt-3">
              <AddDocumentForm project={project} onAdded={docs.reload} />
            </div>
          ) : null}
          {docs.status === "error" && docs.error ? (
            <ErrorState error={docs.error} onRetry={docs.reload} what="documents" />
          ) : !docs.data ? (
            <LoadingState label="Loading documents…" />
          ) : docs.data.length === 0 ? (
            <EmptyState title="No documents yet">Documents added by a QA/QC engineer or HSE manager appear here.</EmptyState>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">Type</th>
                  <th scope="col">Version</th>
                  <th scope="col">Domain</th>
                  <th scope="col">Scope</th>
                  <th scope="col">Chunks</th>
                  <th scope="col">Source</th>
                </tr>
              </thead>
              <tbody>
                {docs.data.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <span className="font-medium">{d.title}</span>
                      {d.suspicious_chunks > 0 ? (
                        <span className="ml-1.5">
                          <SuspiciousFlag count={d.suspicious_chunks} />
                        </span>
                      ) : null}
                      <div className="mono text-slate-500" title={`SHA-256 ${d.sha256}`}>
                        SHA-256 {d.sha256.slice(0, 12)}…
                      </div>
                    </td>
                    <td>
                      <Badge>{d.doc_type}</Badge>
                    </td>
                    <td className="tabular-nums whitespace-nowrap">v{d.version}</td>
                    <td>
                      <DomainBadge domain={d.domain} />
                    </td>
                    <td className="whitespace-nowrap text-slate-700">{scopeLabel(d, project)}</td>
                    <td className="tabular-nums">{d.chunks}</td>
                    <td className="text-xs text-slate-700">{d.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </>
  );
}
