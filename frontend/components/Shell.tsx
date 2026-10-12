"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, fmtDate, getToken, setToken } from "@/lib/api";
import type { Me, Notification, Person, Project } from "@/lib/types";

interface Session {
  me: Me;
  projects: Project[];
  project: Project | null;
  people: Record<string, Person>;
  setProjectId: (id: string) => void;
  can: (perm: string) => boolean;
  roles: string[];
}

const Ctx = createContext<Session | null>(null);
export const useSession = () => {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession outside Shell");
  return s;
};

const PROJECT_KEY = "siteguard.project";

export default function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const isLogin = path?.startsWith("/login");
  const [session, setSession] = useState<Session | null>(null);
  const [projectId, setProjectIdState] = useState<string | null>(null);
  const [people, setPeople] = useState<Record<string, Person>>({});

  useEffect(() => {
    if (isLogin) return;
    if (!getToken()) {
      router.replace("/login/");
      return;
    }
    Promise.all([api.get<Me>("/me"), api.get<Project[]>("/projects")])
      .then(([me, projects]) => {
        let stored: string | null = null;
        try {
          stored = localStorage.getItem(PROJECT_KEY);
        } catch {}
        const pid = projects.find((p) => p.id === stored)?.id ?? projects[0]?.id ?? null;
        setProjectIdState(pid);
        setSession({ me, projects, project: null, people: {}, setProjectId: () => {}, can: () => false, roles: [] });
      })
      .catch(() => {
        setToken(null);
        router.replace("/login/");
      });
  }, [isLogin, router]);

  useEffect(() => {
    if (!projectId) return;
    api
      .get<Person[]>(`/projects/${projectId}/people`)
      .then((rows) => setPeople(Object.fromEntries(rows.map((p) => [p.id, p]))))
      .catch(() => setPeople({}));
  }, [projectId]);

  const setProjectId = useCallback((id: string) => {
    setProjectIdState(id);
    try {
      localStorage.setItem(PROJECT_KEY, id);
    } catch {}
  }, []);

  if (isLogin) return <>{children}</>;
  if (!session) return <p className="p-6 text-sm text-muted">Loading Site Guard AI…</p>;

  const project = session.projects.find((p) => p.id === projectId) ?? null;
  const memberships = session.me.memberships.filter(
    (m) => project && m.organization_id === project.organization_id && (!m.project_id || m.project_id === project.id),
  );
  const perms = new Set(memberships.flatMap((m) => m.permissions));
  const value: Session = {
    ...session,
    project,
    people,
    setProjectId,
    can: (perm) => perms.has(perm),
    roles: memberships.map((m) => m.role),
  };

  const nav = [
    { href: "/", label: "Dashboard" },
    { href: "/incidents/", label: "Incidents" },
    { href: "/review/", label: "Actions" },
    { href: "/knowledge/", label: "Knowledge" },
    ...(value.can("VIEW_AUDIT") ? [{ href: "/audit/", label: "Audit" }] : []),
    ...(memberships.some((m) => !m.project_id && m.permissions.includes("VIEW_AUDIT")) ? [{ href: "/outbox/", label: "Email outbox" }] : []),
  ];

  return (
    <Ctx.Provider value={value}>
      <a href="#main" className="sr-only focus:not-sr-only">
        Skip to content
      </a>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2">
          <Link href="/" className="flex items-center gap-2 font-semibold text-ink">
            <span aria-hidden className="inline-flex h-7 w-7 items-center justify-center rounded bg-accent text-sm text-accent-ink">SG</span>
            Site Guard AI
          </Link>
          <nav aria-label="Main" className="flex flex-wrap gap-1">
            {nav.map((n) => {
              const active = n.href === "/" ? path === "/" : path?.startsWith(n.href.replace(/\/$/, ""));
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded px-2.5 py-1 text-sm ${active ? "bg-surface-2 font-semibold text-ink" : "text-ink-2 hover:bg-surface-2"}`}
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            {session.projects.length > 0 && (
              <select
                aria-label="Project"
                className="rounded-md border border-line bg-surface px-2 py-1 text-sm"
                value={projectId ?? ""}
                onChange={(e) => setProjectId(e.target.value)}
              >
                {session.projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} · {p.name}
                  </option>
                ))}
              </select>
            )}
            <Notifications />
            <span className="hidden text-sm text-ink-2 md:inline">{session.me.full_name}</span>
            <button
              className="text-sm text-accent hover:underline"
              onClick={() => {
                setToken(null);
                router.replace("/login/");
              }}
            >
              Log out
            </button>
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-7xl px-4 py-5">
        {children}
      </main>
      <footer className="mx-auto max-w-7xl px-4 pb-6 text-xs text-muted">
        Decision support only. AI output is reviewed by qualified people; Site Guard AI does not certify legal compliance.
      </footer>
    </Ctx.Provider>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const load = useCallback(() => {
    api.get<Notification[]>("/notifications?unread_only=true").then(setItems).catch(() => setItems([]));
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 60_000);
    return () => clearInterval(t);
  }, [load]);
  return (
    <div className="relative">
      <button
        className="rounded px-2 py-1 text-sm text-ink-2 hover:bg-surface-2"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen(!open)}
      >
        Notifications{items.length > 0 && <span className="ml-1 rounded-full bg-accent px-1.5 text-xs text-accent-ink">{items.length}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-1 w-[min(26rem,90vw)] rounded-lg border border-line bg-surface p-2 shadow-lg">
          {items.length === 0 ? (
            <p className="p-2 text-sm text-muted">No unread notifications.</p>
          ) : (
            <ul className="max-h-96 divide-y divide-line overflow-auto">
              {items.map((n) => (
                <li key={n.id} className="p-2 text-sm">
                  <div className="text-xs text-muted">
                    {n.kind.replaceAll("_", " ").toLowerCase()} · {fmtDate(n.created_at, true)}
                  </div>
                  <div className="text-ink">{n.message}</div>
                  <div className="mt-1 flex gap-3 text-xs">
                    {n.incident_id && (
                      <Link className="text-accent hover:underline" href={`/incident/?id=${n.incident_id}`} onClick={() => setOpen(false)}>
                        Open incident
                      </Link>
                    )}
                    <button
                      className="text-accent hover:underline"
                      onClick={() => api.post(`/notifications/${n.id}/read`).then(load)}
                    >
                      Mark read
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function personName(people: Record<string, Person>, id: string | null | undefined): string {
  if (!id) return "System";
  return people[id]?.full_name ?? "Unknown user";
}
