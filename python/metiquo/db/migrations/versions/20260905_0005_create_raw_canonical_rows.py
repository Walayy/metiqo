"""Créer le canonique tabulaire Oracle's Elixir.

Revision ID: 20260905_0005
Revises: 20260905_0004
Create Date: 2026-09-05 23:15:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0005"
down_revision: str | None = "20260905_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RAW_SCHEMA = "raw"
SHA256_PATTERN = "^[0-9a-f]{64}$"


def upgrade() -> None:
    """Créer les lignes courantes sans autoriser de suppression implicite."""

    op.create_table(
        "canonical_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("dataset", sa.String(length=128), nullable=False),
        sa.Column("natural_key", sa.Text(), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"row_hash ~ '{SHA256_PATTERN}'", name="ck_canonical_rows_row_hash"),
        sa.CheckConstraint("revision >= 1", name="ck_canonical_rows_revision"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_canonical_rows_source_snapshot_id_snapshots",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["raw.ingestion_runs.id"],
            name="fk_canonical_rows_source_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_canonical_rows"),
        sa.UniqueConstraint(
            "provider",
            "dataset",
            "natural_key",
            name="uq_canonical_rows_natural_key",
        ),
        schema=RAW_SCHEMA,
    )


def downgrade() -> None:
    """Supprimer le canonique tabulaire."""

    op.drop_table("canonical_rows", schema=RAW_SCHEMA)
