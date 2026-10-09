"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Capa, Incident, Workspace } from "@/lib/types";
import { useApp } from "@/components/Shell";
import CapaCard from "@/components/CapaCard";
import { Empty, ErrorBox, Loading, SeverityBadge } from "@/components/ui";

interface Group { incident: Incident; capa: Capa[]; permissions: string[] }

// There is no queue endpoint yet, so this gathers pending actions from the project's open incidents.
export default function ReviewQueue() {
  const { project } = useApp();
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Incident[]>(`/projects/${project.id}/incidents`)
      .then((list) => Promise.all(list.filter((i) => i.status !== "CLOSED").map((i) => api<Workspace>(`/incidents/${i.id}`))))
      .then((all) =>
        setGroups(
          all
            .map((w) => ({ incident: w.incident, capa: w.capa.filter((c) => c.approval_status === "PENDING_REVIEW"), permissions: w.permissions }))
            .filter((g) => g.capa.length > 0),
        ),
      )
      .catch((e: Error) => setError(e.message));
  }, [project.id]);
  useEffect(load, [load]);

  if (error) return <ErrorBox message={error} />;
  if (!groups) return <Loading what="review queue" />;
  const total = groups.reduce((n, g) => n + g.capa.length, 0);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Review queue</h1>
        <p className="text-sm text-ink-soft">{total} proposed action{total === 1 ? "" : "s"} awaiting a human decision. AI proposals are drafts until approved.</p>
      </div>
      {groups.length === 0 && <Empty>Nothing to review.</Empty>}
      {groups.map((g) => (
        <section key={g.incident.id} className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-ink-soft">{g.incident.reference}</span>
            <Link href={`/incidents/${g.incident.id}`} className="font-semibold text-brand hover:underline">{g.incident.title}</Link>
            <SeverityBadge value={g.incident.severity} />
          </div>
          <div className="space-y-3">{g.capa.map((c) => <CapaCard key={c.id} capa={c} permissions={g.permissions} onChanged={load} />)}</div>
        </section>
      ))}
    </div>
  );
}
