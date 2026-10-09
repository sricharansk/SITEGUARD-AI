// Backend-for-frontend proxy: forwards the browser's API calls to the FastAPI service with the bearer token
// taken from the httpOnly session cookie. The API still authorizes every call; this layer only carries the
// token, blocks cross-site writes and limits which API paths the browser can reach.
import { NextResponse, type NextRequest } from "next/server";
import { CORRELATION_ID_PATTERN, errorResponse, isAllowedOrigin } from "@/lib/server/http";
import { SESSION_COOKIE, apiBaseUrl, apiTimeoutMs } from "@/lib/server/session";

export const dynamic = "force-dynamic";

/** First path segments the web app uses. Login goes through /api/session, never through here. */
const ALLOWED_ROOTS = new Set([
  "me",
  "projects",
  "incidents",
  "evidence",
  "capa",
  "risk",
  "agents",
  "documents",
  "search",
  "dashboard",
  "audit",
  "health",
]);

const PASSTHROUGH_RESPONSE_HEADERS = ["content-type", "content-disposition", "x-correlation-id"];

type RouteParams = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  if (!isAllowedOrigin(request.method, request.headers)) {
    return errorResponse(403, "FORBIDDEN", "Request origin is not allowed.");
  }
  const { path } = await params;
  const root = path[0];
  if (!root || !ALLOWED_ROOTS.has(root) || path.some((s) => s === "" || s === "." || s === "..")) {
    return errorResponse(404, "NOT_FOUND", "Not found.");
  }
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) {
    return errorResponse(401, "UNAUTHENTICATED", "Authentication required.");
  }

  const target = `${apiBaseUrl()}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers({
    Authorization: `Bearer ${token}`,
    Accept: request.headers.get("accept") ?? "application/json",
  });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType); // keeps the multipart boundary intact
  const correlationId = request.headers.get("x-correlation-id");
  if (correlationId && CORRELATION_ID_PATTERN.test(correlationId)) headers.set("X-Correlation-ID", correlationId);

  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer();

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(apiTimeoutMs()),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      return errorResponse(504, "UPSTREAM_TIMEOUT", "The Site Guard API did not answer in time. Try again.");
    }
    return errorResponse(502, "UPSTREAM_UNAVAILABLE", "The Site Guard API is unreachable. Try again shortly.");
  }

  const responseHeaders = new Headers({ "Cache-Control": "no-store" });
  for (const name of PASSTHROUGH_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  const response = new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders });
  if (upstream.status === 401) {
    // The token expired or was revoked: drop the cookie so the next page load goes to /login.
    response.cookies.set(SESSION_COOKIE, "", { path: "/", maxAge: 0 });
  }
  return response;
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
