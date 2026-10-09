"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, buildPath, toApiError, type ApiError, type Query } from "./api";

export type LoadStatus = "idle" | "loading" | "success" | "error";

export interface ApiState<T> {
  status: LoadStatus;
  /** Last data for this path; kept while a reload is in flight so the screen does not flash. */
  data: T | undefined;
  error: ApiError | undefined;
  /** True while reloading data that is already on screen. */
  refreshing: boolean;
  reload: () => void;
}

interface Settled<T> {
  key: string;
  url: string;
  data?: T;
  error?: ApiError;
}

/** GET an API path through the BFF. Pass null to wait (for example until a project is selected). */
export function useApi<T>(path: string | null, query?: Query): ApiState<T> {
  const url = path === null ? null : buildPath(path, query);
  const [nonce, setNonce] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const key = url === null ? null : `${url}#${nonce}`;

  useEffect(() => {
    if (url === null || key === null) return;
    const controller = new AbortController();
    api<T>(url, { signal: controller.signal }).then(
      (data) => setSettled({ key, url, data }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setSettled({ key, url, error: toApiError(error) });
      },
    );
    return () => controller.abort();
  }, [url, key]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const current = settled && settled.key === key ? settled : null;
  const sameUrl = settled && settled.url === url ? settled : null;
  let status: LoadStatus = "idle";
  if (key !== null) status = current ? (current.error ? "error" : "success") : "loading";
  const data = sameUrl?.data;
  return {
    status,
    data,
    error: current?.error,
    refreshing: status === "loading" && data !== undefined,
    reload,
  };
}

export interface Mutation {
  pending: boolean;
  error: ApiError | undefined;
  /** Short confirmation shown after the last successful call. */
  success: string | null;
  run: <R>(call: () => Promise<R>, successMessage?: string) => Promise<R | undefined>;
  reset: () => void;
}

/** Track one user-triggered API call: pending, error (with correlation ID) and success message. */
export function useMutation(): Mutation {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | undefined>(undefined);
  const [success, setSuccess] = useState<string | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(async <R,>(call: () => Promise<R>, successMessage?: string) => {
    setPending(true);
    setError(undefined);
    setSuccess(null);
    try {
      const result = await call();
      if (mounted.current) setSuccess(successMessage ?? "Saved.");
      return result;
    } catch (err) {
      if (mounted.current) setError(toApiError(err));
      return undefined;
    } finally {
      if (mounted.current) setPending(false);
    }
  }, []);

  const reset = useCallback(() => {
    setError(undefined);
    setSuccess(null);
  }, []);

  return { pending, error, success, run, reset };
}
