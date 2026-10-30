"""PostgreSQL + pgvector integration (runs only when SITEGUARD_TEST_POSTGRES_URL points at an empty database).

The default suite runs on SQLite. CI runs this module against the same pgvector image as docker-compose, so the
migrations, the `vector` column type and the `<=>` distance query are exercised on the real engine.
"""

import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.db import Base, run_migrations
from app.models import ChunkEmbedding, Organization
from app.services import rag

URL = os.environ.get("SITEGUARD_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set SITEGUARD_TEST_POSTGRES_URL to run PostgreSQL integration tests")


@pytest.fixture(scope="module")
def pg_engine():
    engine = create_engine(URL or "")
    with engine.begin() as conn:
        conn.execute(text("drop schema public cascade"))
        conn.execute(text("create schema public"))
    run_migrations(engine)
    yield engine
    engine.dispose()


def test_postgres_schema_matches_models(pg_engine):
    with pg_engine.connect() as conn:
        assert conn.execute(text("select extname from pg_extension where extname = 'vector'")).scalar() == "vector"
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff


def test_pgvector_hybrid_search(pg_engine):
    with Session(pg_engine) as db:
        org = Organization(name="PG Org")
        db.add(org)
        db.flush()
        for title, body in (
            ("Excavation Procedure", "Excavations deeper than 1.2 metres are shored or protected by a trench box."),
            ("Hot Works", "A fire watch remains for 60 minutes after welding and grinding finish."),
        ):
            rag.ingest(db, organization_id=org.id, title=title, text=f"# S\n\n{body}", doc_type="PROCEDURE", source="t")
        db.commit()
        assert db.query(ChunkEmbedding).count() == 2
        hits = rag.search(db, organization_id=org.id, query="shoring for excavated trenches", limit=2)
        assert hits[0].document_title == "Excavation Procedure" and hits[0].scores["vector"] > 0


def test_concurrent_incident_reports_get_unique_references(pg_engine):
    """Reports submitted at the same moment each get their own reference instead of failing on the unique key."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import UTC, datetime
    from threading import Barrier

    from app.models import Domain, Incident, Project, Severity, User
    from app.services import incidents

    with Session(pg_engine) as db:
        org = Organization(name="Concurrency Org")
        db.add(org)
        db.flush()
        project = Project(organization_id=org.id, code="CC-1", name="Concurrency")
        user = User(email="reporter@concurrency.test", full_name="Reporter", password_hash="x")
        db.add_all([project, user])
        db.commit()
        ids = (org.id, project.id, user.id)

    workers = 8
    barrier = Barrier(workers)

    def report(n: int) -> str:
        with Session(pg_engine) as db:
            barrier.wait()
            inc = incidents.create(
                db,
                organization_id=ids[0],
                project_id=ids[1],
                reporter_id=ids[2],
                data={
                    "title": f"Concurrent report {n}",
                    "description": "Synthetic report submitted at the same time as others.",
                    "domain": Domain.SAFETY,
                    "severity": Severity.LOW,
                    "occurred_at": datetime.now(UTC),
                },
            )
            db.commit()
            return inc.reference

    with ThreadPoolExecutor(workers) as pool:
        refs = list(pool.map(report, range(workers)))
    assert len(set(refs)) == workers
    with Session(pg_engine) as db:
        assert db.query(Incident).filter(Incident.project_id == ids[1]).count() == workers


def test_audit_trail_is_append_only(pg_engine):
    from sqlalchemy.exc import DBAPIError

    from app.models import AuditEvent

    with Session(pg_engine) as db:
        org = Organization(name="Audit Org")
        db.add(org)
        db.flush()
        db.add(AuditEvent(organization_id=org.id, action="auth.login", entity_type="user", entity_id="u1"))
        db.commit()
    for stmt in ("UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events", "TRUNCATE audit_events"):
        with pytest.raises(DBAPIError, match="append-only"), pg_engine.begin() as conn:
            conn.execute(text(stmt))
