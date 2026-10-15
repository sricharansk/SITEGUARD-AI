"""Operational scripts that need no PostgreSQL: backup file handling and the smoke test's API checks.

The PostgreSQL backup and restore drill is tests/test_backup_restore.py (CI `postgres` job).
"""

import io
import json
import tarfile

import pytest

from tests.conftest import PASSWORD
from tests.scripts_loader import load_script

backup = load_script("backup")
smoke_test = load_script("smoke_test")
load_test = load_script("load_test")


# -- backup.py ---------------------------------------------------------------------------------------------------


def test_database_url_becomes_libpq_environment_without_the_password_in_argv():
    env = backup.libpq_env("postgresql+psycopg://sg%40ops:p%40ss%2Fword@db.internal:5433/siteguard?sslmode=require")
    assert env == {
        "PGDATABASE": "siteguard",
        "PGHOST": "db.internal",
        "PGPORT": "5433",
        "PGUSER": "sg@ops",
        "PGPASSWORD": "p@ss/word",
        "PGSSLMODE": "require",
        "PGCONNECT_TIMEOUT": "15",
    }


@pytest.mark.parametrize("url", ["sqlite:///./siteguard.db", "mysql://u:p@h/db", "postgresql://u:p@h/"])
def test_only_postgresql_urls_with_a_database_are_accepted(url):
    with pytest.raises(backup.BackupError):
        backup.libpq_env(url)


def _evidence_tree(root):
    files = {
        "org-1/inc-1/aaa": b"\x89PNG\r\n\x1a\nphoto",
        "org-1/inc-2/bbb": b"%PDF-1.7 report",
        "org-1/documents/ccc": b"# Procedure\n\nKeep the exclusion zone clear.\n",
    }
    for rel, content in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(content)
    return files


def test_evidence_archive_round_trip_keeps_every_hash(tmp_path):
    source, target = tmp_path / "src", tmp_path / "dst"
    _evidence_tree(source)
    files = backup.evidence_files(source)
    archive = tmp_path / "evidence.tar.gz"
    backup.write_archive(source, files, archive)
    target.mkdir()
    backup.extract_archive(archive, target, files)
    assert backup.evidence_files(target) == files
    assert sorted(files) == ["org-1/documents/ccc", "org-1/inc-1/aaa", "org-1/inc-2/bbb"]


@pytest.mark.parametrize("name", ["../outside", "/etc/passwd", "org-1/../../outside", "not-in-manifest"])
def test_archive_entries_outside_the_manifest_or_the_target_are_refused(tmp_path, name):
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo(name)
        info.size = 4
        tar.addfile(info, io.BytesIO(b"evil"))
    target = tmp_path / "target"
    target.mkdir()
    with pytest.raises(backup.BackupError, match="unexpected entry"):
        backup.extract_archive(archive, target, {"org-1/inc-1/aaa": {"sha256": "0", "size": 4}})
    assert list(target.iterdir()) == []
    assert not (tmp_path / "outside").exists()


def test_symbolic_links_in_the_evidence_directory_are_refused(tmp_path):
    (tmp_path / "real").write_bytes(b"x")
    (tmp_path / "link").symlink_to(tmp_path / "real")
    with pytest.raises(backup.BackupError, match="symbolic link"):
        backup.evidence_files(tmp_path)


def test_file_problems_report_missing_changed_and_unsafe_files(tmp_path):
    files = _evidence_tree(tmp_path)
    good = backup.sha256_file(tmp_path / "org-1/inc-1/aaa")
    (tmp_path / "org-1/inc-2/bbb").write_bytes(b"tampered")
    stored = {
        "evidence": [("org-1/inc-1/aaa", good), ("org-1/inc-2/bbb", "0" * 64), ("org-1/inc-9/gone", "0" * 64)],
        "documents": [("../../etc/passwd", "0" * 64)],
    }
    problems = backup.file_problems(stored, tmp_path)
    assert problems == [
        "evidence: SHA-256 mismatch for org-1/inc-2/bbb",
        "evidence: missing file org-1/inc-9/gone",
        "documents: unsafe storage key '../../etc/passwd'",
    ]
    assert len(files) == 3


def test_row_count_differences_are_reported():
    assert backup.count_problems({"incidents": 3, "evidence": 1}, {"incidents": 3, "evidence": 1}) == []
    assert backup.count_problems({"incidents": 3, "evidence": 1}, {"incidents": 2, "audit_events": 5}) == [
        "row count for audit_events: backup None, database 5",
        "row count for evidence: backup 1, database None",
        "row count for incidents: backup 3, database 2",
    ]


def _fake_backup(directory, dump=b"PGDMP fake dump"):
    directory.mkdir()
    (directory / "database.dump").write_bytes(dump)
    source = directory.parent / "fake-evidence"
    _evidence_tree(source)
    files = backup.evidence_files(source)
    backup.write_archive(source, files, directory / "evidence.tar.gz")
    manifest = {
        "format": backup.FORMAT,
        "database": {
            "file": "database.dump",
            "sha256": backup.sha256_file(directory / "database.dump"),
            "size": len(dump),
            "row_counts": {},
            "alembic_revision": "0003",
        },
        "evidence": {
            "file": "evidence.tar.gz",
            "sha256": backup.sha256_file(directory / "evidence.tar.gz"),
            "size": (directory / "evidence.tar.gz").stat().st_size,
            "files": files,
        },
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))


@pytest.mark.parametrize("damaged", ["database.dump", "evidence.tar.gz"])
def test_restore_refuses_a_damaged_backup_before_touching_the_database(tmp_path, monkeypatch, capsys, damaged):
    _fake_backup(tmp_path / "backup")
    path = tmp_path / "backup" / damaged
    data = bytearray(path.read_bytes())
    data[-1] ^= 0xFF
    path.write_bytes(bytes(data))
    # Unreachable on purpose: the checksum check must fail first, so the database is never contacted.
    monkeypatch.setenv("SITEGUARD_RESTORE_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/never")
    code = backup.main(["restore", "--backup", str(tmp_path / "backup"), "--evidence-dir", str(tmp_path / "out")])
    assert code == 1
    assert "SHA-256 mismatch" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_restore_refuses_an_unknown_backup_format(tmp_path, monkeypatch, capsys):
    _fake_backup(tmp_path / "backup")
    manifest = tmp_path / "backup" / "manifest.json"
    manifest.write_text(json.dumps({**json.loads(manifest.read_text()), "format": "something-else/9"}))
    monkeypatch.setenv("SITEGUARD_RESTORE_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/never")
    assert backup.main(["restore", "--backup", str(tmp_path / "backup"), "--evidence-dir", str(tmp_path / "o")]) == 1
    assert "unsupported backup format" in capsys.readouterr().err


def test_backup_needs_the_database_url_from_the_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SITEGUARD_DATABASE_URL", raising=False)
    code = backup.main(["backup", "--evidence-dir", str(tmp_path), "--out", str(tmp_path / "b")])
    assert code == 1
    assert "set SITEGUARD_DATABASE_URL" in capsys.readouterr().err


# -- smoke_test.py (API half; the web half runs against the real web app in CI) --------------------------------------


def _smoke(client, **kw):
    values = {"api_url": "http://testserver", "web_url": None, "email": None, "password": None, "require_login": False}
    values.update(kw)
    return smoke_test.Smoke(http=client, **values)


def test_smoke_test_passes_against_the_api_with_a_read_only_account(client):
    smoke = _smoke(client, email="auditor@demo.siteguard.local", password=PASSWORD)
    smoke.api_checks()
    assert [(r.name, r.status) for r in smoke.results] == [
        ("api: GET /health", "PASS"),
        ("api: anonymous read refused", "PASS"),
        ("api: unknown user refused", "PASS"),
        ("api: sign in", "PASS"),
        ("api: authenticated read (/me, /projects)", "PASS"),
    ]
    assert "AUDITOR" in smoke.results[-1].detail
    assert smoke.report() == 0


def test_smoke_test_skips_sign_in_without_credentials(client):
    smoke = _smoke(client)
    smoke.api_checks()
    assert [r.status for r in smoke.results] == ["PASS", "PASS", "PASS", "SKIP", "SKIP"]
    assert smoke.report() == 0


def test_smoke_test_fails_without_credentials_when_login_is_required(client):
    smoke = _smoke(client, require_login=True)
    smoke.api_checks()
    assert smoke.results[3].status == "FAIL" and "required" in smoke.results[3].detail
    assert smoke.report() == 1


def test_smoke_test_fails_on_a_wrong_password_and_never_prints_it(client, capsys):
    smoke = _smoke(client, email="auditor@demo.siteguard.local", password="wrong-password-for-smoke")
    smoke.api_checks()
    assert smoke.results[3].status == "FAIL"
    assert smoke.report() == 1
    assert "wrong-password-for-smoke" not in capsys.readouterr().out


# -- dependency_audit.py -----------------------------------------------------------------------------------------

dependency_audit = load_script("dependency_audit")
TODAY = dependency_audit.date(2026, 10, 9)

# Shapes copied from real `pip-audit --format json` and `npm audit --json` output (09 October 2026).
PIP_AUDIT_REPORT = {
    "dependencies": [
        {"name": "fastapi", "version": "0.143.0", "vulns": []},
        {
            "name": "Requests",
            "version": "2.19.0",
            "vulns": [
                # The PyPI service reports the same advisory twice (one entry per source).
                {"id": "PYSEC-2018-28", "fix_versions": ["2.20.0"], "aliases": ["GHSA-x84v-xcm2-53pg"]},
                {"id": "PYSEC-2018-28", "fix_versions": ["2.20.0"], "aliases": ["GHSA-x84v-xcm2-53pg"]},
            ],
        },
    ],
    "fixes": [],
}
NPM_AUDIT_REPORT = {
    "auditReportVersion": 2,
    "vulnerabilities": {
        "braces": {
            "name": "braces",
            "severity": "high",
            "via": [
                {
                    "source": 1240992,
                    "name": "braces",
                    "title": "braces vulnerable to stack-exhaustion denial of service",
                    "url": "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm",
                    "severity": "high",
                    "range": "<=3.0.3",
                }
            ],
        },
        "micromatch": {"name": "micromatch", "severity": "high", "via": ["braces"]},
        "tiny": {
            "name": "tiny",
            "severity": "moderate",
            "via": [
                {
                    "source": 1,
                    "name": "tiny",
                    "url": "https://github.com/advisories/GHSA-aaaa-bbbb-cccc",
                    "severity": "moderate",
                    "range": "<1",
                }
            ],
        },
    },
}


def _exceptions(tmp_path, body: str):
    path = tmp_path / "exceptions.toml"
    path.write_text(body)
    return path


def _entry(**kw) -> str:
    values = {
        "id": '"GHSA-vfj7-8cjw-p6xm"',
        "ecosystem": '"npm"',
        "package": '"braces"',
        "reason": '"Development-only dependency of the linter; not in the image."',
        "reviewed_by": '"Reviewer"',
        "reviewed_on": "2026-10-01",
        "expires": "2026-12-01",
    }
    values.update(kw)
    return "[[exception]]\n" + "\n".join(f"{k} = {v}" for k, v in values.items()) + "\n"


def test_pip_audit_findings_are_deduplicated_and_all_fail():
    findings = dependency_audit.pypi_findings(PIP_AUDIT_REPORT)
    assert len(findings) == 1
    assert findings[0].ids == {"PYSEC-2018-28", "GHSA-x84v-xcm2-53pg"}
    assert dependency_audit.audit(findings, [], "pypi") == 1


def test_npm_findings_keep_only_high_and_critical_advisories():
    findings = dependency_audit.npm_findings(NPM_AUDIT_REPORT)
    assert [(f.package, f.primary_id, f.severity) for f in findings] == [("braces", "GHSA-vfj7-8cjw-p6xm", "high")]


def test_a_reviewed_exception_lets_the_audit_pass(tmp_path, capsys):
    exceptions = dependency_audit.load_exceptions(_exceptions(tmp_path, _entry()), TODAY)
    assert dependency_audit.audit(dependency_audit.npm_findings(NPM_AUDIT_REPORT), exceptions, "npm") == 0
    assert "EXCEPTED  braces" in capsys.readouterr().out


def test_exceptions_match_aliases_and_normalized_python_names(tmp_path):
    body = _entry(id='"GHSA-x84v-xcm2-53pg"', ecosystem='"pypi"', package='"requests"')
    exceptions = dependency_audit.load_exceptions(_exceptions(tmp_path, body), TODAY)
    assert dependency_audit.audit(dependency_audit.pypi_findings(PIP_AUDIT_REPORT), exceptions, "pypi") == 0


def test_an_exception_for_another_package_does_not_hide_a_finding(tmp_path):
    exceptions = dependency_audit.load_exceptions(_exceptions(tmp_path, _entry(package='"other"')), TODAY)
    assert dependency_audit.audit(dependency_audit.npm_findings(NPM_AUDIT_REPORT), exceptions, "npm") == 1


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"expires": "2026-10-08"}, "expired on 2026-10-08"),
        ({"expires": "2027-06-01"}, "more than 90 days"),
        ({"reason": '""'}, "missing reason"),
        ({"ecosystem": '"maven"'}, "ecosystem must be pypi or npm"),
        ({"expires": '"2026-12-01"'}, "must be dates"),
    ],
)
def test_invalid_or_expired_exceptions_fail_the_audit(tmp_path, override, message):
    with pytest.raises(dependency_audit.AuditError, match=message):
        dependency_audit.load_exceptions(_exceptions(tmp_path, _entry(**override)), TODAY)


def test_the_committed_exceptions_file_is_valid():
    # Structure only: an entry that has expired fails the CI audit job, not this test.
    for entry in dependency_audit.load_exceptions(dependency_audit.DEFAULT_EXCEPTIONS, dependency_audit.date.min):
        assert entry.reason and entry.reviewed_by


def test_audit_tool_errors_fail_closed(tmp_path, capsys):
    report = tmp_path / "npm.json"
    report.write_text(json.dumps({"error": {"code": "ENOLOCK", "summary": "no lockfile"}}))
    assert dependency_audit.main(["npm", "--input", str(report)]) == 1
    assert "npm audit failed" in capsys.readouterr().err


# -- load_test.py --------------------------------------------------------------------------------------------------


def _load_args(**kw):
    import argparse

    values = {"base_url": "http://testserver", "users": 2, "writers": 1, "duration": 1.0, "ramp": 0.0}
    values |= {"think_ms": 0.0, "seed": 1} | kw
    return argparse.Namespace(**values)


def test_load_test_runs_readers_and_writers_without_errors(client, monkeypatch):
    import asyncio

    import httpx

    monkeypatch.setenv("SITEGUARD_LOAD_PASSWORD", PASSWORD)
    runner = load_test.Runner(_load_args(), transport=httpx.ASGITransport(app=client.app))
    result = asyncio.run(runner.run())
    names = {r["endpoint"] for r in result["endpoints"]}
    assert result["error_rate"] == 0 and result["requests"] > 0
    assert result["incidents_created"] >= 1 and "POST /incidents/{id}/investigate" in names
    assert "| Endpoint |" in load_test.to_markdown(result)


def test_load_test_refuses_a_production_deployment():
    import asyncio

    import httpx

    health = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": {"env": "production"}}))
    with pytest.raises(SystemExit, match="production"):
        asyncio.run(load_test.Runner(_load_args(), transport=health).run())


def test_load_test_percentiles():
    assert load_test.pct([], 95) == 0.0
    assert load_test.pct([5.0], 99) == 5.0
    values = [float(v) for v in range(1, 101)]
    assert load_test.pct(values, 50) == 50.0 and load_test.pct(values, 95) == 95.0 and load_test.pct(values, 99) == 99.0


# -- label_snapshot.py -------------------------------------------------------------------------------------------


def test_label_snapshot_lists_every_case_and_is_deterministic():
    label_snapshot = load_script("label_snapshot")
    first, second = label_snapshot.snapshot(), label_snapshot.snapshot()
    assert first == second
    assert len(first) == 186  # 120 dev + 46 held-out + 20 seeded incidents
    assert any(line.startswith("heldout_v2.yaml V01 ") for line in first)
    assert any("Worker slipped at unprotected slab edge" in line and "Lifting" not in line for line in first)
