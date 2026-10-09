// Shared helpers for the BFF route handlers: CSRF origin check and envelope-shaped errors.
import { NextResponse } from "next/server";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function configuredOrigins(): string[] {
  return (process.env.SITEGUARD_ALLOWED_ORIGINS ?? "")
    .split(",")
    .map((o) => o.trim().replace(/\/+$/, ""))
    .filter(Boolean);
}

/**
 * CSRF defence for state-changing requests: the browser's Origin header must name this host (or an origin listed
 * in SITEGUARD_ALLOWED_ORIGINS, for deployments behind a proxy that rewrites Host). Requests without an Origin
 * header are refused; browsers always send it on cross-site and same-site POST/PATCH/DELETE.
 */
export function isAllowedOrigin(
  method: string,
  headers: Headers,
  allowedOrigins: readonly string[] = configuredOrigins(),
): boolean {
  if (SAFE_METHODS.has(method.toUpperCase())) return true;
  const origin = headers.get("origin");
  if (!origin || origin === "null") return false;
  let parsed: URL;
  try {
    parsed = new URL(origin);
  } catch {
    return false;
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false;
  const host = headers.get("host");
  if (host && parsed.host.toLowerCase() === host.toLowerCase()) return true;
  return allowedOrigins.includes(parsed.origin);
}

export function errorResponse(status: number, code: string, message: string): NextResponse {
  const correlationId = crypto.randomUUID();
  return NextResponse.json(
    { data: null, error: { code, message, correlation_id: correlationId } },
    { status, headers: { "X-Correlation-ID": correlationId, "Cache-Control": "no-store" } },
  );
}

export const CORRELATION_ID_PATTERN = /^[A-Za-z0-9-]{8,64}$/;
