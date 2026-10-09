// @vitest-environment node
// Sign-in stores the API token in an httpOnly cookie and never returns it to browser JavaScript.
import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DELETE, POST } from "@/app/api/session/route";
import { proxy } from "@/proxy";

const WEB = "http://localhost:3000";

function loginRequest(body: unknown, origin: string | null = WEB) {
  const headers: Record<string, string> = { host: "localhost:3000", "content-type": "application/json" };
  if (origin) headers.origin = origin;
  return new NextRequest(`${WEB}/api/session`, { method: "POST", headers, body: JSON.stringify(body) });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.stubEnv("SITEGUARD_API_URL", "http://api.test:8000");
  fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ data: { access_token: "jwt-token-value", token_type: "bearer" }, error: null }), {
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

describe("POST /api/session", () => {
  it("signs in against the API and sets an httpOnly, SameSite=Lax cookie", async () => {
    const res = await POST(loginRequest({ email: " hse@example.test ", password: "pw" }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ data: { authenticated: true }, error: null });
    expect(JSON.stringify(body)).not.toContain("jwt-token-value");

    const cookie = res.headers.get("set-cookie") ?? "";
    expect(cookie).toContain("sg_session=jwt-token-value");
    expect(cookie).toMatch(/HttpOnly/i);
    expect(cookie).toMatch(/SameSite=lax/i);
    expect(cookie).toMatch(/Path=\//);
    expect(cookie).not.toMatch(/Secure/i); // NODE_ENV is "test"; production adds Secure

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://api.test:8000/auth/login");
    expect(JSON.parse(String(init.body))).toEqual({ email: "hse@example.test", password: "pw" });
  });

  it("marks the cookie Secure in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    const res = await POST(loginRequest({ email: "hse@example.test", password: "pw" }));
    expect(res.headers.get("set-cookie")).toMatch(/Secure/i);
  });

  it("refuses a sign-in posted from another site", async () => {
    const res = await POST(loginRequest({ email: "hse@example.test", password: "pw" }, "https://evil.example"));
    expect(res.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("validates the body before calling the API", async () => {
    const res = await POST(loginRequest({ email: "x", password: "" }));
    expect(res.status).toBe(400);
    expect(((await res.json()) as { error: { code: string } }).error.code).toBe("INVALID_REQUEST");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("passes the API's sign-in error through and sets no cookie", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ data: null, error: { code: "INVALID_CREDENTIALS", message: "Wrong email or password.", correlation_id: "cid-l1" } }),
        { status: 401, headers: { "content-type": "application/json", "x-correlation-id": "cid-l1" } },
      ),
    );
    const res = await POST(loginRequest({ email: "hse@example.test", password: "wrong" }));
    expect(res.status).toBe(401);
    expect(((await res.json()) as { error: { code: string } }).error.code).toBe("INVALID_CREDENTIALS");
    expect(res.headers.get("x-correlation-id")).toBe("cid-l1");
    expect(res.headers.get("set-cookie")).toBeNull();
  });

  it("rejects a success response without a token", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ data: {}, error: null }), { headers: { "content-type": "application/json" } }));
    const res = await POST(loginRequest({ email: "hse@example.test", password: "pw" }));
    expect(res.status).toBe(502);
    expect(res.headers.get("set-cookie")).toBeNull();
  });
});

describe("DELETE /api/session", () => {
  it("clears the cookie", async () => {
    const res = await DELETE(new NextRequest(`${WEB}/api/session`, { method: "DELETE", headers: { host: "localhost:3000", origin: WEB } }));
    expect(res.status).toBe(200);
    expect(res.headers.get("set-cookie")).toMatch(/sg_session=;.*Max-Age=0/i);
  });

  it("refuses a cross-site sign-out", async () => {
    const res = await DELETE(
      new NextRequest(`${WEB}/api/session`, { method: "DELETE", headers: { host: "localhost:3000", origin: "https://evil.example" } }),
    );
    expect(res.status).toBe(403);
  });
});

describe("page proxy (session redirect)", () => {
  it("sends visitors without a session to /login with the page to return to", () => {
    const res = proxy(new NextRequest(`${WEB}/incidents/abc?tab=capa`));
    expect(res.status).toBe(307);
    const location = new URL(res.headers.get("location")!);
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("/incidents/abc?tab=capa");
  });

  it("lets the login page and signed-in visitors through", () => {
    expect(proxy(new NextRequest(`${WEB}/login`)).headers.get("location")).toBeNull();
    const signedIn = proxy(new NextRequest(`${WEB}/dashboard`, { headers: { cookie: "sg_session=t" } }));
    expect(signedIn.headers.get("location")).toBeNull();
  });
});
