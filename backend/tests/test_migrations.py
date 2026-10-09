from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app import models  # noqa: F401  (register tables)
from app.core.db import BASELINE_REVISION, MIGRATIONS_DIR, Base, run_migrations


def _engine(tmp_path, name="m.db"):
    return create_engine(f"sqlite:///{tmp_path / name}")


def test_migrations_match_models(tmp_path):
    engine = _engine(tmp_path)
    run_migrations(engine)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models and migrations differ; add a revision: {diff}"


def _config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def test_pilot_database_is_stamped_not_recreated(tmp_path):
    # A pilot database: the baseline schema created without Alembic (no alembic_version table).
    engine = _engine(tmp_path, "legacy.db")
    cfg = _config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, BASELINE_REVISION)
        conn.execute(text("drop table alembic_version"))
        conn.execute(
            text("insert into organizations (id, name, created_at, updated_at) values ('o1', 'Kept', :t, :t)"),
            {"t": "2026-01-01 00:00:00"},
        )
    run_migrations(engine)
    with engine.connect() as conn:
        assert conn.execute(text("select name from organizations")).scalar_one() == "Kept"
        head = ScriptDirectory.from_config(cfg).get_current_head()
        assert conn.execute(text("select version_num from alembic_version")).scalar_one() == head


def test_downgrade_to_base_and_back(tmp_path):
    engine = _engine(tmp_path, "roundtrip.db")
    cfg = _config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
    assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    run_migrations(engine)
    assert "incidents" in inspect(engine).get_table_names()
