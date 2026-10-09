"""Run work on untrusted bytes (document parsing, image decoding) in a child process with CPU, memory and wall-clock
limits, so a hostile file cannot stall or exhaust the API process (DECISIONS 017)."""

import json
import logging
import os
import subprocess
import sys

log = logging.getLogger("siteguard.isolation")


class WorkerTimeout(Exception):
    pass


class WorkerCrashed(Exception):
    """The child exited without a result, usually because it hit the memory or CPU limit."""


def run_worker(module: str, args: list[str], content: bytes, *, timeout: float, memory_mb: int) -> dict:
    """Run `python -m <module> <args>` with `content` on stdin and return the JSON object it writes to stdout."""

    def limits() -> None:  # pragma: no cover - runs in the child
        try:
            import resource

            resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (max(1, int(timeout)),) * 2)
        except (ImportError, ValueError, OSError):
            pass

    env = {k: v for k, v in os.environ.items() if k in ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "SYSTEMROOT")}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", module, *args],
            input=content,
            capture_output=True,
            timeout=timeout,
            preexec_fn=limits if os.name == "posix" else None,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkerTimeout(module) from exc
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        log.warning("worker process failed", extra={"extra_fields": {"code": proc.returncode, "module": module}})
        raise WorkerCrashed(module) from None
    if not isinstance(result, dict):
        raise WorkerCrashed(module)
    return result
