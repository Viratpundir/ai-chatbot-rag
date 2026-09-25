"""durable document ingestion status

Revision ID: 20260924_120000
Revises: 20260923_223607
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260924_120000"
down_revision = "20260923_223607"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE document_status_enum ADD VALUE IF NOT EXISTS 'uploaded'")
        op.execute("ALTER TYPE document_status_enum ADD VALUE IF NOT EXISTS 'ready'")
        op.execute("UPDATE documents SET status = 'uploaded' WHERE status = 'pending'")
        op.execute("UPDATE documents SET status = 'ready' WHERE status = 'completed'")

    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("documents")}
    if "processing_started_at" not in columns:
        op.add_column(
            "documents",
            sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "processing_completed_at" not in columns:
        op.add_column(
            "documents",
            sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        )

    if bind.dialect.name != "postgresql":
        op.execute("UPDATE documents SET status = 'uploaded' WHERE status = 'pending'")
        op.execute("UPDATE documents SET status = 'ready' WHERE status = 'completed'")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("documents")}
    if "processing_completed_at" in columns:
        op.drop_column("documents", "processing_completed_at")
    if "processing_started_at" in columns:
        op.drop_column("documents", "processing_started_at")
