// @vitest-environment node
// The BFF proxy forwards to the API with the bearer token from the httpOnly cookie, refuses cross-site writes and
// unknown paths, and passes status, body and the safe response headers through.
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GET, PATCH, POST } from "@/app/api/backend/[...path]/route";

const API = "http://api.test:8000";
const WEB = "http://localhost:3000";

function request(
  path: string,
  init: { method?: string; headers?: Record<string, string>; body?: BodyInit; cookie?: string | null } = {},
) {
  const headers: Record<string, string> = { host: "localhost:3000", ...init.headers };
  if (init.cookie !== null) headers.cookie = `sg_session=${init.cookie ?? "token-abc"}`;
  return new NextRequest(`${WEB}/api/backend/${path}`, { method: init.method ?? "GET", headers, body: init.body });
}

const params = (path: string) => ({ params: Promise.resolve({ path: path.split("?")[0]!.split("/").map(decodeURIComponent) }) });

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.stubEnv("SITEGUARD_API_URL", `${API}/`);
  fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ data: { ok: true }, error: null }), {
      status: 200,
      headers: {
        "content-type": "application/json",
        "x-correlation-id": "cid-upstream-1",
        "set-cookie": "upstream=1",
        server: "uvicorn",
      },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

describe("BFF proxy", () => {
  it("forwards a GET with the bearer token and query string", async () => {
    const res = await GET(request("incidents?project_id=p1&q=edge"), params("incidents"));
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API}/incidents?project_id=p1&q=edge`);
    expect(new Headers(init.headers).get("authorization")).toBe("Bearer token-abc");
    expect(init.body).toBeUndefined();
    expect(init.redirect).toBe("manual");
  });

  it("passes status, body and only the safe response headers through", async () => {
    fetchMock.mockResolvedValue(
      new Response("file-bytes", {
        status: 200,
        headers: {
          "content-type": "text/plain",
          "content-disposition": 'attachment; filename="note.txt"',
          "x-correlation-id": "cid-dl-1",
          "set-cookie": "upstream=1",
        },
      }),
    );
    const res = await GET(request("evidence/e1/download"), params("evidence/e1/download"));
    expect(await res.text()).toBe("file-bytes");
    expect(res.headers.get("content-type")).toBe("text/plain");
    expect(res.headers.get("content-disposition")).toBe('attachment; filename="note.txt"');
    expect(res.headers.get("x-correlation-id")).toBe("cid-dl-1");
    expect(res.headers.get("set-cookie")).toBeNull();
    expect(res.headers.get("cache-control")).toBe("no-store");
  });

  it("encodes each path segment", async () => {
    await GET(request("incidents/a%20b%3Fc"), params("incidents/a%20b%3Fc"));
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe(`${API}/incidents/a%20b%3Fc`);
  });

  it("forwards a same-origin JSON POST with its body and content type", async () => {
    const body = JSON.stringify({ decision: "APPROVE", reason: "ok" });
    await POST(
      request("capa/c1/review", {
        method: "POST",
        headers: { origin: WEB, "content-type": "application/json", "x-correlation-id": "cid-client-0001" },
        body,
      }),
      params("capa/c1/review"),
    );
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const sent = new Headers(init.headers);
    expect(init.method).toBe("POST");
    expect(sent.get("content-type")).toBe("application/json");
    expect(sent.get("x-correlation-id")).toBe("cid-client-0001");
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe(body);
  });

  it("keeps the multipart boundary on uploads", async () => {
    const form = new FormData();
    form.append("file", new Blob(["hello"], { type: "text/plain" }), "note.txt");
    const encoded = new Request("http://x", { method: "POST", body: form });
    const contentType = encoded.headers.get("content-type")!;
    await POST(
      request("incidents/i1/evidence", {
        method: "POST",
        headers: { origin: WEB, "content-type": contentType },
        body: await encoded.arrayBuffer(),
      }),
      params("incidents/i1/evidence"),
    );
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get("content-type")).toBe(contentType);
    expect(contentType).toMatch(/^multipart\/form-data; boundary=/);
  });

  it("refuses a cross-site write before calling the API", async () => {
    const res = await PATCH(
      request("incidents/i1", { method: "PATCH", headers: { origin: "https://evil.example" }, body: "{}" }),
      params("incidents/i1"),
    );
    expect(res.status).toBe(403);
    const body = (await res.json()) as { error: { code: string; correlation_id: string } };
    expect(body.error.code).toBe("FORBIDDEN");
    expect(body.error.correlation_id).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses a write without an Origin header", async () => {
    const res = await POST(request("incidents", { method: "POST", body: "{}" }), params("incidents"));
    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(["auth/login", "openapi.json", "docs", "incidents/../auth/login"])("does not expose %s", async (path) => {
    const res = await GET(request(path), { params: Promise.resolve({ path: path.split("/") }) });
    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers 401 without a session cookie", async () => {
    const res = await GET(request("me", { cookie: null }), params("me"));
    expect(res.status).toBe(401);
    expect(((await res.json()) as { error: { code: string } }).error.code).toBe("UNAUTHENTICATED");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("clears the session cookie when the API rejects the token", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ data: null, error: { code: "UNAUTHENTICATED", message: "Token expired.", correlation_id: "c" } }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );
    const res = await GET(request("me"), params("me"));
    expect(res.status).toBe(401);
    expect(res.headers.get("set-cookie")).toMatch(/sg_session=;.*Max-Age=0/i);
  });

  it("passes API errors through unchanged", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ data: null, error: { code: "NOT_FOUND", message: "Incident not found.", correlation_id: "cid-nf" } }), {
        status: 404,
        headers: { "content-type": "application/json", "x-correlation-id": "cid-nf" },
      }),
    );
    const res = await GET(request("incidents/other-tenant"), params("incidents/other-tenant"));
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ data: null, error: { code: "NOT_FOUND", message: "Incident not found.", correlation_id: "cid-nf" } });
    expect(res.headers.get("x-correlation-id")).toBe("cid-nf");
  });

  it("passes a binary report through byte for byte with its file name and audited SHA-256", async () => {
    // Every byte value, after a PDF header: anything that decoded or re-encoded the body as text would change it.
    const bytes = new Uint8Array([...new TextEncoder().encode("%PDF-1.7\n"), ...Array.from({ length: 256 }, (_, i) => i)]);
    const sha = "f".repeat(64);
    fetchMock.mockResolvedValue(
      new Response(bytes, {
        status: 200,
        headers: {
          "content-type": "application/pdf",
          "content-disposition": 'attachment; filename="SG-2026-0001-report.pdf"',
          "x-report-sha256": sha,
          "x-correlation-id": "cid-report-1",
          "set-cookie": "upstream=1",
          server: "uvicorn",
        },
      }),
    );
    const path = "incidents/i1/report";
    const res = await GET(request(`${path}?format=pdf&include_ai=false`), params(path));
    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toBe(`${API}/incidents/i1/report?format=pdf&include_ai=false`);
    expect(res.status).toBe(200);
    expect(new Uint8Array(await res.arrayBuffer())).toEqual(bytes);
    expect(res.headers.get("content-type")).toBe("application/pdf");
    expect(res.headers.get("content-disposition")).toBe('attachment; filename="SG-2026-0001-report.pdf"');
    expect(res.headers.get("x-report-sha256")).toBe(sha);
    expect(res.headers.get("x-correlation-id")).toBe("cid-report-1");
    expect(res.headers.get("set-cookie")).toBeNull();
    expect(res.headers.get("server")).toBeNull();
  });

  it.each([
    ["POST", "knowledge/answer"],
    ["GET", "notifications"],
    ["POST", "notifications/read-all"],
    ["POST", "notifications/n1/read"],
    ["GET", "notifications/deliveries"],
    ["POST", "notifications/deliveries/d1/retry"],
  ])("forwards %s %s (the API decides who may use it)", async (method, path) => {
    const handler = method === "GET" ? GET : POST;
    const init = method === "GET" ? {} : { method, headers: { origin: WEB, "content-type": "application/json" }, body: "{}" };
    const res = await handler(request(path, init), params(path));
    expect(res.status).toBe(200);
    const [url, sent] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${API}/${path}`);
    expect(sent.method).toBe(method);
  });

  it("still refuses a cross-site POST to the new roots", async () => {
    const res = await POST(
      request("notifications/read-all", { method: "POST", headers: { origin: "https://evil.example" }, body: "{}" }),
      params("notifications/read-all"),
    );
    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("maps an unreachable API to 502 and a timeout to 504", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("fetch failed"));
    expect((await GET(request("me"), params("me"))).status).toBe(502);
    fetchMock.mockRejectedValueOnce(new DOMException("The operation timed out.", "TimeoutError"));
    const res = await GET(request("me"), params("me"));
    expect(res.status).toBe(504);
    expect(((await res.json()) as { error: { code: string } }).error.code).toBe("UPSTREAM_TIMEOUT");
  });
});
