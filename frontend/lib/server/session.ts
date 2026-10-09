// Server-only session settings for the BFF. The API token lives in an httpOnly cookie that browser
// JavaScript cannot read; route handlers attach it as a bearer token when they call the API.

export const SESSION_COOKIE = "sg_session";

/** Matches the API's default token lifetime (SITEGUARD_JWT_TTL_MINUTES=480). An expired token is cleared on 401. */
export const SESSION_MAX_AGE_SECONDS = 8 * 60 * 60;

export interface SessionCookieOptions {
  httpOnly: true;
  sameSite: "lax";
  secure: boolean;
  path: "/";
  maxAge: number;
}

export function sessionCookieOptions(maxAge: number = SESSION_MAX_AGE_SECONDS): SessionCookieOptions {
  return {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  };
}

/** Base URL of the FastAPI service, server side only (never exposed to the browser). */
export function apiBaseUrl(): string {
  return (process.env.SITEGUARD_API_URL || "http://localhost:8000").replace(/\/+$/, "");
}

/** Upper bound for one proxied call; the full AI investigation can take minutes with a live model. */
export function apiTimeoutMs(): number {
  const value = Number(process.env.SITEGUARD_API_TIMEOUT_MS);
  return Number.isFinite(value) && value > 0 ? value : 300_000;
}
