from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    return create_engine(url, pool_pre_ping=True, **kwargs)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def configure(url: str) -> None:
    """Rebind the engine (used by tests)."""
    global engine
    engine = _make_engine(url)
    SessionLocal.configure(bind=engine)


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
# Revision that matches the schema the pilot created with metadata.create_all before Alembic was added.
BASELINE_REVISION = "0001"


def run_migrations(target: Engine | None = None) -> None:
    """Upgrade the database to the latest Alembic revision.

    Databases created by the pilot (tables present, no alembic_version) are stamped at the baseline first.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    with (target or engine).begin() as conn:
        cfg.attributes["connection"] = conn
        tables = set(inspect(conn).get_table_names())
        if "organizations" in tables and "alembic_version" not in tables:
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
