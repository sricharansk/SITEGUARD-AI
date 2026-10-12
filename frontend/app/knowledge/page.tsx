"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, fmtDate, label, qs } from "@/lib/api";
import type { GroundedAnswer, KnowledgeDoc, SearchHit } from "@/lib/types";
import { useSession } from "@/components/Shell";
import { AiPanel, Button, Card, Empty, ErrorBanner, Field, inputCls, Loading } from "@/components/ui";

const DOC_TYPES = ["PROCEDURE", "ITP", "SPECIFICATION", "STANDARD", "METHOD_STATEMENT", "REFERENCE"];
const ANSWER_TONE: Record<GroundedAnswer["status"], string> = {
  ANSWERED: "text-good-ink",
  INSUFFICIENT_EVIDENCE: "text-ink-2",
  CONFLICTING_EVIDENCE: "text-critical-ink",
};

export default function KnowledgePage() {
  const { project, can, me } = useSession();
  const [docs, setDocs] = useState<KnowledgeDoc[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const reload = useCallback(() => {
    api.get<KnowledgeDoc[]>("/documents").then(setDocs).catch(setError);
  }, []);
  useEffect(reload, [reload]);

  // Organization-wide documents need an organization-wide membership; the server checks this again.
  const orgWide =
    !!project &&
    me.memberships.some((m) => m.organization_id === project.organization_id && !m.project_id && m.permissions.includes("MANAGE_DOCUMENTS"));

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Knowledge</h1>
      <p className="text-sm text-ink-2">
        Procedures, ITPs and standards the agents retrieve and cite. Document text is untrusted data: passages with
        instruction-like text are flagged and never cited, and answers only use documents you are allowed to see.
      </p>
      <ErrorBanner error={error} />
      <Ask projectId={project?.id} onOpen={setOpenId} />
      <Search projectId={project?.id} onOpen={setOpenId} />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card title={docs ? `Documents (${docs.length})` : "Documents"}>
          {!docs ? (
            <Loading what="Loading documents" />
          ) : docs.length === 0 ? (
            <Empty>No documents yet.</Empty>
          ) : (
            <ul className="divide-y divide-line text-sm">
              {docs.map((d) => (
                <li key={d.id} className="py-2">
                  <button type="button" className="text-left font-medium text-accent hover:underline" onClick={() => setOpenId(d.id)}>
                    {d.title}
                  </button>
                  <DocStatus d={d} />
                  <div className="text-xs text-muted">
                    {label(d.doc_type)} · {label(d.domain)} · v{d.version} · {d.scope === "organization" ? "Organization-wide" : "This project"}
                    {d.page_count ? ` · ${d.page_count} page(s)` : ""} · {d.chunks} passage(s)
                    {d.suspicious_chunks > 0 ? ` · ${d.suspicious_chunks} flagged` : ""}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="space-y-4">
          {openId && <DocDetail id={openId} onClose={() => setOpenId(null)} />}
          {can("MANAGE_DOCUMENTS") && project && (
            <Upload organizationId={project.organization_id} projectId={project.id} orgWide={orgWide} onDone={(id) => (reload(), setOpenId(id))} />
          )}
        </div>
      </div>
    </div>
  );
}

function DocStatus({ d }: { d: KnowledgeDoc }) {
  if (d.status === "READY") return null;
  return (
    <p className={`text-xs ${d.status === "FAILED" ? "text-critical-ink" : "text-ink-2"}`}>
      {label(d.status)}
      {d.error ? `: ${d.error}` : ""}
    </p>
  );
}

function Ask({ projectId, onOpen }: { projectId?: string; onOpen: (id: string) => void }) {
  const [question, setQuestion] = useState("How often must scaffolds be inspected?");
  const [answer, setAnswer] = useState<GroundedAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function ask(e: FormEvent) {
    e.preventDefault();
    if (!projectId) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await api.post<GroundedAnswer>("/knowledge/answer", { project_id: projectId, question }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const byRef = Object.fromEntries((answer?.citations ?? []).map((c) => [c.ref, c]));
  return (
    <Card title="Ask the knowledge base">
      <form onSubmit={ask} className="space-y-2">
        <Field label="Question" hint="Answers cite the passages they come from, or say the documents do not answer it.">
          <textarea className={inputCls} rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} minLength={3} maxLength={1000} required />
        </Field>
        <Button type="submit" disabled={busy || question.trim().length < 3}>
          {busy ? "Answering…" : "Ask"}
        </Button>
      </form>
      <ErrorBanner error={error} />
      {answer && (
        <div className="mt-3">
          <AiPanel title="Grounded answer" provider={answer.provider} flagged={answer.needs_human_review} reasons={answer.needs_human_review ? [answer.uncertainty] : []}>
            <p className={`mb-2 text-sm font-medium ${ANSWER_TONE[answer.status]}`} data-testid="answer-status">
              {label(answer.status)} · confidence {Math.round(answer.confidence * 100)}%
            </p>
            {answer.statements.length === 0 ? (
              <p className="text-sm">{answer.answer}</p>
            ) : (
              <ol className="list-decimal space-y-1 pl-5 text-sm">
                {answer.statements.map((s, i) => (
                  <li key={i}>
                    {s.text}{" "}
                    {s.citations.map((ref) => {
                      const c = byRef[ref];
                      return (
                        <button
                          key={ref}
                          type="button"
                          className="ml-1 rounded bg-surface-2 px-1 text-xs text-accent hover:underline"
                          onClick={() => c && onOpen(c.document_id)}
                          title={ref}
                        >
                          {c ? `${c.document_title} v${c.version}, ${c.section}${c.page ? `, p. ${c.page}` : ""}` : ref}
                        </button>
                      );
                    })}
                  </li>
                ))}
              </ol>
            )}
            {answer.conflicts.length > 0 && (
              <div className="mt-2">
                <p className="text-xs font-medium text-critical-ink">Sources disagree:</p>
                <ul className="list-disc pl-5 text-xs">
                  {answer.conflicts.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </div>
            )}
            {answer.unsupported_claims.length > 0 && (
              <p className="mt-2 text-xs text-ink-2">
                {answer.unsupported_claims.length} statement(s) were removed because no retrieved passage supports them.
              </p>
            )}
            {answer.excluded_sources.length > 0 && (
              <p className="mt-1 text-xs text-ink-2">{answer.excluded_sources.length} flagged passage(s) were left out as untrusted.</p>
            )}
            <p className="mt-2 text-xs text-muted">{answer.disclaimer}</p>
          </AiPanel>
        </div>
      )}
    </Card>
  );
}

function Search({ projectId, onOpen }: { projectId?: string; onOpen: (id: string) => void }) {
  const [q, setQ] = useState("guardrail edge protection harness");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  function search(e: FormEvent) {
    e.preventDefault();
    if (!projectId) return;
    setError(null);
    api.get<SearchHit[]>(`/search${qs({ q, project_id: projectId, limit: 8 })}`).then(setHits).catch(setError);
  }

  return (
    <Card title="Search passages">
      <form onSubmit={search} className="flex gap-2" role="search">
        <input aria-label="Search knowledge" className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} />
        <Button type="submit">Search</Button>
      </form>
      <ErrorBanner error={error} />
      {hits &&
        (hits.length === 0 ? (
          <Empty>No matching passages.</Empty>
        ) : (
          <>
            <p className="mt-3 text-xs font-medium text-ink-2">Results ({hits.length})</p>
            <ol className="mt-1 space-y-3">
              {hits.map((h) => (
              <li key={h.ref} className="text-sm">
                <div className="font-medium">
                  <button type="button" className="text-accent hover:underline" onClick={() => onOpen(h.document_id)}>
                    {h.document_title}
                  </button>{" "}
                  — {h.section}
                  {h.page ? `, page ${h.page}` : ""}
                  {h.suspicious && <span className="ml-2 text-xs text-critical-ink">⚑ instruction-like text, not citable</span>}
                </div>
                <p className="whitespace-pre-line text-ink-2">{h.text}</p>
                <div className="text-xs text-muted">
                  v{h.version} · {h.scope === "organization" ? "organization-wide" : "this project"} · score {h.score}
                  {Object.entries(h.scores).length > 0 && ` (${Object.entries(h.scores).map(([k, v]) => `${k} ${v}`).join(", ")})`} · <code>{h.ref}</code>
                </div>
              </li>
              ))}
            </ol>
          </>
        ))}
    </Card>
  );
}

function DocDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const [doc, setDoc] = useState<KnowledgeDoc | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    let current = true;
    setDoc(null);
    setError(null);
    api
      .get<KnowledgeDoc>(`/documents/${id}`)
      .then((d) => current && setDoc(d))
      .catch((e) => current && setError(e));
    return () => {
      current = false;
    };
  }, [id]);

  async function download(d: KnowledgeDoc) {
    try {
      const file = await api.blob(`/documents/${d.id}/download`);
      const url = URL.createObjectURL(file);
      const a = document.createElement("a");
      a.href = url;
      a.download = d.file_name ?? "document";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e);
    }
  }

  return (
    <Card
      title={doc ? doc.title : "Document"}
      actions={
        <button type="button" className="text-xs text-accent hover:underline" onClick={onClose}>
          Close
        </button>
      }
    >
      <ErrorBanner error={error} />
      {!doc ? (
        !error && <Loading what="Loading document" />
      ) : (
        <div className="space-y-2 text-sm">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
            <dt className="text-muted">Status</dt>
            <dd>
              {label(doc.status)}
              {doc.error ? `: ${doc.error}` : ""}
            </dd>
            <dt className="text-muted">Type / version</dt>
            <dd>
              {label(doc.doc_type)} · v{doc.version}
              {doc.effective_date ? ` · effective ${fmtDate(doc.effective_date)}` : ""}
            </dd>
            <dt className="text-muted">Source</dt>
            <dd>{doc.source}</dd>
            <dt className="text-muted">File</dt>
            <dd>
              {doc.file_name ?? "text entry"}
              {doc.parser ? ` · parsed as ${doc.parser}` : ""}
              {doc.page_count ? ` · ${doc.page_count} page(s)` : ""}
            </dd>
            <dt className="text-muted">SHA-256</dt>
            <dd className="break-all font-mono">{doc.sha256}</dd>
            {doc.tags.length > 0 && (
              <>
                <dt className="text-muted">Tags</dt>
                <dd>{doc.tags.join(", ")}</dd>
              </>
            )}
          </dl>
          {doc.file_name && doc.file_name !== "document.md" && (
            <Button variant="secondary" onClick={() => download(doc)}>
              Download original
            </Button>
          )}
          <ol className="max-h-96 space-y-2 overflow-y-auto border-t border-line pt-2">
            {(doc.chunk_list ?? []).map((c) => (
              <li key={c.ref} className="text-xs">
                <p className="font-medium">
                  {c.section}
                  {c.page ? ` · page ${c.page}` : ""}
                  {c.suspicious && <span className="ml-2 text-critical-ink">⚑ flagged, never cited</span>}
                </p>
                <p className="whitespace-pre-line text-ink-2">{c.text}</p>
              </li>
            ))}
          </ol>
        </div>
      )}
    </Card>
  );
}

function Upload({ organizationId, projectId, orgWide, onDone }: { organizationId: string; projectId: string; orgWide: boolean; onDone: (id: string) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState({ title: "", doc_type: "PROCEDURE", source: "", domain: "BOTH", version: "1", effective_date: "", tags: "", scope: "project" });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<KnowledgeDoc | null>(null);
  const [error, setError] = useState<unknown>(null);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("organization_id", organizationId);
    if (form.scope === "project") fd.append("project_id", projectId);
    for (const k of ["title", "doc_type", "source", "domain", "version", "effective_date", "tags"] as const) if (form[k]) fd.append(k, form[k]);
    setBusy(true);
    setError(null);
    try {
      const doc = await api.upload<KnowledgeDoc>("/documents/upload", fd);
      setResult(doc);
      onDone(doc.id);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Add a document">
      <form onSubmit={submit} className="space-y-2">
        <Field label="File" hint="PDF, Word (.docx), Markdown or text. Scanned PDFs without a text layer cannot be read yet.">
          <input type="file" accept=".pdf,.docx,.md,.markdown,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
        </Field>
        <Field label="Title">
          <input className={inputCls} value={form.title} onChange={set("title")} required maxLength={300} />
        </Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Type">
            <select className={inputCls} value={form.doc_type} onChange={set("doc_type")}>
              {DOC_TYPES.map((t) => (
                <option key={t} value={t}>
                  {label(t)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Domain">
            <select className={inputCls} value={form.domain} onChange={set("domain")}>
              {["SAFETY", "QUALITY", "BOTH"].map((d) => (
                <option key={d} value={d}>
                  {label(d)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Version">
            <input className={inputCls} value={form.version} onChange={set("version")} maxLength={40} required />
          </Field>
          <Field label="Effective date">
            <input type="date" className={inputCls} value={form.effective_date} onChange={set("effective_date")} />
          </Field>
        </div>
        <Field label="Source" hint="Where the document comes from, for example the issuing department or client.">
          <input className={inputCls} value={form.source} onChange={set("source")} required maxLength={500} />
        </Field>
        <Field label="Tags" hint="Comma-separated">
          <input className={inputCls} value={form.tags} onChange={set("tags")} maxLength={500} />
        </Field>
        <Field label="Who can use it">
          <select className={inputCls} value={form.scope} onChange={set("scope")}>
            <option value="project">This project only</option>
            {orgWide && <option value="organization">Every project in the organization</option>}
          </select>
        </Field>
        <Button type="submit" disabled={busy || !file}>
          {busy ? "Uploading and indexing…" : "Upload"}
        </Button>
      </form>
      <ErrorBanner error={error} />
      {result && (
        <p role="status" className={`mt-2 text-sm ${result.status === "FAILED" ? "text-critical-ink" : "text-good-ink"}`}>
          {result.duplicate
            ? "This file is already in the knowledge base; the existing document is shown."
            : result.status === "READY"
              ? `Indexed: ${result.chunks} passage(s)${result.page_count ? ` from ${result.page_count} page(s)` : ""}.`
              : `Could not be read: ${result.error}`}
        </p>
      )}
    </Card>
  );
}
