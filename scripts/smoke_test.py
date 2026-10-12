"""Smoke test a running Site Guard AI deployment: health, login, one authenticated read and the web app.

Usage:
    python scripts/smoke_test.py --api-url http://localhost:8000 --web-url http://localhost:8000
    python scripts/smoke_test.py --api-url https://siteguard-staging.example.com \
        --web-url https://siteguard-staging.example.com --wait 300 --require-login

The API serves the web app at /app, so both URLs are normally the same origin; either may be omitted.
Credentials are read from SITEGUARD_SMOKE_EMAIL and SITEGUARD_SMOKE_PASSWORD, never from the command line.
Use a read-only account (AUDITOR or VIEWER). A sign-in as a random unknown user is always checked to be refused.
Without credentials the signed-in checks are skipped, unless --require-login turns missing credentials into a
failure.

Read-only: it signs in and reads. Signing in records an `auth.login` audit event. Tokens and passwords
are never printed. Exit code 0 when every check that ran passed, 1 otherwise. With GITHUB_STEP_SUMMARY
set, the result table is also written there.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass
class Result:
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""


@dataclass
class Smoke:
    api_url: str | None
    web_url: str | None
    email: str | None
    password: str | None
    require_login: bool
    results: list[Result] = field(default_factory=list)
    http: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=TIMEOUT, follow_redirects=False))

    # -- helpers -------------------------------------------------------------------------------------------------

    def check(self, name: str, fn: Callable[[], str]) -> bool:
        try:
            detail = fn()
        except Skip as exc:
            self.results.append(Result(name, "SKIP", str(exc)))
            return True
        except Exception as exc:  # noqa: BLE001 - every failure becomes a FAIL row, never a traceback
            self.results.append(Result(name, "FAIL", _short(exc)))
            return False
        self.results.append(Result(name, "PASS", detail))
        return True

    def request(self, method: str, url: str, **kw) -> httpx.Response:
        try:
            return self.http.request(method, url, **kw)
        finally:
            # Cookies are sent explicitly (Cookie header), so the client jar never decides what is sent.
            self.http.cookies.clear()

    def credentials(self) -> dict[str, str]:
        """The smoke-test account, or Skip (FAIL with --require-login) when none is configured."""
        if self.email and self.password:
            return {"email": self.email, "password": self.password}
        if self.require_login:
            raise AssertionError("SITEGUARD_SMOKE_EMAIL and SITEGUARD_SMOKE_PASSWORD are required (--require-login)")
        raise Skip("no smoke-test credentials (set SITEGUARD_SMOKE_EMAIL and SITEGUARD_SMOKE_PASSWORD)")

    # -- waiting ---------------------------------------------------------------------------------------------------

    def wait_until_healthy(self, seconds: float) -> None:
        targets = [
            u
            for u in (
                f"{self.api_url}/health" if self.api_url else None,
                f"{self.web_url}/health" if self.web_url else None,
            )
            if u
        ]
        deadline = time.monotonic() + seconds
        for url in targets:
            while True:
                try:
                    if self.request("GET", url).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() >= deadline:
                    break  # the health check itself reports the failure
                time.sleep(5)

    # -- API checks ------------------------------------------------------------------------------------------------

    def api_checks(self) -> None:
        base = self.api_url
        token: dict[str, str] = {}

        def health() -> str:
            r = self.request("GET", f"{base}/health")
            data = _envelope(r, 200)
            assert data.get("status") == "ok", f"status {data.get('status')!r}"
            assert r.headers.get("x-correlation-id"), "no X-Correlation-ID header"
            assert r.headers.get("x-content-type-options") == "nosniff", "no nosniff header"
            assert r.headers.get("x-frame-options") == "DENY", "no X-Frame-Options: DENY"
            return f"env={data.get('env')} ai_provider={data.get('ai_provider')}"

        def anonymous_read_refused() -> str:
            r = self.request("GET", f"{base}/projects")
            error = _error(r, 401)
            return f"401 {error.get('code')}"

        def unknown_user_refused() -> str:
            # Works without an account: the login path answers, so the database is reachable.
            error = _error(self.request("POST", f"{base}/auth/login", json=_unknown_user()), 401)
            return f"401 {error.get('code')}"

        def login() -> str:
            r = self.request("POST", f"{base}/auth/login", json=self.credentials())
            data = _envelope(r, 200)
            assert isinstance(data.get("access_token"), str) and data["access_token"], "no access token"
            token["value"] = data["access_token"]
            return "token issued"

        def authenticated_read() -> str:
            if "value" not in token:
                raise Skip("not signed in")
            headers = {"Authorization": f"Bearer {token['value']}"}
            me = _envelope(self.request("GET", f"{base}/me", headers=headers), 200)
            assert str(me.get("email", "")).lower() == (self.email or "").lower(), "/me is not the signed-in user"
            roles = sorted({m.get("role") for m in me.get("memberships", [])})
            projects = _envelope(self.request("GET", f"{base}/projects", headers=headers), 200)
            assert isinstance(projects, list), "projects is not a list"
            return f"/me ok (roles: {', '.join(roles) or 'none'}), {len(projects)} project(s) visible"

        self.check("api: GET /health", health)
        self.check("api: anonymous read refused", anonymous_read_refused)
        self.check("api: unknown user refused", unknown_user_refused)
        self.check("api: sign in", login)
        self.check("api: authenticated read (/me, /projects)", authenticated_read)

    # -- web checks ------------------------------------------------------------------------------------------------

    def web_checks(self) -> None:
        """The web app is a static build served by the API at /app (same origin as the API)."""
        base = self.web_url or ""

        def root_redirects() -> str:
            r = self.request("GET", f"{base}/")
            assert r.status_code in (301, 302, 307, 308), f"expected a redirect, got HTTP {r.status_code}"
            assert r.headers.get("location", "").rstrip("/").endswith("/app"), "does not redirect to /app/"
            return f"{r.status_code} -> {r.headers.get('location')}"

        def app_shell() -> str:
            r = self.request("GET", f"{base}/app/")
            assert r.status_code == 200, f"expected HTTP 200, got {r.status_code}"
            assert "text/html" in r.headers.get("content-type", ""), "not HTML"
            assert "Site Guard AI" in r.text, "page does not look like the Site Guard web app"
            csp = r.headers.get("content-security-policy", "")
            assert "frame-ancestors 'none'" in csp and "default-src 'self'" in csp, "missing or weak CSP"
            return f"{len(r.content)} bytes, CSP present"

        def login_page() -> str:
            r = self.request("GET", f"{base}/app/login/")
            assert r.status_code == 200, f"expected HTTP 200, got {r.status_code}"
            return "login page served"

        def https_only() -> str:
            if not base.startswith("https://"):
                raise Skip("not an https URL (local or loopback stack)")
            r = self.request("GET", f"{base}/health")
            assert "max-age=" in r.headers.get("strict-transport-security", ""), "no Strict-Transport-Security"
            return "HSTS set"

        self.check("web: / redirects to /app/", root_redirects)
        self.check("web: GET /app/ with CSP", app_shell)
        self.check("web: login page", login_page)
        self.check("web: HSTS on https", https_only)

    # -- report ----------------------------------------------------------------------------------------------------

    def report(self) -> int:
        width = max(len(r.name) for r in self.results)
        for r in self.results:
            print(f"{r.status:<4}  {r.name:<{width}}  {r.detail}")
        failed = [r for r in self.results if r.status == "FAIL"]
        print(f"\n{len(self.results) - len(failed)}/{len(self.results)} checks passed or skipped; {len(failed)} failed")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write("### Smoke test\n\n| Result | Check | Detail |\n|---|---|---|\n")
                for r in self.results:
                    f.write(f"| {r.status} | {r.name} | {r.detail.replace('|', '/')} |\n")
        return 1 if failed else 0


class Skip(Exception):
    """A check that could not run (for example no credentials); never counts as a failure."""


def _short(exc: Exception) -> str:
    text = str(exc) or type(exc).__name__
    return text if len(text) <= 200 else text[:197] + "..."


def _json(r: httpx.Response) -> dict:
    try:
        body = r.json()
    except ValueError:
        raise AssertionError(f"HTTP {r.status_code}, body is not JSON") from None
    assert isinstance(body, dict) and "data" in body and "error" in body, f"HTTP {r.status_code}, not an envelope"
    return body


def _envelope(r: httpx.Response, status: int):
    body = _json(r)
    if r.status_code != status:
        code = (body.get("error") or {}).get("code")
        raise AssertionError(f"expected HTTP {status}, got {r.status_code} ({code})")
    assert body["error"] is None, "error set on a successful response"
    return body["data"]


def _error(r: httpx.Response, status: int) -> dict:
    body = _json(r)
    assert r.status_code == status, f"expected HTTP {status}, got {r.status_code}"
    error = body.get("error") or {}
    assert error.get("code") and error.get("message") and error.get("correlation_id"), "incomplete error envelope"
    return error


def _unknown_user() -> dict[str, str]:
    # Random, so it can never match a real account; it costs one attempt of the login rate limit.
    tag = secrets.token_hex(6)
    return {"email": f"smoke-{tag}@invalid.example", "password": secrets.token_urlsafe(16)}


def _base(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise SystemExit(f"not an http(s) URL: {url}")
    return url.rstrip("/")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api-url", help="API base URL, for example http://localhost:8000")
    ap.add_argument("--web-url", help="base URL serving /app (usually the same as --api-url)")
    ap.add_argument("--wait", type=float, default=0, help="seconds to wait for health endpoints before checking")
    ap.add_argument("--require-login", action="store_true", help="fail when no smoke-test credentials are set")
    args = ap.parse_args(argv)
    if not args.api_url and not args.web_url:
        ap.error("give --api-url, --web-url or both")
    smoke = Smoke(
        api_url=_base(args.api_url),
        web_url=_base(args.web_url),
        email=os.environ.get("SITEGUARD_SMOKE_EMAIL") or None,
        password=os.environ.get("SITEGUARD_SMOKE_PASSWORD") or None,
        require_login=args.require_login,
    )
    if args.wait:
        smoke.wait_until_healthy(args.wait)
    if smoke.api_url:
        smoke.api_checks()
    if smoke.web_url:
        smoke.web_checks()
    return smoke.report()


if __name__ == "__main__":
    sys.exit(main())
