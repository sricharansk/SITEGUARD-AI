"""Fail on known vulnerabilities in Site Guard AI's locked dependencies, except reviewed, unexpired exceptions.

    python scripts/dependency_audit.py pypi --requirements backend/requirements.lock
    python scripts/dependency_audit.py npm --project frontend

pypi  runs pip-audit on the lock file's exact pins (--no-deps --disable-pip, PyPI advisory data). pip-audit reports
      no severity, so every known vulnerability fails.
npm   runs `npm audit --omit=dev --json` on the production dependencies; high and critical advisories fail
      (`--audit-level=high`). Development-only tools (lint, test, build) are not shipped in the images.

Exceptions are read from .github/dependency-audit-exceptions.toml (change with --exceptions). Each needs the
advisory id (GHSA, PYSEC or CVE; aliases match), ecosystem, package, reason, reviewer, review date and an expiry at
most 90 days after review. An invalid or expired entry fails the audit; an unused entry is reported so it can be
removed. --input reads a saved JSON report instead of running the tool (tests). Exit code 0 when nothing is left
after exceptions, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCEPTIONS = REPO_ROOT / ".github" / "dependency-audit-exceptions.toml"
MAX_EXCEPTION_DAYS = 90
NPM_FAILING_SEVERITIES = ("high", "critical")
REQUIRED_FIELDS = ("id", "ecosystem", "package", "reason", "reviewed_by", "reviewed_on", "expires")


class AuditError(Exception):
    """The audit could not run or its configuration is invalid."""


@dataclass(frozen=True)
class Finding:
    ecosystem: str
    package: str
    version: str
    ids: frozenset[str]
    severity: str
    summary: str

    @property
    def primary_id(self) -> str:
        return sorted(self.ids)[0] if self.ids else "unknown"


@dataclass(frozen=True)
class Exception_:
    id: str
    ecosystem: str
    package: str
    reason: str
    reviewed_by: str
    reviewed_on: date
    expires: date

    def matches(self, f: Finding) -> bool:
        return (
            self.ecosystem == f.ecosystem
            and normalize(self.package, f.ecosystem) == normalize(f.package, f.ecosystem)
            and self.id.upper() in {i.upper() for i in f.ids}
        )


def normalize(name: str, ecosystem: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower() if ecosystem == "pypi" else name


# -- exceptions --------------------------------------------------------------------------------------------------


def load_exceptions(path: Path, today: date) -> list[Exception_]:
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise AuditError(f"cannot read {path}: {exc}") from exc
    entries = data.get("exception", [])
    if not isinstance(entries, list):
        raise AuditError(f"{path}: use [[exception]] tables")
    out, problems = [], []
    for n, raw in enumerate(entries, 1):
        missing = [k for k in REQUIRED_FIELDS if not raw.get(k)]
        if missing:
            problems.append(f"exception {n}: missing {', '.join(missing)}")
            continue
        if raw["ecosystem"] not in ("pypi", "npm"):
            problems.append(f"exception {n}: ecosystem must be pypi or npm")
            continue
        if not isinstance(raw["reviewed_on"], date) or not isinstance(raw["expires"], date):
            problems.append(f"exception {n}: reviewed_on and expires must be dates (YYYY-MM-DD, unquoted)")
            continue
        entry = Exception_(**{k: raw[k] for k in REQUIRED_FIELDS})
        if (entry.expires - entry.reviewed_on).days > MAX_EXCEPTION_DAYS:
            problems.append(f"exception {n} ({entry.id}): expires more than {MAX_EXCEPTION_DAYS} days after review")
        elif entry.expires < today:
            problems.append(f"exception {n} ({entry.id}): expired on {entry.expires}; review it again or fix")
        else:
            out.append(entry)
    if problems:
        raise AuditError(f"{path}:\n  " + "\n  ".join(problems))
    return out


# -- tool output -------------------------------------------------------------------------------------------------


def run_json(cmd: list[str], cwd: Path | None = None) -> dict:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise AuditError(f"{cmd[0]} is not installed") from exc
    try:
        return json.loads(proc.stdout)
    except ValueError:
        raise AuditError(f"{' '.join(cmd)} failed (exit {proc.returncode}): {proc.stderr.strip()[-1500:]}") from None


def pypi_findings(report: dict) -> list[Finding]:
    findings: dict[tuple[str, str, frozenset[str]], Finding] = {}
    for dep in report.get("dependencies", []):
        if dep.get("skip_reason"):
            raise AuditError(f"pip-audit skipped {dep.get('name')}: {dep['skip_reason']}")
        for vuln in dep.get("vulns", []):
            ids = frozenset([vuln["id"], *vuln.get("aliases", [])])
            fixes = ", ".join(vuln.get("fix_versions") or []) or "none"
            key = (dep["name"], dep.get("version", "?"), ids)  # the same advisory can come from two sources
            findings[key] = Finding("pypi", key[0], key[1], ids, "unknown", f"fixed in: {fixes}")
    return list(findings.values())


def npm_findings(report: dict) -> list[Finding]:
    if "error" in report:
        raise AuditError(f"npm audit failed: {report['error']}")
    findings: dict[tuple[str, str], Finding] = {}
    for vuln in report.get("vulnerabilities", {}).values():
        for via in vuln.get("via", []):
            if not isinstance(via, dict) or via.get("severity") not in NPM_FAILING_SEVERITIES:
                continue  # strings point at another package's advisory, which is listed under that package
            url = via.get("url", "")
            ghsa = url.rsplit("/", 1)[-1] if "/advisories/GHSA-" in url else str(via.get("source"))
            key = (via.get("name", vuln.get("name", "?")), ghsa)
            affected = f"(affected {via.get('range', '?')})"
            findings[key] = Finding("npm", key[0], affected, frozenset([ghsa]), via["severity"], via.get("title", ""))
    return list(findings.values())


# -- audit -------------------------------------------------------------------------------------------------------


def audit(findings: list[Finding], exceptions: list[Exception_], ecosystem: str) -> int:
    remaining = [f for f in findings if not any(e.matches(f) for e in exceptions)]
    excepted = [f for f in findings if f not in remaining]
    unused = [e for e in exceptions if e.ecosystem == ecosystem and not any(e.matches(f) for f in findings)]
    for f in excepted:
        print(f"EXCEPTED  {f.package} {f.version}  {f.primary_id}  ({f.summary})")
    for e in unused:
        print(f"UNUSED    exception {e.id} for {e.package}: nothing matches it any more; remove it")
    for f in remaining:
        print(f"VULNERABLE  {f.package} {f.version}  {', '.join(sorted(f.ids))}  [{f.severity}]  {f.summary}")
    print(f"{ecosystem}: {len(findings)} finding(s), {len(excepted)} excepted, {len(remaining)} failing")
    return 1 if remaining else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ecosystem", choices=["pypi", "npm"])
    ap.add_argument("--requirements", type=Path, default=REPO_ROOT / "backend" / "requirements.lock")
    ap.add_argument("--project", type=Path, default=REPO_ROOT / "frontend")
    ap.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    ap.add_argument("--input", type=Path, help="read this saved JSON report instead of running the audit tool")
    args = ap.parse_args(argv)
    today = datetime.now(UTC).date()
    try:
        exceptions = load_exceptions(args.exceptions, today)
        if args.input:
            report = json.loads(args.input.read_text())
        elif args.ecosystem == "pypi":
            cmd = ["pip-audit", "--requirement", str(args.requirements), "--no-deps", "--disable-pip"]
            report = run_json([*cmd, "--progress-spinner", "off", "--format", "json"])
        else:
            report = run_json(["npm", "audit", "--omit=dev", "--audit-level=high", "--json"], cwd=args.project)
        findings = pypi_findings(report) if args.ecosystem == "pypi" else npm_findings(report)
    except (AuditError, OSError, ValueError) as exc:
        print(f"dependency audit FAILED: {exc}", file=sys.stderr)
        return 1
    return audit(findings, exceptions, args.ecosystem)


if __name__ == "__main__":
    sys.exit(main())
