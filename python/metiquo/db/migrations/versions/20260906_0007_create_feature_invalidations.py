"""Créer les événements immuables d'invalidation de features.

Revision ID: 20260906_0007
Revises: 20260906_0006
Create Date: 2026-09-06 00:35:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0007"
down_revision: str | None = "20260906_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FEATURES_SCHEMA = "features"


def upgrade() -> None:
    """Créer une file append-only dérivée des révisions raw."""

    op.create_table(
        "invalidations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("dataset", sa.String(length=128), nullable=False),
        sa.Column("affected_from", sa.Date(), nullable=False),
        sa.Column("changed_through", sa.Date(), nullable=False),
        sa.Column("revision_count", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "changed_through >= affected_from",
            name="ck_invalidations_date_range",
        ),
        sa.CheckConstraint("revision_count >= 1", name="ck_invalidations_revision_count"),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["raw.ingestion_runs.id"],
            name="fk_invalidations_source_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_invalidations_source_snapshot_id_snapshots",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_invalidations"),
        sa.UniqueConstraint("source_run_id", name="uq_invalidations_source_run_id"),
        schema=FEATURES_SCHEMA,
    )
    op.create_index(
        "ix_invalidations_affected_from",
        "invalidations",
        ["affected_from"],
        schema=FEATURES_SCHEMA,
    )
    op.execute(
        """
        CREATE FUNCTION features.prevent_invalidation_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'feature invalidation % is append-only', OLD.id
            USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_invalidations_prevent_mutation
        BEFORE UPDATE OR DELETE ON features.invalidations
        FOR EACH ROW EXECUTE FUNCTION features.prevent_invalidation_mutation()
        """
    )


def downgrade() -> None:
    """Supprimer la file d'invalidation."""

    op.execute("DROP TRIGGER trg_invalidations_prevent_mutation ON features.invalidations")
    op.execute("DROP FUNCTION features.prevent_invalidation_mutation()")
    op.drop_index(
        "ix_invalidations_affected_from",
        table_name="invalidations",
        schema=FEATURES_SCHEMA,
    )
    op.drop_table("invalidations", schema=FEATURES_SCHEMA)
