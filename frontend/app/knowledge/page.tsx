"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, label, qs } from "@/lib/api";
import { useSession } from "@/components/Shell";
import { Button, Card, Empty, ErrorBanner, inputCls } from "@/components/ui";

interface Doc {
  id: string;
  title: string;
  doc_type: string;
  source: string;
  version: string;
  domain: string;
  chunks: number;
  suspicious_chunks: number;
}
interface Hit {
  ref: string;
  document_title: string;
  section: string;
  text: string;
  score: number;
  suspicious: boolean;
  doc_type: string;
}

export default function KnowledgePage() {
  const { project } = useSession();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [q, setQ] = useState("guardrail edge protection harness");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    api.get<Doc[]>("/documents").then(setDocs).catch(setError);
  }, []);

  async function search(e?: FormEvent) {
    e?.preventDefault();
    if (!project) return;
    setError(null);
    api.get<Hit[]>(`/search${qs({ q, project_id: project.id, limit: 8 })}`).then(setHits).catch(setError);
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Knowledge</h1>
      <p className="text-sm text-ink-2">
        Procedures, ITPs and standards the agents retrieve and cite. Retrieved text is treated as untrusted data; chunks with
        instruction-like text are flagged and never cited.
      </p>
      <form onSubmit={search} className="flex gap-2" role="search">
        <input aria-label="Search knowledge" className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} />
        <Button type="submit">Search</Button>
      </form>
      <ErrorBanner error={error} />
      {hits && (
        <Card title={`Results (${hits.length})`}>
          {hits.length === 0 ? (
            <Empty>No matching passages.</Empty>
          ) : (
            <ol className="space-y-3">
              {hits.map((h) => (
                <li key={h.ref} className="text-sm">
                  <div className="font-medium">
                    {h.document_title} — {h.section}
                    {h.suspicious && <span className="ml-2 text-xs text-critical-ink">⚑ instruction-like text, not citable</span>}
                  </div>
                  <p className="whitespace-pre-line text-ink-2">{h.text}</p>
                  <div className="text-xs text-muted">
                    score {h.score} · <code>{h.ref}</code>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      )}
      <Card title={`Documents (${docs.length})`}>
        <ul className="divide-y divide-line text-sm">
          {docs.map((d) => (
            <li key={d.id} className="py-2">
              <div className="font-medium">{d.title}</div>
              <div className="text-xs text-muted">
                {label(d.doc_type)} · {label(d.domain)} · v{d.version} · {d.chunks} chunks
                {d.suspicious_chunks > 0 ? ` · ${d.suspicious_chunks} flagged` : ""} · {d.source}
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
