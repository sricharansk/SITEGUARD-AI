// API client: envelope parsing, error mapping (code, message, correlation ID), request encoding and the 401 path.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  api,
  buildPath,
  evidenceDownloadUrl,
  login,
  parseEnvelope,
  safeNextPath,
  setUnauthenticatedHandler,
} from "@/lib/api";
import { envelopeResponse, errorEnvelopeResponse } from "../fixtures";

describe("parseEnvelope", () => {
  it("returns data from a success envelope", async () => {
    await expect(parseEnvelope(envelopeResponse({ id: "x" }))).resolves.toEqual({ id: "x" });
  });

  it("throws ApiError with the API's code, message and correlation ID", async () => {
    const error = await parseEnvelope(errorEnvelopeResponse(409, "INVALID_TRANSITION", "Not allowed now.", "cid-abcdef12")).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(409);
    expect(apiError.code).toBe("INVALID_TRANSITION");
    expect(apiError.message).toBe("Not allowed now.");
    expect(apiError.correlationId).toBe("cid-abcdef12");
  });

  it("flags 401, 403 and 404 for the screen states", async () => {
    const forbidden = (await parseEnvelope(errorEnvelopeResponse(403, "FORBIDDEN", "No.")).catch((e) => e)) as ApiError;
    expect(forbidden.isForbidden).toBe(true);
    expect(forbidden.isUnauthenticated).toBe(false);
    const missing = (await parseEnvelope(errorEnvelopeResponse(404, "NOT_FOUND", "Gone.")).catch((e) => e)) as ApiError;
    expect(missing.isNotFound).toBe(true);
    const anon = (await parseEnvelope(errorEnvelopeResponse(401, "UNAUTHENTICATED", "Sign in.")).catch((e) => e)) as ApiError;
    expect(anon.isUnauthenticated).toBe(true);
  });

  it("maps a non-envelope error body to HTTP_ERROR and keeps the header correlation ID", async () => {
    const res = new Response("<html>bad gateway</html>", {
      status: 502,
      headers: { "content-type": "text/html", "x-correlation-id": "cid-header-1" },
    });
    const error = (await parseEnvelope(res).catch((e) => e)) as ApiError;
    expect(error.status).toBe(502);
    expect(error.code).toBe("HTTP_ERROR");
    expect(error.correlationId).toBe("cid-header-1");
  });

  it("treats a 200 without an envelope as a bad response", async () => {
    const res = new Response(JSON.stringify({ hello: "world" }), { headers: { "content-type": "application/json" } });
    const error = (await parseEnvelope(res).catch((e) => e)) as ApiError;
    expect(error.status).toBe(502);
    expect(error.code).toBe("BAD_RESPONSE");
  });

  it("treats an error envelope on a 200 as a failure", async () => {
    const res = new Response(JSON.stringify({ data: null, error: { code: "X", message: "Odd", correlation_id: null } }), {
      headers: { "content-type": "application/json" },
    });
    const error = (await parseEnvelope(res).catch((e) => e)) as ApiError;
    expect(error.code).toBe("X");
    expect(error.status).toBe(500);
  });
});

describe("api()", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let restoreHandler: ReturnType<typeof setUnauthenticatedHandler>;
  const onUnauthenticated = vi.fn();

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    onUnauthenticated.mockReset();
    restoreHandler = setUnauthenticatedHandler(onUnauthenticated);
  });

  afterEach(() => {
    setUnauthenticatedHandler(restoreHandler);
  });

  it("calls the same-origin BFF with query parameters, skipping empty values", async () => {
    fetchMock.mockResolvedValue(envelopeResponse([]));
    await api("/incidents", { query: { project_id: "p1", status: "", severity: null, q: "edge" } });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/backend/incidents?project_id=p1&q=edge");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
    expect(init.body).toBeUndefined();
  });

  it("sends plain objects as JSON", async () => {
    fetchMock.mockResolvedValue(envelopeResponse({ id: "new" }));
    await expect(api("/incidents", { method: "POST", body: { title: "A" } })).resolves.toEqual({ id: "new" });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ title: "A" }));
  });

  it("sends FormData as multipart and lets the browser set the boundary", async () => {
    fetchMock.mockResolvedValue(envelopeResponse({ id: "ev" }));
    const form = new FormData();
    form.append("description", "note");
    await api("/incidents/1/evidence", { method: "POST", body: form });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.body).toBe(form);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });

  it("runs the unauthenticated handler on 401 and still throws", async () => {
    fetchMock.mockResolvedValue(errorEnvelopeResponse(401, "UNAUTHENTICATED", "Sign in again."));
    await expect(api("/me")).rejects.toMatchObject({ status: 401, code: "UNAUTHENTICATED" });
    expect(onUnauthenticated).toHaveBeenCalledTimes(1);
  });

  it("does not redirect on 403: the screen shows the unauthorized state", async () => {
    fetchMock.mockResolvedValue(errorEnvelopeResponse(403, "FORBIDDEN", "Role cannot do this."));
    await expect(api("/audit")).rejects.toMatchObject({ status: 403 });
    expect(onUnauthenticated).not.toHaveBeenCalled();
  });

  it("maps a network failure to NETWORK_ERROR", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api("/me")).rejects.toMatchObject({ status: 0, code: "NETWORK_ERROR" });
  });
});

describe("login()", () => {
  it("posts credentials to the session endpoint, never to the API directly", async () => {
    const fetchMock = vi.fn().mockResolvedValue(envelopeResponse({ authenticated: true }));
    vi.stubGlobal("fetch", fetchMock);
    await login("hse@example.test", "secret");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/session");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ email: "hse@example.test", password: "secret" });
  });

  it("surfaces the API's sign-in error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(errorEnvelopeResponse(401, "INVALID_CREDENTIALS", "Wrong email or password.")));
    await expect(login("a@b.c", "x")).rejects.toMatchObject({ code: "INVALID_CREDENTIALS", message: "Wrong email or password." });
  });
});

describe("helpers", () => {
  it("buildPath leaves a path without query untouched", () => {
    expect(buildPath("/me")).toBe("/me");
    expect(buildPath("/audit", { limit: 50, entity_id: undefined })).toBe("/audit?limit=50");
  });

  it("evidenceDownloadUrl encodes the id", () => {
    expect(evidenceDownloadUrl("a/b")).toBe("/api/backend/evidence/a%2Fb/download");
  });

  it.each([
    [null, "/dashboard"],
    ["/incidents/1?tab=capa", "/incidents/1?tab=capa"],
    ["https://evil.example/", "/dashboard"],
    ["//evil.example/", "/dashboard"],
    ["/\\evil.example", "/dashboard"],
    ["/login?next=/x", "/dashboard"],
    ["/api/session", "/dashboard"],
    ["javascript:alert(1)", "/dashboard"],
  ])("safeNextPath(%s) -> %s", (input, expected) => {
    expect(safeNextPath(input)).toBe(expected);
  });
});
