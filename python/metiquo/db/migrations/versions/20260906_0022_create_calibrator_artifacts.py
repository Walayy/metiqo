"""Créer les artefacts de calibration OOS.

Revision ID: 20260906_0022
Revises: 20260906_0021
Create Date: 2026-09-06 22:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0022"
down_revision: str | None = "20260906_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persister sélection, paramètres et prédictions calibrées OOS."""

    op.create_table(
        "calibrator_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benchmark_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ensemble_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("calibrator_version", sa.String(length=64), nullable=False),
        sa.Column("walk_forward_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidate_evaluations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("calibration_slope", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("calibration_intercept", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("segment_reports", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("oos_prediction_count", sa.Integer(), nullable=False),
        sa.Column("oos_predictions_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("artifact_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("code_commit", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("market = 'game_winner'", name="supported_market"),
        sa.CheckConstraint("source_kind IN ('tabular', 'ensemble')", name="source_kind"),
        sa.CheckConstraint(
            "(source_kind = 'tabular' AND benchmark_run_id IS NOT NULL "
            "AND ensemble_run_id IS NULL) OR "
            "(source_kind = 'ensemble' AND ensemble_run_id IS NOT NULL)",
            name="source_reference",
        ),
        sa.CheckConstraint("method IN ('platt', 'isotonic')", name="method"),
        sa.CheckConstraint("length(trim(calibrator_version)) > 0", name="calibrator_version"),
        sa.CheckConstraint(
            "walk_forward_fingerprint ~ '^[0-9a-f]{64}$'", name="walk_forward_fingerprint"
        ),
        sa.CheckConstraint("jsonb_typeof(parameters) = 'object'", name="parameters_object"),
        sa.CheckConstraint(
            "jsonb_typeof(candidate_evaluations) = 'object'", name="candidates_object"
        ),
        sa.CheckConstraint("jsonb_typeof(metrics) = 'object'", name="metrics_object"),
        sa.CheckConstraint("jsonb_typeof(segment_reports) = 'array'", name="segments_array"),
        sa.CheckConstraint("oos_prediction_count >= 1", name="prediction_count"),
        sa.CheckConstraint(
            "oos_predictions_fingerprint ~ '^[0-9a-f]{64}$'", name="predictions_fingerprint"
        ),
        sa.CheckConstraint("artifact_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        sa.CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["ml.datasets.id"],
            name="fk_ml_calibrator_artifacts_dataset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_run_id"],
            ["ml.tabular_benchmark_runs.id"],
            name="fk_ml_calibrator_artifacts_benchmark",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ensemble_run_id"],
            ["ml.ensemble_candidate_runs.id"],
            name="fk_ml_calibrator_artifacts_ensemble",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_calibrator_artifacts"),
        sa.UniqueConstraint("artifact_fingerprint", name="uq_ml_calibrator_artifacts_fingerprint"),
        schema="ml",
    )
    op.create_table(
        "calibrator_oos_predictions",
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("example_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fold_index", sa.Integer(), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label", sa.Boolean(), nullable=False),
        sa.Column("probability", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.CheckConstraint("position >= 0", name="position"),
        sa.CheckConstraint("fold_index >= 0", name="fold_index"),
        sa.CheckConstraint("probability >= 0 AND probability <= 1", name="probability"),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["ml.calibrator_artifacts.id"],
            name="fk_ml_calibrator_oos_predictions_artifact",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["example_id"],
            ["core.games.id"],
            name="fk_ml_calibrator_oos_predictions_example",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("artifact_id", "position", name="pk_ml_calibrator_oos_predictions"),
        sa.UniqueConstraint("artifact_id", "example_id", name="uq_ml_calibrator_oos_example"),
        schema="ml",
    )
    op.execute(
        """
        CREATE FUNCTION ml.prevent_calibrator_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'calibrator artifact is append-only';
        END;
        $$
        """
    )
    for table in ("calibrator_artifacts", "calibrator_oos_predictions"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_prevent_mutation
            BEFORE UPDATE OR DELETE ON ml.{table}
            FOR EACH ROW EXECUTE FUNCTION ml.prevent_calibrator_mutation()
            """
        )


def downgrade() -> None:
    """Retirer les artefacts de calibration publiés."""

    for table in ("calibrator_oos_predictions", "calibrator_artifacts"):
        op.execute(f"DROP TRIGGER trg_{table}_prevent_mutation ON ml.{table}")
    op.execute("DROP FUNCTION ml.prevent_calibrator_mutation()")
    op.drop_table("calibrator_oos_predictions", schema="ml")
    op.drop_table("calibrator_artifacts", schema="ml")
