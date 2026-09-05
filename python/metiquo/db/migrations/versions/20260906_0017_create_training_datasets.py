"""Créer les datasets d'entraînement versionnés.

Revision ID: 20260906_0017
Revises: 20260906_0016
Create Date: 2026-09-06 17:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0017"
down_revision: str | None = "20260906_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ML_SCHEMA = "ml"


def upgrade() -> None:
    """Créer les manifestes et exemples append-only."""

    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("dataset", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=64), nullable=False),
        sa.Column("feature_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_set_version", sa.String(length=64), nullable=False),
        sa.Column("feature_set_hash", sa.String(length=64), nullable=False),
        sa.Column("label_definition", sa.String(length=128), nullable=False),
        sa.Column("quality_filter", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cutoff_min", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cutoff_max", sa.DateTime(timezone=True), nullable=False),
        sa.Column("competition_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("oe_snapshot_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("exclusions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("example_count", sa.Integer(), nullable=False),
        sa.Column("exclusion_count", sa.Integer(), nullable=False),
        sa.Column("examples_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("code_commit", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("market = 'game_winner'", name="supported_market"),
        sa.CheckConstraint("length(trim(provider)) > 0", name="provider"),
        sa.CheckConstraint("length(trim(dataset)) > 0", name="dataset"),
        sa.CheckConstraint("length(trim(dataset_version)) > 0", name="dataset_version"),
        sa.CheckConstraint("length(trim(label_definition)) > 0", name="label_definition"),
        sa.CheckConstraint(
            "length(trim(feature_set_version)) > 0",
            name="feature_set_version",
        ),
        sa.CheckConstraint("period_end > period_start", name="period"),
        sa.CheckConstraint("cutoff_max >= cutoff_min", name="cutoff_range"),
        sa.CheckConstraint("example_count >= 1", name="example_count"),
        sa.CheckConstraint("exclusion_count >= 0", name="exclusion_count"),
        sa.CheckConstraint(
            "jsonb_typeof(quality_filter) = 'object'",
            name="quality_filter_object",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(competition_ids) = 'array'",
            name="competitions_array",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(oe_snapshot_ids) = 'array'",
            name="snapshots_array",
        ),
        sa.CheckConstraint(
            "jsonb_array_length(oe_snapshot_ids) >= 1",
            name="snapshots_nonempty",
        ),
        sa.CheckConstraint("jsonb_typeof(exclusions) = 'array'", name="exclusions_array"),
        sa.CheckConstraint(
            "jsonb_array_length(exclusions) = exclusion_count",
            name="exclusions_count",
        ),
        sa.CheckConstraint("feature_set_hash ~ '^[0-9a-f]{64}$'", name="feature_set_hash"),
        sa.CheckConstraint(
            "examples_fingerprint ~ '^[0-9a-f]{64}$'",
            name="examples_fingerprint",
        ),
        sa.CheckConstraint("dataset_hash ~ '^[0-9a-f]{64}$'", name="dataset_hash"),
        sa.CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        sa.ForeignKeyConstraint(
            ["feature_set_id"],
            ["features.feature_sets.id"],
            name="fk_ml_datasets_feature_set",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_datasets"),
        sa.UniqueConstraint("dataset_hash", name="uq_ml_datasets_hash"),
        schema=ML_SCHEMA,
    )
    op.create_table(
        "dataset_examples",
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label_team_a_win", sa.Boolean(), nullable=False),
        sa.Column("label_source_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label_source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("position >= 0", name="position"),
        sa.CheckConstraint("team_a_id <> team_b_id", name="distinct_teams"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["ml.datasets.id"],
            name="fk_ml_dataset_examples_dataset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["core.games.id"],
            name="fk_ml_dataset_examples_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["feature_snapshot_id"],
            ["features.feature_snapshots.id"],
            name="fk_ml_dataset_examples_feature_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_a_id"],
            ["core.teams.id"],
            name="fk_ml_dataset_examples_team_a",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_b_id"],
            ["core.teams.id"],
            name="fk_ml_dataset_examples_team_b",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"],
            ["core.competitions.id"],
            name="fk_ml_dataset_examples_competition",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["label_source_revision_id"],
            ["core.canonical_entity_revisions.id"],
            name="fk_ml_dataset_examples_label_revision",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["label_source_snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_ml_dataset_examples_label_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("dataset_id", "position", name="pk_ml_dataset_examples"),
        sa.UniqueConstraint("dataset_id", "event_id", name="uq_dataset_examples_event"),
        sa.UniqueConstraint(
            "dataset_id",
            "feature_snapshot_id",
            name="uq_dataset_examples_feature_snapshot",
        ),
        schema=ML_SCHEMA,
    )
    op.execute(
        """
        CREATE FUNCTION ml.prevent_training_dataset_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'training dataset is append-only';
        END;
        $$
        """
    )
    for table in ("datasets", "dataset_examples"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_prevent_mutation
            BEFORE UPDATE OR DELETE ON ml.{table}
            FOR EACH ROW EXECUTE FUNCTION ml.prevent_training_dataset_mutation()
            """
        )


def downgrade() -> None:
    """Retirer les datasets après leurs protections append-only."""

    for table in ("dataset_examples", "datasets"):
        op.execute(f"DROP TRIGGER trg_{table}_prevent_mutation ON ml.{table}")
    op.execute("DROP FUNCTION ml.prevent_training_dataset_mutation()")
    op.drop_table("dataset_examples", schema=ML_SCHEMA)
    op.drop_table("datasets", schema=ML_SCHEMA)
