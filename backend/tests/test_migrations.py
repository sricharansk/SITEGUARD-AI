"""The Alembic migrations must build exactly the schema in app/models.py."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

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
