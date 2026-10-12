"""Backup and restore drill on PostgreSQL + pgvector (Playbook Prompt 47, docs/GOVERNANCE.md#backup-and-restore).

Creates real data through the application (demo seed with knowledge documents, incident evidence files), backs it
up with scripts/backup.py, restores into a fresh database and evidence directory, and checks row counts, evidence
hashes and search on the copy. (Ported from PR #2; stored document originals join the drill with document uploads.)
Runs when SITEGUARD_TEST_POSTGRES_URL is set and
the PostgreSQL client tools are on PATH (or in SITEGUARD_TEST_PG_BIN); the CI `postgres` job does both.
"""

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT, get_settings
from app.core.db import run_migrations
from app.models import Evidence, Incident, Organization, User
from app.seed import seed
from app.services import evidence, rag
from tests.scripts_loader import load_script

backup_script = load_script("backup")
URL = os.environ.get("SITEGUARD_TEST_POSTGRES_URL")
PG_BIN = os.environ.get("SITEGUARD_TEST_PG_BIN") or None
SCRIPT = REPO_ROOT / "scripts" / "backup.py"
pytestmark = [
    pytest.mark.skipif(not URL, reason="set SITEGUARD_TEST_POSTGRES_URL to run the PostgreSQL restore drill"),
    pytest.mark.skipif(
        not all(shutil.which(t, path=PG_BIN) for t in ("pg_dump", "pg_restore", "psql")),
        reason="needs the PostgreSQL client tools (pg_dump, pg_restore, psql)",
    ),
]


def run_script(*args, **env: str) -> subprocess.CompletedProcess[str]:
    pg_bin = ["--pg-bin", PG_BIN] if PG_BIN else []
    cmd = [sys.executable, str(SCRIPT), *pg_bin, *[str(a) for a in args]]
    return subprocess.run(cmd, env={**os.environ, **env}, capture_output=True, text=True, check=False)


@pytest.fixture(scope="module")
def databases():
    admin = create_engine(URL or "", isolation_level="AUTOCOMMIT")
    suffix = uuid.uuid4().hex[:8]
    names = {"source": f"sg_backup_src_{suffix}", "target": f"sg_backup_dst_{suffix}"}
    with admin.connect() as conn:
        for name in names.values():
            conn.execute(text(f'create database "{name}"'))
    base = make_url(URL or "")
    yield {key: base.set(database=name).render_as_string(hide_password=False) for key, name in names.items()}
    with admin.connect() as conn:
        for name in names.values():
            conn.execute(text(f'drop database if exists "{name}" with (force)'))
    admin.dispose()


@pytest.fixture(scope="module")
def source(databases, tmp_path_factory) -> Path:
    """Source database with demo data (including knowledge documents) and two evidence files."""
    evidence_dir = tmp_path_factory.mktemp("evidence-source")
    engine = create_engine(databases["source"])
    run_migrations(engine)
    settings = get_settings()
    previous = settings.evidence_dir
    settings.evidence_dir = evidence_dir  # evidence.store writes under the configured directory
    try:
        with Session(engine) as db:
            seed(db)
            reporter = db.scalars(select(User).where(User.email == "site@demo.siteguard.local")).one()
            for n, incident in enumerate(db.scalars(select(Incident).order_by(Incident.reference).limit(2))):
                content = f"Synthetic site photo note {n} for the backup drill.".encode()
                key, digest = evidence.store(incident.organization_id, incident.id, content)
                db.add(
                    Evidence(
                        incident_id=incident.id,
                        filename=f"note-{n}.txt",
                        content_type="text/plain",
                        size_bytes=len(content),
                        sha256=digest,
                        storage_key=key,
                        uploaded_by=reporter.id,
                    )
                )
            db.commit()
    finally:
        settings.evidence_dir = previous
        engine.dispose()
    return evidence_dir


@pytest.fixture(scope="module")
def drill(databases, source, tmp_path_factory):
    work = tmp_path_factory.mktemp("drill")
    backup_dir, restored = work / "backup", work / "evidence-restored"
    made = run_script(
        "backup", "--evidence-dir", source, "--out", backup_dir, SITEGUARD_DATABASE_URL=databases["source"]
    )
    assert made.returncode == 0, made.stderr
    restored_run = run_script(
        "restore",
        "--backup",
        backup_dir,
        "--evidence-dir",
        restored,
        SITEGUARD_RESTORE_DATABASE_URL=databases["target"],
    )
    assert restored_run.returncode == 0, restored_run.stderr
    return {"backup": backup_dir, "restored": restored, "source_evidence": source, "output": restored_run.stdout}


def _counts(url: str) -> dict[str, int]:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            tables = inspect(conn).get_table_names()
            return {t: conn.execute(text(f'select count(*) from "{t}"')).scalar_one() for t in tables}
    finally:
        engine.dispose()


def test_restore_reproduces_every_row(databases, drill):
    source, target = _counts(databases["source"]), _counts(databases["target"])
    assert source == target
    for table in ("incidents", "evidence", "documents", "document_chunks", "capa_actions", "audit_events"):
        assert source[table] > 0, table
    assert source["evidence"] == 2
    assert '"status": "ok"' in drill["output"]


def test_restored_evidence_matches_the_hashes_recorded_in_the_database(databases, drill):
    engine = create_engine(databases["target"])
    with Session(engine) as db:
        rows = [(e.storage_key, e.sha256) for e in db.scalars(select(Evidence))]
    engine.dispose()
    assert len(rows) == 2
    for key, digest in rows:
        assert backup_script.sha256_file(drill["restored"] / key) == digest
        assert (drill["source_evidence"] / key).read_bytes() == (drill["restored"] / key).read_bytes()


def test_restored_knowledge_is_searchable(databases, drill):
    engine = create_engine(databases["target"])
    with Session(engine) as db:
        org = db.scalars(select(Organization).order_by(Organization.name)).first()
        assert org is not None
        hits = rag.search(db, organization_id=org.id, query="exclusion zone under suspended loads", limit=3)
    engine.dispose()
    assert hits and "Lifting" in hits[0].document_title


def test_restore_refuses_a_database_that_is_not_empty(databases, drill, tmp_path):
    again = run_script(
        "restore",
        "--backup",
        drill["backup"],
        "--evidence-dir",
        tmp_path / "evidence",
        SITEGUARD_RESTORE_DATABASE_URL=databases["target"],
    )
    assert again.returncode == 1 and "is not empty" in again.stderr
    assert not (tmp_path / "evidence").exists()


def test_verify_detects_a_changed_evidence_file(databases, drill, tmp_path):
    copy = tmp_path / "evidence"
    shutil.copytree(drill["restored"], copy)
    ok = run_script(
        "verify",
        "--evidence-dir",
        copy,
        "--manifest",
        drill["backup"] / "manifest.json",
        SITEGUARD_DATABASE_URL=databases["target"],
    )
    assert ok.returncode == 0, ok.stderr
    victim = next(p for p in copy.rglob("*") if p.is_file())
    victim.write_bytes(b"altered after the backup")
    bad = run_script("verify", "--evidence-dir", copy, SITEGUARD_DATABASE_URL=databases["target"])
    assert bad.returncode == 1 and "SHA-256 mismatch" in bad.stderr
