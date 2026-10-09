// @vitest-environment node
// CSRF defence: state-changing requests must come from this host (or a configured origin).
import { describe, expect, it } from "vitest";
import { errorResponse, isAllowedOrigin } from "@/lib/server/http";

const headers = (values: Record<string, string>) => new Headers(values);

describe("isAllowedOrigin", () => {
  it("lets safe methods through without an Origin", () => {
    expect(isAllowedOrigin("GET", headers({}))).toBe(true);
    expect(isAllowedOrigin("head", headers({}))).toBe(true);
  });

  it("accepts a write whose Origin matches the Host", () => {
    expect(isAllowedOrigin("POST", headers({ origin: "http://localhost:3000", host: "localhost:3000" }))).toBe(true);
    expect(isAllowedOrigin("PATCH", headers({ origin: "https://SiteGuard.example", host: "siteguard.example" }))).toBe(true);
  });

  it.each([
    ["no Origin", { host: "localhost:3000" }],
    ["a null Origin", { origin: "null", host: "localhost:3000" }],
    ["another site", { origin: "https://evil.example", host: "localhost:3000" }],
    ["another port", { origin: "http://localhost:4000", host: "localhost:3000" }],
    ["a look-alike host", { origin: "http://localhost:3000.evil.example", host: "localhost:3000" }],
    ["a non-http scheme", { origin: "file://localhost:3000", host: "localhost:3000" }],
    ["a malformed Origin", { origin: "not a url", host: "localhost:3000" }],
  ])("refuses a write from %s", (_label, values) => {
    expect(isAllowedOrigin("POST", headers(values))).toBe(false);
    expect(isAllowedOrigin("DELETE", headers(values))).toBe(false);
  });

  it("accepts an explicitly configured origin when a proxy rewrites Host", () => {
    const h = headers({ origin: "https://safety.example", host: "web:3000" });
    expect(isAllowedOrigin("POST", h)).toBe(false);
    expect(isAllowedOrigin("POST", h, ["https://safety.example"])).toBe(true);
  });
});

describe("errorResponse", () => {
  it("returns the API envelope with a correlation ID in body and header", async () => {
    const res = errorResponse(403, "FORBIDDEN", "Request origin is not allowed.");
    expect(res.status).toBe(403);
    const body = (await res.json()) as { data: null; error: { code: string; message: string; correlation_id: string } };
    expect(body.data).toBeNull();
    expect(body.error.code).toBe("FORBIDDEN");
    expect(body.error.correlation_id).toBe(res.headers.get("x-correlation-id"));
    expect(res.headers.get("cache-control")).toBe("no-store");
  });
});
