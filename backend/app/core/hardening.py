"""Login throttling, request body limits and HTTP security headers (docs/SECURITY.md).

The throttle is in memory, so each replica counts on its own; with N replicas an attacker gets at most N times the
budget. Move it to Redis or the database before scaling out beyond a few replicas.
"""

import threading
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.errors import _envelope


class LoginThrottle:
    """Counts failed logins per (email, client) and per email inside a sliding window."""

    def __init__(self) -> None:
        self._failures: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _window(self, key: tuple[str, str], now: float) -> deque[float]:
        q = self._failures[key]
        horizon = now - get_settings().login_window_seconds
        while q and q[0] < horizon:
            q.popleft()
        return q

    def retry_after(self, email: str, client: str) -> int:
        """Seconds until another attempt is allowed, or 0 if allowed now."""
        s = get_settings()
        now = time.monotonic()
        with self._lock:
            checks = [
                (self._window((email, client), now), s.login_max_failures),
                (self._window((email, "*"), now), s.login_max_failures_per_account),
            ]
            waits = [int(q[0] + s.login_window_seconds - now) + 1 for q, limit in checks if len(q) >= limit]
        return max(waits, default=0)

    def failed(self, email: str, client: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._window((email, client), now).append(now)
            self._window((email, "*"), now).append(now)

    def succeeded(self, email: str, client: str) -> None:
        with self._lock:
            self._failures.pop((email, client), None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_throttle = LoginThrottle()

# The web app is a Next.js static export: its bootstrap scripts are inline, so script-src needs 'unsafe-inline'.
# Everything else is locked to the same origin. /docs (Swagger UI) loads assets from a CDN and is left without CSP.
WEB_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/app"):
            h.setdefault("Content-Security-Policy", WEB_CSP)
        else:
            h.setdefault("Cache-Control", "no-store")  # API responses can hold incident data
        if get_settings().env not in ("local", "test"):
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


# Room for multipart boundaries and form fields around the largest allowed file.
BODY_OVERHEAD_BYTES = 1024 * 1024


def max_body_bytes() -> int:
    s = get_settings()
    return max(s.document_max_bytes, s.evidence_max_bytes) + BODY_OVERHEAD_BYTES


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Refuse request bodies over the largest allowed upload before they are read.

    Multipart forms are spooled to disk while FastAPI parses them, before authentication runs, so without this
    limit an anonymous client could fill the disk. A declared Content-Length is checked up front; chunked bodies
    are counted as they arrive and cut off at the limit.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = max_body_bytes()
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            await self._reject(scope, send, limit)
            return
        received = 0
        exceeded = False
        started = False

        async def counting_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if exceeded:
                return  # whatever the app answers to a cut-off body is replaced by the 413 below
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except _BodyTooLarge:
            pass
        if exceeded and not started:
            await self._reject(scope, send, limit)

    @staticmethod
    async def _reject(scope: Scope, send: Send, limit: int) -> None:
        response = _envelope(Request(scope), 413, "FILE_TOO_LARGE", f"Request body exceeds {limit} bytes")
        await response(scope, _no_receive, send)


async def _no_receive() -> Message:
    return {"type": "http.disconnect"}
