// Session endpoints for the BFF. POST signs in against the API and stores the token in an httpOnly cookie;
// DELETE signs out. The token is never returned to browser JavaScript.
import { NextResponse, type NextRequest } from "next/server";
import { errorResponse, isAllowedOrigin } from "@/lib/server/http";
import { SESSION_COOKIE, apiBaseUrl, sessionCookieOptions } from "@/lib/server/session";

export const dynamic = "force-dynamic";

interface LoginBody {
  email: string;
  password: string;
}

function readLogin(value: unknown): LoginBody | null {
  if (typeof value !== "object" || value === null) return null;
  const { email, password } = value as Record<string, unknown>;
  if (typeof email !== "string" || typeof password !== "string") return null;
  const trimmed = email.trim();
  if (trimmed.length < 3 || trimmed.length > 320 || password.length < 1 || password.length > 200) return null;
  return { email: trimmed, password };
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!isAllowedOrigin(request.method, request.headers)) {
    return errorResponse(403, "FORBIDDEN", "Request origin is not allowed.");
  }
  let credentials: LoginBody | null = null;
  try {
    credentials = readLogin(await request.json());
  } catch {
    credentials = null;
  }
  if (!credentials) {
    return errorResponse(400, "INVALID_REQUEST", "Enter your email address and password.");
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(credentials),
      cache: "no-store",
    });
  } catch {
    return errorResponse(502, "UPSTREAM_UNAVAILABLE", "The Site Guard API is unreachable. Try again shortly.");
  }

  let payload: unknown = null;
  try {
    payload = await upstream.json();
  } catch {
    payload = null;
  }
  const envelope = payload as { data?: { access_token?: unknown } | null; error?: unknown } | null;
  if (!upstream.ok) {
    if (envelope && typeof envelope === "object" && "error" in envelope) {
      const headers = new Headers({ "Cache-Control": "no-store" });
      const cid = upstream.headers.get("x-correlation-id");
      if (cid) headers.set("X-Correlation-ID", cid);
      return NextResponse.json({ data: null, error: envelope.error }, { status: upstream.status, headers });
    }
    return errorResponse(upstream.status, "HTTP_ERROR", "Sign-in failed.");
  }
  const token = envelope?.data?.access_token;
  if (typeof token !== "string" || !token) {
    return errorResponse(502, "BAD_RESPONSE", "The Site Guard API returned an unexpected response.");
  }

  const response = NextResponse.json(
    { data: { authenticated: true }, error: null },
    { headers: { "Cache-Control": "no-store" } },
  );
  response.cookies.set(SESSION_COOKIE, token, sessionCookieOptions());
  return response;
}

export async function DELETE(request: NextRequest): Promise<NextResponse> {
  if (!isAllowedOrigin(request.method, request.headers)) {
    return errorResponse(403, "FORBIDDEN", "Request origin is not allowed.");
  }
  const response = NextResponse.json(
    { data: { authenticated: false }, error: null },
    { headers: { "Cache-Control": "no-store" } },
  );
  response.cookies.set(SESSION_COOKIE, "", sessionCookieOptions(0));
  return response;
}
