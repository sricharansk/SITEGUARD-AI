// Browser-side API client. Every call goes to the same-origin BFF proxy (/api/backend/...), which adds the
// bearer token from the httpOnly session cookie. The token is never visible to browser JavaScript.
import type { ApiErrorBody, Envelope } from "./types";

export const API_BASE = "/api/backend";

export type QueryValue = string | number | boolean | null | undefined;
export type Query = Record<string, QueryValue>;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly correlationId: string | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.correlationId = body.correlation_id;
  }

  /** 401: no session or the token expired. */
  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  /** 403: signed in, but the server refused the action for this role. */
  get isForbidden(): boolean {
    return this.status === 403;
  }

  /** 404: missing, or outside the caller's tenant (the API does not reveal which). */
  get isNotFound(): boolean {
    return this.status === 404;
  }
}

type UnauthenticatedHandler = (error: ApiError) => void;

function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  const next = `${window.location.pathname}${window.location.search}`;
  // A full page load on purpose: the session ended, so all client state from it is discarded.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/login?next=${encodeURIComponent(next)}`);
}

let onUnauthenticated: UnauthenticatedHandler = redirectToLogin;

/** Replace the 401 handler (tests use this); returns the previous handler. */
export function setUnauthenticatedHandler(handler: UnauthenticatedHandler): UnauthenticatedHandler {
  const previous = onUnauthenticated;
  onUnauthenticated = handler;
  return previous;
}

export function buildPath(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

function isEnvelope(value: unknown): value is Envelope<unknown> {
  return typeof value === "object" && value !== null && "data" in value && "error" in value;
}

/** Unwrap the API envelope `{data, error}`; throw ApiError for any error or unexpected body. */
export async function parseEnvelope<T>(res: Response): Promise<T> {
  const headerCid = res.headers.get("x-correlation-id");
  let body: unknown = null;
  if ((res.headers.get("content-type") ?? "").includes("application/json")) {
    try {
      body = await res.json();
    } catch {
      body = null;
    }
  }
  if (isEnvelope(body)) {
    if (body.error || !res.ok) {
      throw new ApiError(res.ok ? 500 : res.status, {
        code: body.error?.code ?? "HTTP_ERROR",
        message: body.error?.message ?? `Request failed with status ${res.status}`,
        correlation_id: body.error?.correlation_id ?? headerCid,
      });
    }
    return body.data as T;
  }
  throw new ApiError(res.ok ? 502 : res.status, {
    code: res.ok ? "BAD_RESPONSE" : "HTTP_ERROR",
    message: res.ok ? "The server returned an unexpected response." : `Request failed with status ${res.status}.`,
    correlation_id: headerCid,
  });
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH";
  /** A plain object is sent as JSON; FormData is sent as multipart. */
  body?: unknown;
  query?: Query;
  signal?: AbortSignal;
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, {
    code: "NETWORK_ERROR",
    message: "Could not reach the Site Guard web server. Check your connection and try again.",
    correlation_id: null,
  });
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, signal } = options;
  const headers: Record<string, string> = { Accept: "application/json" };
  const init: RequestInit = { method, headers, signal, credentials: "same-origin", cache: "no-store" };
  if (body instanceof FormData) {
    init.body = body; // the browser sets the multipart boundary
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${buildPath(path, query)}`, init);
  } catch (error) {
    if (signal?.aborted) throw error;
    throw toApiError(error);
  }
  try {
    return await parseEnvelope<T>(res);
  } catch (error) {
    if (error instanceof ApiError && error.isUnauthenticated) onUnauthenticated(error);
    throw error;
  }
}

export function evidenceDownloadUrl(evidenceId: string): string {
  return `${API_BASE}/evidence/${encodeURIComponent(evidenceId)}/download`;
}

/** Sign in through the BFF; the session cookie is set by the server. Throws ApiError on failure. */
export async function login(email: string, password: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email, password }),
      credentials: "same-origin",
    });
  } catch (error) {
    throw toApiError(error);
  }
  await parseEnvelope<unknown>(res);
}

export async function logout(): Promise<void> {
  try {
    await fetch("/api/session", { method: "DELETE", credentials: "same-origin" });
  } catch {
    // Signing out is best effort: the caller navigates to /login either way.
  }
}

/** Only same-site relative paths are accepted as post-login destinations (no open redirects). */
export function safeNextPath(next: string | null | undefined, fallback = "/dashboard"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  if (next.startsWith("/login") || next.startsWith("/api/")) return fallback;
  return next;
}
