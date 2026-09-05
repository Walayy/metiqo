"""Créer les snapshots de features immuables et retraçables.

Revision ID: 20260906_0016
Revises: 20260906_0015
Create Date: 2026-09-06 15:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0016"
down_revision: str | None = "20260906_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FEATURES_SCHEMA = "features"


def upgrade() -> None:
    """Créer la preuve append-only d'un vecteur calculé."""

    op.create_table(
        "feature_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_oe_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_input_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_knowledge_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("definition_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("missingness", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_game_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("target_game_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_revision_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_snapshot_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_games_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("code_commit", sa.String(length=64), nullable=False),
        sa.Column("leakage_checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "rebuild_invalidation_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("vector_hash", sa.String(length=64), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("supersedes_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("team_a_id <> team_b_id", name="distinct_teams"),
        sa.CheckConstraint(
            "max_input_time IS NULL OR max_input_time < cutoff_at",
            name="input_cutoff",
        ),
        sa.CheckConstraint(
            "max_knowledge_time IS NULL OR max_knowledge_time <= cutoff_at",
            name="knowledge_cutoff",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(definition_versions) = 'object'",
            name="definitions_object",
        ),
        sa.CheckConstraint("jsonb_typeof(values) = 'object'", name="values_object"),
        sa.CheckConstraint("jsonb_typeof(missingness) = 'object'", name="missingness_object"),
        sa.CheckConstraint("jsonb_typeof(source_game_ids) = 'array'", name="games_array"),
        sa.CheckConstraint(
            "jsonb_typeof(target_game_ids) = 'array'",
            name="target_games_array",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_revision_ids) = 'array'",
            name="revisions_array",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(source_snapshot_ids) = 'array'",
            name="snapshots_array",
        ),
        sa.CheckConstraint("jsonb_typeof(leakage_checks) = 'object'", name="leakage_object"),
        sa.CheckConstraint(
            "jsonb_typeof(rebuild_invalidation_ids) = 'array'",
            name="rebuild_invalidations_array",
        ),
        sa.CheckConstraint(
            "source_games_fingerprint ~ '^[0-9a-f]{64}$'",
            name="games_fingerprint",
        ),
        sa.CheckConstraint("vector_hash ~ '^[0-9a-f]{64}$'", name="vector_hash"),
        sa.CheckConstraint("snapshot_hash ~ '^[0-9a-f]{64}$'", name="snapshot_hash"),
        sa.CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        sa.CheckConstraint("generation >= 1", name="generation"),
        sa.ForeignKeyConstraint(
            ["feature_set_id"],
            ["features.feature_sets.id"],
            name="fk_feature_snapshots_feature_set",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_snapshot_id"],
            ["features.feature_snapshots.id"],
            name="fk_feature_snapshots_supersedes",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_oe_snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_feature_snapshots_target_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_a_id"],
            ["core.teams.id"],
            name="fk_feature_snapshots_team_a",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_b_id"],
            ["core.teams.id"],
            name="fk_feature_snapshots_team_b",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_feature_snapshots"),
        sa.UniqueConstraint("snapshot_hash", name="uq_feature_snapshots_hash"),
        schema=FEATURES_SCHEMA,
    )
    op.create_index(
        "ix_features_feature_snapshots_event_cutoff",
        "feature_snapshots",
        ["event_id", "cutoff_at"],
        unique=False,
        schema=FEATURES_SCHEMA,
    )
    op.create_index(
        "ix_features_feature_snapshots_teams_cutoff",
        "feature_snapshots",
        ["team_a_id", "team_b_id", "cutoff_at"],
        unique=False,
        schema=FEATURES_SCHEMA,
    )
    op.execute(
        """
        CREATE FUNCTION features.prevent_feature_snapshot_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'feature snapshot is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_feature_snapshots_prevent_mutation
        BEFORE UPDATE OR DELETE ON features.feature_snapshots
        FOR EACH ROW EXECUTE FUNCTION features.prevent_feature_snapshot_mutation()
        """
    )


def downgrade() -> None:
    """Retirer les snapshots après leur protection append-only."""

    op.execute("DROP TRIGGER trg_feature_snapshots_prevent_mutation ON features.feature_snapshots")
    op.execute("DROP FUNCTION features.prevent_feature_snapshot_mutation()")
    op.drop_index(
        "ix_features_feature_snapshots_teams_cutoff",
        table_name="feature_snapshots",
        schema=FEATURES_SCHEMA,
    )
    op.drop_index(
        "ix_features_feature_snapshots_event_cutoff",
        table_name="feature_snapshots",
        schema=FEATURES_SCHEMA,
    )
    op.drop_table("feature_snapshots", schema=FEATURES_SCHEMA)
