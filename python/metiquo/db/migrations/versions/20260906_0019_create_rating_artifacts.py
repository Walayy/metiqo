"""Créer les artefacts de baseline rating.

Revision ID: 20260906_0019
Revises: 20260906_0018
Create Date: 2026-09-06 19:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0019"
down_revision: str | None = "20260906_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ML_SCHEMA = "ml"


def upgrade() -> None:
    """Versionner la conversion rating-probabilité choisie sur OOF."""

    op.create_table(
        "rating_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("artifact_version", sa.String(length=64), nullable=False),
        sa.Column("walk_forward_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("rating_feature", sa.String(length=128), nullable=False),
        sa.Column("selected_scale", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("candidate_scales", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selection_metric", sa.String(length=32), nullable=False),
        sa.Column("selection_scope", sa.String(length=32), nullable=False),
        sa.Column("candidate_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifact_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("code_commit", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("market = 'game_winner'", name="supported_market"),
        sa.CheckConstraint("length(trim(artifact_version)) > 0", name="artifact_version"),
        sa.CheckConstraint(
            "walk_forward_fingerprint ~ '^[0-9a-f]{64}$'",
            name="walk_forward_fingerprint",
        ),
        sa.CheckConstraint("rating_feature = 'rating.difference'", name="rating_feature"),
        sa.CheckConstraint("selected_scale > 0", name="selected_scale"),
        sa.CheckConstraint("jsonb_typeof(candidate_scales) = 'array'", name="scales_array"),
        sa.CheckConstraint(
            "jsonb_array_length(candidate_scales) >= 1",
            name="scales_nonempty",
        ),
        sa.CheckConstraint("selection_metric = 'log_loss'", name="selection_metric"),
        sa.CheckConstraint("selection_scope = 'oof_validation'", name="selection_scope"),
        sa.CheckConstraint(
            "jsonb_typeof(candidate_metrics) = 'object'",
            name="candidate_metrics_object",
        ),
        sa.CheckConstraint("artifact_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        sa.CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["ml.datasets.id"],
            name="fk_ml_rating_artifacts_dataset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_rating_artifacts"),
        sa.UniqueConstraint(
            "artifact_fingerprint",
            name="uq_ml_rating_artifacts_fingerprint",
        ),
        schema=ML_SCHEMA,
    )
    op.drop_constraint(
        op.f("ck_baseline_runs_supported_baseline"),
        "baseline_runs",
        schema=ML_SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_baseline_runs_supported_baseline"),
        "baseline_runs",
        "baseline_name IN ('competition_prior', 'recent_form', 'rating')",
        schema=ML_SCHEMA,
    )
    op.add_column(
        "baseline_runs",
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=ML_SCHEMA,
    )
    op.create_foreign_key(
        "fk_ml_baseline_runs_artifact",
        "baseline_runs",
        "rating_artifacts",
        ["artifact_id"],
        ["id"],
        source_schema=ML_SCHEMA,
        referent_schema=ML_SCHEMA,
        ondelete="RESTRICT",
    )
    op.execute(
        """
        CREATE FUNCTION ml.prevent_rating_artifact_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'rating artifact is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_rating_artifacts_prevent_mutation
        BEFORE UPDATE OR DELETE ON ml.rating_artifacts
        FOR EACH ROW EXECUTE FUNCTION ml.prevent_rating_artifact_mutation()
        """
    )


def downgrade() -> None:
    """Retirer les artefacts et restaurer les deux baselines précédentes."""

    op.execute("DROP TRIGGER trg_rating_artifacts_prevent_mutation ON ml.rating_artifacts")
    op.execute("DROP FUNCTION ml.prevent_rating_artifact_mutation()")
    op.execute(
        "ALTER TABLE ml.baseline_predictions "
        "DISABLE TRIGGER trg_baseline_predictions_prevent_mutation"
    )
    op.execute(
        """
        DELETE FROM ml.baseline_predictions
        WHERE run_id IN (
          SELECT id FROM ml.baseline_runs WHERE baseline_name = 'rating'
        )
        """
    )
    op.execute(
        "ALTER TABLE ml.baseline_predictions "
        "ENABLE TRIGGER trg_baseline_predictions_prevent_mutation"
    )
    op.execute("ALTER TABLE ml.baseline_runs DISABLE TRIGGER trg_baseline_runs_prevent_mutation")
    op.execute("DELETE FROM ml.baseline_runs WHERE baseline_name = 'rating'")
    op.execute("ALTER TABLE ml.baseline_runs ENABLE TRIGGER trg_baseline_runs_prevent_mutation")
    op.drop_constraint(
        "fk_ml_baseline_runs_artifact",
        "baseline_runs",
        schema=ML_SCHEMA,
        type_="foreignkey",
    )
    op.drop_column("baseline_runs", "artifact_id", schema=ML_SCHEMA)
    op.drop_constraint(
        op.f("ck_baseline_runs_supported_baseline"),
        "baseline_runs",
        schema=ML_SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_baseline_runs_supported_baseline"),
        "baseline_runs",
        "baseline_name IN ('competition_prior', 'recent_form')",
        schema=ML_SCHEMA,
    )
    op.drop_table("rating_artifacts", schema=ML_SCHEMA)
