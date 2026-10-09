"use client";

// Signed-in user, visible projects and the selected project (remembered per browser in localStorage).
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Me, Project } from "@/lib/types";

export const PROJECT_STORAGE_KEY = "siteguard.projectId";

interface AppContextValue {
  me: Me | undefined;
  meError: ApiError | undefined;
  projects: Project[] | undefined;
  projectsError: ApiError | undefined;
  projectsLoading: boolean;
  project: Project | undefined;
  setProjectId: (id: string) => void;
  reloadProjects: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

function readStoredProjectId(): string | null {
  try {
    return window.localStorage.getItem(PROJECT_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const me = useApi<Me>("/me");
  const projects = useApi<Project[]>("/projects");
  // The remembered project only decides which data to fetch, and nothing project-specific is rendered on the
  // server (data loads after mount), so reading localStorage in the initializer cannot cause a hydration mismatch.
  const [chosenId, setChosenId] = useState<string | null>(() =>
    typeof window === "undefined" ? null : readStoredProjectId(),
  );

  const setProjectId = useCallback((id: string) => {
    setChosenId(id);
    try {
      window.localStorage.setItem(PROJECT_STORAGE_KEY, id);
    } catch {
      // Storage can be unavailable (private mode); the choice still applies for this page view.
    }
  }, []);

  const list = projects.data;
  const project = useMemo(() => {
    if (!list || list.length === 0) return undefined;
    return list.find((p) => p.id === chosenId) ?? list[0];
  }, [list, chosenId]);

  const value: AppContextValue = {
    me: me.data,
    meError: me.error,
    projects: list,
    projectsError: projects.error,
    projectsLoading: projects.status === "loading" && !list,
    project,
    setProjectId,
    reloadProjects: projects.reload,
  };
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext(): AppContextValue {
  const value = useContext(AppContext);
  if (!value) throw new Error("useAppContext must be used inside <AppProvider>");
  return value;
}
