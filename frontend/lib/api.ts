// Thin client for the Site Guard AI API. The server enforces every permission; the UI only hides what a
// user cannot do. The pilot keeps the bearer token in sessionStorage (cleared when the tab closes);
// production should use OIDC (Entra ID) with httpOnly cookies (docs/SECURITY.md).

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const TOKEN_KEY = "siteguard.token";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public correlationId?: string,
  ) {
    super(message);
  }
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the user will be asked to log in again */
  }
}

async function request<T>(method: string, path: string, body?: unknown, blob = false): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE}${path}`, { method, headers, body: payload });
  if (blob && res.ok) return (await res.blob()) as T;
  let json: any = null;
  try {
    json = await res.json();
  } catch {
    /* non-JSON error */
  }
  if (!res.ok || json?.error) {
    const err = json?.error ?? {};
    if (res.status === 401) setToken(null);
    throw new ApiError(res.status, err.code ?? "HTTP_ERROR", err.message ?? res.statusText, err.correlation_id);
  }
  return json.data as T;
}

export const api = {
  get: <T,>(path: string) => request<T>("GET", path),
  post: <T,>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T,>(path: string, body: unknown) => request<T>("PATCH", path, body),
  upload: <T,>(path: string, form: FormData) => request<T>("POST", path, form),
  blob: (path: string) => request<Blob>("GET", path, undefined, true),
};

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const href = (path: string) => path; // basePath is applied by next/link

export function fmtDate(iso: string | null | undefined, withTime = false): string {
  if (!iso) return "";
  const d = new Date(iso);
  return withTime
    ? d.toLocaleString(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

/** Human label for an enum value (PENDING_REVIEW -> Pending review). Free text is returned unchanged. */
const ACRONYMS: [RegExp, string][] = [
  [/\bhse\b/g, "HSE"],
  [/\bqa qc\b/g, "QA/QC"],
  [/\bppe\b/g, "PPE"],
  [/\bitp\b/g, "ITP"],
  [/\bai\b/g, "AI"],
  [/\bcapa\b/g, "CAPA"],
];
export const label = (s: string) => {
  if (!/^[A-Z0-9_]+$/.test(s)) return s;
  let out = s.replaceAll("_", " ").toLowerCase();
  for (const [re, rep] of ACRONYMS) out = out.replace(re, rep);
  return out.replace(/^\w/, (c) => c.toUpperCase());
};
