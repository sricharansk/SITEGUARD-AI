"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, session } from "@/lib/api";
import type { Me, Project } from "@/lib/types";
import { Loading } from "./ui";

interface Ctx {
  me: Me;
  projects: Project[];
  project: Project;
  setProjectId: (id: string) => void;
}
const AppContext = createContext<Ctx | null>(null);
export const useApp = () => {
  const c = useContext(AppContext);
  if (!c) throw new Error("useApp outside Shell");
  return c;
};

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/incidents", label: "Incidents" },
  { href: "/review", label: "Review queue" },
];

export default function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session.get()) {
      router.replace("/login");
      return;
    }
    Promise.all([api<Me>("/me"), api<Project[]>("/projects")])
      .then(([m, p]) => {
        setMe(m);
        setProjects(p);
        setProjectId(p[0]?.id ?? null);
      })
      .catch((e: Error) => {
        if (!session.get()) router.replace("/login");
        else setError(e.message);
      });
  }, [router]);

  if (error) return <p role="alert" className="p-6 text-red-800">{error}</p>;
  if (!me) return <Loading what="workspace" />;
  const project = projects.find((p) => p.id === projectId);
  if (!project)
    return <p className="p-6 text-ink-soft">Your account has no projects yet. Ask an administrator to add you to one.</p>;

  const role = me.memberships[0]?.role.replace(/_/g, " ");
  return (
    <AppContext.Provider value={{ me, projects, project, setProjectId }}>
      <div className="min-h-screen">
        <header className="border-b border-surface-line bg-brand-dark text-white">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
            <Link href="/" className="text-lg font-bold tracking-tight">Site Guard AI</Link>
            <nav aria-label="Primary" className="flex gap-1">
              {NAV.map((n) => {
                const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
                return (
                  <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                    className={`rounded px-3 py-1.5 text-sm ${active ? "bg-white text-brand-dark font-semibold" : "text-white/90 hover:bg-white/15"}`}>
                    {n.label}
                  </Link>
                );
              })}
            </nav>
            <div className="ml-auto flex flex-wrap items-center gap-3 text-sm">
              <label className="flex items-center gap-2">
                <span className="sr-only">Project</span>
                <select value={project.id} onChange={(e) => setProjectId(e.target.value)}
                  className="rounded border-0 bg-white/15 px-2 py-1 text-white [&>option]:text-ink">
                  {projects.map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name}</option>)}
                </select>
              </label>
              <span className="text-white/80">{me.full_name}{role ? ` — ${role}` : ""}</span>
              <button onClick={() => { session.clear(); router.replace("/login"); }}
                className="rounded border border-white/40 px-2.5 py-1 hover:bg-white/15">Sign out</button>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-ink-faint">
          Decision support only. Not a legal compliance certification. AI output is a draft until a qualified person approves it.
        </footer>
      </div>
    </AppContext.Provider>
  );
}
