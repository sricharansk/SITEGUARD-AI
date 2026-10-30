import logging
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
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


# backend/migrations, both in the repository and in the image (/srv/backend/migrations).
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def run_migrations(target: Engine | None = None) -> None:
    """Upgrade the database to the latest Alembic revision (same as `alembic upgrade head`)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    with (target or engine).begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


def head_revision() -> str | None:
    """The latest Alembic revision in MIGRATIONS_DIR."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(cfg).get_current_head()


def readiness(db: Session) -> dict[str, dict]:
    """Can this process serve requests: the database answers and its schema is at the latest migration. When the
    schema is created from the models (SITEGUARD_AUTO_CREATE_SCHEMA, local runs and tests) there is no migration to
    compare. Booleans only; the error type goes to the log, never to the (unauthenticated) caller."""
    try:
        db.execute(text("SELECT 1"))
        if get_settings().auto_create_schema:
            return {"database": {"ok": True}, "migrations": {"ok": True, "mode": "auto_create_schema"}}
        current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:
        logging.getLogger("siteguard.ready").warning(
            "database not ready", extra={"extra_fields": {"error_type": type(exc).__name__}}
        )
        return {"database": {"ok": False}, "migrations": {"ok": False}}
    return {"database": {"ok": True}, "migrations": {"ok": current == head_revision(), "mode": "alembic"}}


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
