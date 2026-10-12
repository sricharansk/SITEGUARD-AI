"""notification email delivery outbox

Notifications created before this revision get no delivery row: they were in-app only, and sending them now would
email people about old events.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12 15:02:25.375385
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("notification_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SENT", "FAILED", "SKIPPED", name="deliverystatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", "channel"),
    )
    with op.batch_alter_table("notification_deliveries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notification_deliveries_notification_id"), ["notification_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_notification_deliveries_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("notification_deliveries", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notification_deliveries_status"))
        batch_op.drop_index(batch_op.f("ix_notification_deliveries_notification_id"))

    op.drop_table("notification_deliveries")
