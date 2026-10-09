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
