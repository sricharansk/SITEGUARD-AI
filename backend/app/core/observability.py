import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.services.audit import current_correlation_id

log = logging.getLogger("siteguard")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        payload.update(getattr(record, "extra_fields", {}))
        return json.dumps(payload)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger("siteguard")
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    root.propagate = False


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Attach a correlation ID to every request, response, audit event and log line. Never logs bodies."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Correlation-ID", "")
        cid = incoming if 8 <= len(incoming) <= 64 and incoming.replace("-", "").isalnum() else str(uuid.uuid4())
        request.state.correlation_id = cid
        token = current_correlation_id.set(cid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            current_correlation_id.reset(token)
        response.headers["X-Correlation-ID"] = cid
        log.info(
            "request",
            extra={
                "extra_fields": {
                    "correlation_id": cid,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - started) * 1000, 1),
                }
            },
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response
