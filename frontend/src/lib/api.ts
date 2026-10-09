// Thin typed client for the Site Guard AI API. The server enforces all authorization; the UI only reflects it.
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "siteguard.token";

export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
  ) {
    super(message);
  }
}

export const session = {
  get(): string | null {
    try {
      return sessionStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string) {
    try {
      sessionStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable: user must sign in again on reload */
    }
  },
  clear() {
    try {
      sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  },
};

export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const token = session.get();
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method: init.method ?? "GET",
      headers: {
        ...(init.body !== undefined ? { "content-type": "application/json" } : {}),
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
  } catch {
    throw new ApiError("Cannot reach the Site Guard AI API. Check that it is running.", "NETWORK", 0);
  }
  const json = await res.json().catch(() => null);
  if (!res.ok || json?.error) {
    if (res.status === 401) session.clear();
    throw new ApiError(json?.error?.message ?? `Request failed (${res.status})`, json?.error?.code ?? "ERROR", res.status);
  }
  return json.data as T;
}

export async function login(email: string, password: string) {
  const out = await api<{ access_token: string }>("/auth/login", { method: "POST", body: { email, password } });
  session.set(out.access_token);
}
