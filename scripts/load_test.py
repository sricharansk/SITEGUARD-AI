"""Load test a running Site Guard AI deployment with a realistic mix of readers and incident reporters.

Usage:
    python scripts/load_test.py --base-url http://localhost:8000 --users 20 --duration 60
    python scripts/load_test.py --base-url http://localhost:8000 --users 40 --writers 4 --duration 120 \
        --out docs/LOAD_TEST.md --json load.json --max-error-rate 0 --max-p95-ms 1500

Readers (project manager, HSE manager, QA/QC engineer, auditor) open the dashboard, the incident list, incident
workspaces, the action queue, notifications and knowledge search. Writers (safety engineer) report a synthetic
incident and run the full multi-agent investigation on it, the heaviest request the API serves.

Writers create real records, so --writers is 0 unless asked for, and the script refuses to run against a
deployment whose /health reports `production`. Use the demo accounts of a local or staging stack; the password
is read from SITEGUARD_LOAD_PASSWORD (default: the demo password), never from the command line. Tokens are never
printed. Exit code 1 when a --max-* threshold is exceeded or a request fails before the run starts.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

READERS = [
    "pm@demo.siteguard.local",
    "hse@demo.siteguard.local",
    "qa@demo.siteguard.local",
    "auditor@demo.siteguard.local",
]
WRITER = "safety@demo.siteguard.local"
SEARCHES = [
    "edge protection guardrail",
    "trench box inspection",
    "hot work permit fire watch",
    "concrete cover spacers",
    "crane lift plan wind",
    "waterproofing membrane laps",
]
# (weight, name) of what a reader does next; the names are the rows of the report.
READ_MIX = [
    (3, "GET /dashboard"),
    (3, "GET /projects/{id}/incidents"),
    (4, "GET /incidents/{id}"),
    (2, "GET /capa"),
    (2, "GET /notifications"),
    (2, "GET /search"),
    (1, "GET /me"),
]
TIMEOUT = httpx.Timeout(60.0, connect=10.0)


@dataclass
class Stats:
    latencies: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    statuses: dict[str, dict[int, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))

    def record(self, name: str, ms: float, status: int) -> None:
        self.latencies[name].append(ms)
        self.statuses[name][status] += 1
        if not 200 <= status < 300:
            self.errors[name] += 1


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, math.ceil(p / 100 * len(ordered)) - 1))  # nearest rank
    return ordered[k]


class Runner:
    def __init__(self, args: argparse.Namespace, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.args = args
        self.transport = transport  # tests drive the app in process
        self.base = args.base_url.rstrip("/")
        self.password = os.environ.get("SITEGUARD_LOAD_PASSWORD", "siteguard-demo")
        self.stats = Stats()
        self.tokens: dict[str, str] = {}
        self.project_id = ""
        self.incident_ids: list[str] = []
        self.created = 0
        self.deadline = 0.0

    async def call(
        self, http: httpx.AsyncClient, name: str, method: str, path: str, token: str, **kw
    ) -> httpx.Response | None:
        started = time.perf_counter()
        try:
            r = await http.request(method, self.base + path, headers={"Authorization": f"Bearer {token}"}, **kw)
        except httpx.HTTPError:
            self.stats.record(name, (time.perf_counter() - started) * 1000, 0)
            return None
        self.stats.record(name, (time.perf_counter() - started) * 1000, r.status_code)
        return r

    async def setup(self, http: httpx.AsyncClient) -> None:
        health = (await http.get(self.base + "/health")).json()["data"]
        if health.get("env") == "production":
            raise SystemExit("Refusing to load test a production deployment.")
        accounts = READERS + ([WRITER] if self.args.writers else [])
        for email in accounts:
            r = await http.post(self.base + "/auth/login", json={"email": email, "password": self.password})
            if r.status_code != 200:
                raise SystemExit(f"Sign-in failed for {email}: HTTP {r.status_code}")
            self.tokens[email] = r.json()["data"]["access_token"]
        auth = {"Authorization": f"Bearer {self.tokens[READERS[0]]}"}
        projects = (await http.get(self.base + "/projects", headers=auth)).json()["data"]
        for project in projects:  # the first project with incidents to read
            listed = await http.get(f"{self.base}/projects/{project['id']}/incidents", headers=auth)
            self.project_id, self.incident_ids = project["id"], [i["id"] for i in listed.json()["data"]]
            if self.incident_ids:
                break
        else:
            raise SystemExit("No visible project has incidents to read; seed the demo data first.")

    async def reader(self, http: httpx.AsyncClient, n: int, rng: random.Random) -> None:
        token = self.tokens[READERS[n % len(READERS)]]
        names = [name for _, name in READ_MIX]
        weights = [w for w, _ in READ_MIX]
        pid = self.project_id
        while time.monotonic() < self.deadline:
            name = rng.choices(names, weights)[0]
            if name == "GET /dashboard":
                await self.call(http, name, "GET", f"/dashboard?project_id={pid}", token)
            elif name == "GET /projects/{id}/incidents":
                await self.call(http, name, "GET", f"/projects/{pid}/incidents", token)
            elif name == "GET /incidents/{id}":
                await self.call(http, name, "GET", f"/incidents/{rng.choice(self.incident_ids)}", token)
            elif name == "GET /capa":
                await self.call(http, name, "GET", f"/capa?project_id={pid}", token)
            elif name == "GET /notifications":
                await self.call(http, name, "GET", "/notifications", token)
            elif name == "GET /search":
                q = rng.choice(SEARCHES)
                await self.call(http, name, "GET", "/search", token, params={"q": q, "project_id": pid})
            else:
                await self.call(http, name, "GET", "/me", token)
            await asyncio.sleep(self.args.think_ms / 1000)

    async def writer(self, http: httpx.AsyncClient, n: int) -> None:
        token = self.tokens[WRITER]
        k = 0
        while time.monotonic() < self.deadline:
            k += 1
            body = {
                "title": f"Load test {n}-{k}: worker slipped near unprotected slab edge",
                "description": "Synthetic load-test report. A worker slipped near an unprotected slab edge on level 3 "
                "while carrying formwork panels; no injury. Guardrail had been removed for a delivery.",
                "domain": "SAFETY",
                "severity": "MEDIUM",
                "occurred_at": datetime.now(UTC).isoformat(),
                "location": "Level 3 east edge",
                "activity": "Formwork",
                "people_involved": 1,
                "immediate_actions": "Area barricaded, guardrail reinstated.",
            }
            r = await self.call(
                http,
                "POST /projects/{id}/incidents",
                "POST",
                f"/projects/{self.project_id}/incidents",
                token,
                json=body,
            )
            if r is None or r.status_code != 201:
                await asyncio.sleep(1)
                continue
            self.created += 1
            await self.call(
                http,
                "POST /incidents/{id}/investigate",
                "POST",
                f"/incidents/{r.json()['data']['id']}/investigate",
                token,
            )
            await asyncio.sleep(self.args.think_ms / 1000)

    async def run(self) -> dict:
        limits = httpx.Limits(max_connections=self.args.users + self.args.writers + 5)
        async with httpx.AsyncClient(timeout=TIMEOUT, limits=limits, transport=self.transport) as http:
            await self.setup(http)
            started = time.monotonic()
            self.deadline = started + self.args.duration
            rng = random.Random(self.args.seed)
            tasks = []
            for i in range(self.args.users):
                tasks.append(asyncio.create_task(self.reader(http, i, random.Random(rng.random()))))
                if self.args.ramp:
                    await asyncio.sleep(self.args.ramp / max(self.args.users, 1))
            tasks += [asyncio.create_task(self.writer(http, i)) for i in range(self.args.writers)]
            await asyncio.gather(*tasks)
            elapsed = time.monotonic() - started
        return self.summary(elapsed)

    def summary(self, elapsed: float) -> dict:
        rows = []
        all_ms: list[float] = []
        total_errors = 0
        for name in sorted(self.stats.latencies):
            ms = self.stats.latencies[name]
            all_ms += ms
            total_errors += self.stats.errors[name]
            rows.append(
                {
                    "endpoint": name,
                    "requests": len(ms),
                    "rps": round(len(ms) / elapsed, 2),
                    "p50_ms": round(pct(ms, 50), 1),
                    "p95_ms": round(pct(ms, 95), 1),
                    "p99_ms": round(pct(ms, 99), 1),
                    "max_ms": round(max(ms), 1),
                    "mean_ms": round(statistics.fmean(ms), 1),
                    "errors": self.stats.errors[name],
                    "statuses": dict(self.stats.statuses[name]),
                }
            )
        reads = [m for r in rows if r["endpoint"].startswith("GET") for m in self.stats.latencies[r["endpoint"]]]
        return {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "base_url": self.base,
            "readers": self.args.users,
            "writers": self.args.writers,
            "think_ms": self.args.think_ms,
            "duration_s": round(elapsed, 1),
            "requests": len(all_ms),
            "rps": round(len(all_ms) / elapsed, 2),
            "error_rate": round(total_errors / len(all_ms), 4) if all_ms else 0.0,
            "read_p50_ms": round(pct(reads, 50), 1),
            "read_p95_ms": round(pct(reads, 95), 1),
            "read_p99_ms": round(pct(reads, 99), 1),
            "incidents_created": self.created,
            "endpoints": rows,
        }


def to_markdown(s: dict) -> str:
    md = [
        f"### {s['readers']} readers, {s['writers']} writers, think time {s['think_ms']} ms",
        "",
        f"{s['requests']} requests in {s['duration_s']} s ({s['rps']} req/s), error rate {s['error_rate']:.2%}. "
        f"Read latency p50 {s['read_p50_ms']} ms, p95 {s['read_p95_ms']} ms, p99 {s['read_p99_ms']} ms. "
        f"Incidents reported and investigated: {s['incidents_created']}.",
        "",
        "| Endpoint | Requests | req/s | p50 ms | p95 ms | p99 ms | max ms | Errors |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in s["endpoints"]:
        md.append(
            f"| `{r['endpoint']}` | {r['requests']} | {r['rps']} | {r['p50_ms']} | {r['p95_ms']} | {r['p99_ms']} | "
            f"{r['max_ms']} | {r['errors']} |"
        )
    return "\n".join(md) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(prog="python scripts/load_test.py")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--users", type=int, default=10, help="concurrent readers")
    ap.add_argument("--writers", type=int, default=0, help="concurrent incident reporters (create records)")
    ap.add_argument("--duration", type=float, default=30.0, help="seconds")
    ap.add_argument("--ramp", type=float, default=0.0, help="seconds to start all readers")
    ap.add_argument("--think-ms", type=float, default=0.0, help="pause between a user's requests")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", help="append a Markdown section to this file")
    ap.add_argument("--json", help="write the full result as JSON")
    ap.add_argument("--max-error-rate", type=float, help="fail when the error rate is above this (0-1)")
    ap.add_argument("--max-p95-ms", type=float, help="fail when read p95 latency is above this")
    args = ap.parse_args()
    if args.users < 1 or args.writers < 0 or args.duration <= 0:
        ap.error("--users must be >= 1, --writers >= 0 and --duration > 0")

    result = asyncio.run(Runner(args).run())
    md = to_markdown(result)
    print(md)
    if args.out:
        with open(args.out, "a") as fh:
            fh.write("\n" + md)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(result, fh, indent=1)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as fh:
            fh.write("## Load test\n\n" + md)
    failed = []
    if args.max_error_rate is not None and result["error_rate"] > args.max_error_rate:
        failed.append(f"error rate {result['error_rate']:.2%} > {args.max_error_rate:.2%}")
    if args.max_p95_ms is not None and result["read_p95_ms"] > args.max_p95_ms:
        failed.append(f"read p95 {result['read_p95_ms']} ms > {args.max_p95_ms} ms")
    if failed:
        print("FAIL: " + "; ".join(failed), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
