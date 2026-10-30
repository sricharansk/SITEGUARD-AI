"""The Alembic migrations must build exactly the schema in app/models.py."""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError

from app.core.db import Base

BACKEND = Path(__file__).resolve().parents[1]


def test_migrations_match_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'migr.db'}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    with create_engine(url).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"Model changes without a migration: {diff}"
    command.downgrade(cfg, "base")


def test_migrated_audit_trail_is_append_only(tmp_path):
    url = f"sqlite:///{tmp_path / 'audit.db'}"
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_events (id, organization_id, actor_type, action, entity_type, entity_id, details, "
                "created_at) VALUES ('e1', 'o1', 'USER', 'auth.login', 'user', 'u1', '{}', CURRENT_TIMESTAMP)"
            )
        )
    for stmt in ("UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events"):
        with pytest.raises(DatabaseError, match="append-only"), engine.begin() as conn:
            conn.execute(text(stmt))
    with engine.connect() as conn:
        assert conn.execute(text("SELECT action FROM audit_events")).scalars().all() == ["auth.login"]
    engine.dispose()
    command.downgrade(cfg, "0005")
    with create_engine(url).begin() as conn:
        conn.execute(text("DELETE FROM audit_events"))
