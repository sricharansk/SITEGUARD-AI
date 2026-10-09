"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { logout } from "@/lib/api";
import { roleLabel } from "@/lib/format";
import { meCan } from "@/lib/permissions";
import { useAppContext } from "./app-context";
import { HardHatIcon } from "./icons";
import { ErrorState, LoadingState, EmptyState } from "./states";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/incidents", label: "Incidents" },
  { href: "/review", label: "CAPA review" },
  { href: "/knowledge", label: "Knowledge" },
];

function ProjectSwitcher() {
  const { projects, project, setProjectId, projectsLoading } = useAppContext();
  if (projectsLoading) return <span className="text-xs text-slate-300">Loading projects…</span>;
  if (!projects || projects.length === 0) return null;
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="project-switcher" className="text-xs font-semibold text-slate-300">
        Project
      </label>
      <select
        id="project-switcher"
        className="max-w-[16rem] rounded border border-slate-600 bg-slate-800 px-2 py-1 text-sm text-white"
        value={project?.id ?? ""}
        onChange={(e) => setProjectId(e.target.value)}
      >
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.code} · {p.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function UserMenu() {
  const { me, project } = useAppContext();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  const role = me?.memberships.find(
    (m) => m.organization_id === project?.organization_id && (m.project_id === null || m.project_id === project?.id),
  )?.role;
  async function signOut() {
    setSigningOut(true);
    await logout();
    // /login is outside the signed-in layout, so leaving unmounts it and drops the previous user's data.
    router.replace("/login");
  }
  return (
    <div className="flex items-center gap-3">
      {me ? (
        <span className="hidden text-right text-xs leading-tight text-slate-200 sm:block">
          <span className="block font-semibold text-white">{me.full_name}</span>
          {role ? <span>{roleLabel(role)}</span> : null}
        </span>
      ) : null}
      <button
        type="button"
        onClick={signOut}
        disabled={signingOut}
        className="rounded border border-slate-500 px-2 py-1 text-xs font-semibold text-white hover:bg-slate-800"
      >
        {signingOut ? "Signing out…" : "Sign out"}
      </button>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { me, meError, projects, projectsError, projectsLoading, reloadProjects } = useAppContext();
  const nav = meCan(me, "VIEW_AUDIT") ? [...NAV, { href: "/audit", label: "Audit log" }] : NAV;

  let body: ReactNode = children;
  if (projectsError) {
    body = <ErrorState error={projectsError} onRetry={reloadProjects} what="projects" />;
  } else if (meError && !meError.isUnauthenticated) {
    body = <ErrorState error={meError} what="your profile" />;
  } else if (projectsLoading) {
    body = <LoadingState label="Loading your projects…" />;
  } else if (projects && projects.length === 0) {
    body = (
      <EmptyState title="No projects yet">
        You are not a member of any project. Ask an administrator to add you to one.
      </EmptyState>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="border-b-4 border-brand-400 bg-slate-900 text-white">
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2">
          <Link href="/dashboard" className="flex items-center gap-2 font-bold tracking-tight text-white">
            <span className="flex h-7 w-7 items-center justify-center rounded bg-brand-400 text-slate-900">
              <HardHatIcon size={18} />
            </span>
            <span>
              Site Guard AI
              <span className="block text-[10px] font-medium tracking-wider text-slate-300 uppercase">
                Safety &amp; quality decision support
              </span>
            </span>
          </Link>
          <div className="flex flex-wrap items-center gap-4">
            <ProjectSwitcher />
            <UserMenu />
          </div>
        </div>
        <nav aria-label="Main" className="overflow-x-auto bg-slate-800 px-2">
          <ul className="flex gap-1">
            {nav.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`block border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap ${
                      active
                        ? "border-brand-400 text-white"
                        : "border-transparent text-slate-300 hover:border-slate-500 hover:text-white"
                    }`}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </header>
      <main id="main" className="flex-1 px-4 py-4">
        {body}
      </main>
      <footer className="border-t border-slate-200 bg-white px-4 py-2 text-xs text-slate-600">
        Site Guard AI is decision support. AI output must be reviewed by a competent person; it does not replace
        emergency procedures or certify legal compliance.
      </footer>
    </div>
  );
}
