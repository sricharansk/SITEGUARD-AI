"""Run work on untrusted bytes (document parsing, image decoding) in a child process with CPU, memory and wall-clock
limits, so a hostile file cannot stall or exhaust the API process (DECISIONS 017).

The child sets its own limits at startup (`apply_limits`), because `preexec_fn` is unsafe in a threaded server. A
process-wide semaphore caps how many children run at once.
"""

import json
import logging
import os
import subprocess
import sys
import threading

log = logging.getLogger("siteguard.isolation")

MAX_CONCURRENT_WORKERS = 4
_slots = threading.BoundedSemaphore(MAX_CONCURRENT_WORKERS)
_ENV_MEMORY = "SITEGUARD_WORKER_MEMORY_MB"
_ENV_CPU = "SITEGUARD_WORKER_CPU_SECONDS"


class WorkerTimeout(Exception):
    pass


class WorkerCrashed(Exception):
    """The child exited without a result, usually because it hit the memory or CPU limit."""


def apply_limits() -> None:
    """Called first thing in a worker process: cap its address space and CPU time."""
    try:
        import resource

        memory_mb = int(os.environ.get(_ENV_MEMORY, "0"))
        cpu = int(os.environ.get(_ENV_CPU, "0"))
        if memory_mb:
            resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024 * 1024,) * 2)
        if cpu:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu,) * 2)
    except (ImportError, ValueError, OSError):  # pragma: no cover - non-POSIX platforms
        pass


def run_worker(module: str, args: list[str], content: bytes, *, timeout: float, memory_mb: int) -> dict:
    """Run `python -m <module> <args>` with `content` on stdin and return the JSON object it writes to stdout."""
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "SYSTEMROOT")}
    env[_ENV_MEMORY] = str(memory_mb)
    env[_ENV_CPU] = str(max(1, int(timeout)))
    if not _slots.acquire(timeout=timeout):
        raise WorkerTimeout(module)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", module, *args],
            input=content,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkerTimeout(module) from exc
    finally:
        _slots.release()
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        log.warning("worker process failed", extra={"extra_fields": {"code": proc.returncode, "module": module}})
        raise WorkerCrashed(module) from None
    if not isinstance(result, dict):
        raise WorkerCrashed(module)
    return result
