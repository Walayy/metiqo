"""Créer les décisions d'ensemble rating/tabulaire.

Revision ID: 20260906_0021
Revises: 20260906_0020
Create Date: 2026-09-06 21:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0021"
down_revision: str | None = "20260906_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ML_SCHEMA = "ml"


def upgrade() -> None:
    """Persister les poids OOF, la comparaison et la décision d'activation."""

    op.create_table(
        "ensemble_candidate_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benchmark_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("ensemble_version", sa.String(length=64), nullable=False),
        sa.Column("walk_forward_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("candidate_weights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidate_evaluations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selected_rating_weight", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("baseline_run_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decision", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("worst_fold_log_loss", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("prediction_count", sa.Integer(), nullable=False),
        sa.Column("predictions_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("run_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("code_commit", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("market = 'game_winner'", name="supported_market"),
        sa.CheckConstraint("length(trim(ensemble_version)) > 0", name="ensemble_version"),
        sa.CheckConstraint(
            "walk_forward_fingerprint ~ '^[0-9a-f]{64}$'", name="walk_forward_fingerprint"
        ),
        sa.CheckConstraint("jsonb_typeof(candidate_weights) = 'array'", name="weights_array"),
        sa.CheckConstraint("jsonb_array_length(candidate_weights) >= 1", name="weights_nonempty"),
        sa.CheckConstraint(
            "jsonb_typeof(candidate_evaluations) = 'object'", name="candidates_object"
        ),
        sa.CheckConstraint("selected_rating_weight > 0", name="selected_weight_lower"),
        sa.CheckConstraint("selected_rating_weight < 1", name="selected_weight_upper"),
        sa.CheckConstraint("jsonb_typeof(baseline_run_ids) = 'array'", name="baselines_array"),
        sa.CheckConstraint("jsonb_array_length(baseline_run_ids) = 3", name="baselines_count"),
        sa.CheckConstraint("jsonb_typeof(decision) = 'object'", name="decision_object"),
        sa.CheckConstraint("jsonb_typeof(metrics) = 'object'", name="metrics_object"),
        sa.CheckConstraint("worst_fold_log_loss >= 0", name="worst_fold_log_loss"),
        sa.CheckConstraint("prediction_count >= 1", name="prediction_count"),
        sa.CheckConstraint(
            "predictions_fingerprint ~ '^[0-9a-f]{64}$'", name="predictions_fingerprint"
        ),
        sa.CheckConstraint("run_fingerprint ~ '^[0-9a-f]{64}$'", name="run_fingerprint"),
        sa.CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["ml.datasets.id"],
            name="fk_ml_ensemble_candidate_runs_dataset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_run_id"],
            ["ml.tabular_benchmark_runs.id"],
            name="fk_ml_ensemble_candidate_runs_benchmark",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rating_run_id"],
            ["ml.baseline_runs.id"],
            name="fk_ml_ensemble_candidate_runs_rating",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_ensemble_candidate_runs"),
        sa.UniqueConstraint("run_fingerprint", name="uq_ml_ensemble_candidate_runs_fingerprint"),
        schema=ML_SCHEMA,
    )
    op.create_table(
        "ensemble_candidate_predictions",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            ["run_id"],
            ["ml.ensemble_candidate_runs.id"],
            name="fk_ml_ensemble_predictions_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["example_id"],
            ["core.games.id"],
            name="fk_ml_ensemble_predictions_example",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", "position", name="pk_ml_ensemble_predictions"),
        sa.UniqueConstraint("run_id", "example_id", name="uq_ml_ensemble_predictions_example"),
        schema=ML_SCHEMA,
    )
    op.execute(
        """
        CREATE FUNCTION ml.prevent_ensemble_candidate_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'ensemble candidate is append-only';
        END;
        $$
        """
    )
    for table in ("ensemble_candidate_runs", "ensemble_candidate_predictions"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_prevent_mutation
            BEFORE UPDATE OR DELETE ON ml.{table}
            FOR EACH ROW EXECUTE FUNCTION ml.prevent_ensemble_candidate_mutation()
            """
        )


def downgrade() -> None:
    """Retirer les décisions d'ensemble publiées."""

    for table in ("ensemble_candidate_predictions", "ensemble_candidate_runs"):
        op.execute(f"DROP TRIGGER trg_{table}_prevent_mutation ON ml.{table}")
    op.execute("DROP FUNCTION ml.prevent_ensemble_candidate_mutation()")
    op.drop_table("ensemble_candidate_predictions", schema=ML_SCHEMA)
    op.drop_table("ensemble_candidate_runs", schema=ML_SCHEMA)
