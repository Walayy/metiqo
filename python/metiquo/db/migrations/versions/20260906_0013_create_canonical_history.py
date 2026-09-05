"""Historiser chaque état canonique et ses lignes raw sources.

Revision ID: 20260906_0013
Revises: 20260906_0012
Create Date: 2026-09-06 10:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0013"
down_revision: str | None = "20260906_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORE_SCHEMA = "core"


def upgrade() -> None:
    """Créer les révisions et leurs preuves raw, toutes deux append-only."""

    op.create_table(
        "canonical_entity_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("transformation_version", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correction", sa.Boolean(), nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('game_title', 'competition', 'team', 'player', 'patch', "
            "'game', 'series', 'game_team_stat', 'game_player_stat', 'roster_observation')",
            name="ck_canonical_entity_revisions_entity_type",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_canonical_entity_revisions_revision"),
        sa.CheckConstraint(
            "payload_hash ~ '^[0-9a-f]{64}$'",
            name="ck_canonical_entity_revisions_payload_hash",
        ),
        sa.CheckConstraint(
            "length(trim(transformation_version)) > 0",
            name="ck_canonical_entity_revisions_transformation_version",
        ),
        sa.CheckConstraint(
            "length(trim(quality_status)) > 0",
            name="ck_canonical_entity_revisions_quality_status",
        ),
        sa.CheckConstraint(
            "(revision = 1 AND previous_revision_id IS NULL) "
            "OR (revision > 1 AND previous_revision_id IS NOT NULL)",
            name="ck_canonical_entity_revisions_revision_chain",
        ),
        sa.ForeignKeyConstraint(
            ["previous_revision_id"],
            ["core.canonical_entity_revisions.id"],
            name="fk_cer_previous_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_cer_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["raw.ingestion_runs.id"],
            name="fk_cer_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_canonical_entity_revisions"),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "revision",
            name="uq_canonical_entity_revisions_entity_revision",
        ),
        schema=CORE_SCHEMA,
    )
    op.create_index(
        "ix_core_canonical_entity_revisions_entity",
        "canonical_entity_revisions",
        ["entity_type", "entity_id", "revision"],
        schema=CORE_SCHEMA,
    )
    op.create_table(
        "canonical_entity_sources",
        sa.Column("entity_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_raw_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_natural_key", sa.Text(), nullable=False),
        sa.Column("source_row_hash", sa.String(length=64), nullable=False),
        sa.Column("source_row_revision", sa.Integer(), nullable=False),
        sa.Column("source_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "source_row_hash ~ '^[0-9a-f]{64}$'",
            name="ck_canonical_entity_sources_source_row_hash",
        ),
        sa.CheckConstraint(
            "source_row_revision >= 1",
            name="ck_canonical_entity_sources_source_row_revision",
        ),
        sa.ForeignKeyConstraint(
            ["entity_revision_id"],
            ["core.canonical_entity_revisions.id"],
            name="fk_ces_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_raw_row_id"],
            ["raw.canonical_rows.id"],
            name="fk_ces_raw_row",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_ces_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"],
            ["raw.ingestion_runs.id"],
            name="fk_ces_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "entity_revision_id",
            "source_raw_row_id",
            name="pk_canonical_entity_sources",
        ),
        schema=CORE_SCHEMA,
    )
    op.create_index(
        "ix_core_canonical_entity_sources_raw",
        "canonical_entity_sources",
        ["source_raw_row_id"],
        schema=CORE_SCHEMA,
    )
    op.execute(
        """
        CREATE FUNCTION core.prevent_canonical_history_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'canonical history is append-only';
        END;
        $$
        """
    )
    for table_name in ("canonical_entity_revisions", "canonical_entity_sources"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_prevent_mutation
            BEFORE UPDATE OR DELETE ON core.{table_name}
            FOR EACH ROW EXECUTE FUNCTION core.prevent_canonical_history_mutation()
            """
        )


def downgrade() -> None:
    """Retirer l'historique en supprimant d'abord ses protections."""

    for table_name in ("canonical_entity_sources", "canonical_entity_revisions"):
        op.execute(f"DROP TRIGGER trg_{table_name}_prevent_mutation ON core.{table_name}")
    op.execute("DROP FUNCTION core.prevent_canonical_history_mutation()")
    op.drop_index(
        "ix_core_canonical_entity_sources_raw",
        table_name="canonical_entity_sources",
        schema=CORE_SCHEMA,
    )
    op.drop_table("canonical_entity_sources", schema=CORE_SCHEMA)
    op.drop_index(
        "ix_core_canonical_entity_revisions_entity",
        table_name="canonical_entity_revisions",
        schema=CORE_SCHEMA,
    )
    op.drop_table("canonical_entity_revisions", schema=CORE_SCHEMA)
