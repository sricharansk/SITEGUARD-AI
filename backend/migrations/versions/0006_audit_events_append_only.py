"""audit events append-only

Triggers refuse UPDATE and DELETE on `audit_events` (and TRUNCATE on PostgreSQL), so the audit trail stays
append-only for every database client, not only for the application. No columns change.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-30 18:05:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY_MESSAGE = "audit_events is append-only"


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$ "
            f"BEGIN RAISE EXCEPTION '{APPEND_ONLY_MESSAGE}' USING ERRCODE = 'insufficient_privilege'; END $$"
        )
        op.execute(
            "CREATE TRIGGER audit_events_no_update_or_delete BEFORE UPDATE OR DELETE ON audit_events "
            "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()"
        )
        op.execute(
            "CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events "
            "FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only()"
        )
    else:
        for name, verb in (("audit_events_no_update", "UPDATE"), ("audit_events_no_delete", "DELETE")):
            op.execute(
                f"CREATE TRIGGER {name} BEFORE {verb} ON audit_events "
                f"BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY_MESSAGE}'); END"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit_events")
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_update_or_delete ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS audit_events_append_only()")
    else:
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_update")
        op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete")
