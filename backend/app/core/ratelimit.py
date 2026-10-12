"""Small in-process sliding-window limiter. Enough for a single-instance pilot; use a shared store
(Redis or the platform gateway) when running more than one replica."""

import threading
import time
from collections import defaultdict, deque

from app.core.errors import AppError


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                raise AppError("Too many attempts; try again shortly", "RATE_LIMITED", 429)
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
