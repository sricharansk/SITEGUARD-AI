"""document processing, chunk provenance and embeddings

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09 02:33:20.733738
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("vector", sa.JSON().with_variant(Vector(), "postgresql"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id", "model", "model_version"),
    )
    with op.batch_alter_table("chunk_embeddings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_chunk_embeddings_chunk_id"), ["chunk_id"], unique=False)

    with op.batch_alter_table("document_chunks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("page", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("content_sha256", sa.String(length=64), nullable=True))

    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.Enum("PENDING", "PROCESSING", "READY", "FAILED", name="documentstatus", native_enum=False),
                server_default="READY",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("file_name", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("content_type", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("size_bytes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("storage_key", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("page_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("parser", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("effective_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("tags", sa.JSON(), server_default="[]", nullable=False))
        batch_op.add_column(sa.Column("uploaded_by", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key("fk_documents_uploaded_by_users", "users", ["uploaded_by"], ["id"])

    # Existing chunks get their content checksum so embedding stays idempotent.
    bind = op.get_bind()
    chunks = sa.table(
        "document_chunks",
        sa.column("id", sa.String),
        sa.column("text", sa.Text),
        sa.column("content_sha256", sa.String),
    )
    for chunk_id, text in bind.execute(sa.select(chunks.c.id, chunks.c.text)).all():
        bind.execute(
            chunks.update()
            .where(chunks.c.id == chunk_id)
            .values(content_sha256=hashlib.sha256(text.encode()).hexdigest())
        )


def downgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_constraint("fk_documents_uploaded_by_users", type_="foreignkey")
        batch_op.drop_column("processed_at")
        batch_op.drop_column("uploaded_by")
        batch_op.drop_column("tags")
        batch_op.drop_column("effective_date")
        batch_op.drop_column("parser")
        batch_op.drop_column("page_count")
        batch_op.drop_column("storage_key")
        batch_op.drop_column("size_bytes")
        batch_op.drop_column("content_type")
        batch_op.drop_column("file_name")
        batch_op.drop_column("error")
        batch_op.drop_column("status")

    with op.batch_alter_table("document_chunks", schema=None) as batch_op:
        batch_op.drop_column("content_sha256")
        batch_op.drop_column("page")

    with op.batch_alter_table("chunk_embeddings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chunk_embeddings_chunk_id"))

    op.drop_table("chunk_embeddings")
