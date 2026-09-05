"""Créer les benchmarks tabulaires OOF.

Revision ID: 20260906_0020
Revises: 20260906_0019
Create Date: 2026-09-06 20:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0020"
down_revision: str | None = "20260906_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ML_SCHEMA = "ml"


def upgrade() -> None:
    """Persister sélection, métriques, paramètres et probabilités candidates."""

    op.create_table(
        "tabular_benchmark_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("benchmark_version", sa.String(length=64), nullable=False),
        sa.Column("walk_forward_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("feature_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidate_evaluations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("selected_candidate", sa.String(length=64), nullable=False),
        sa.Column("baseline_run_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("promotion_gate", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("promotable", sa.Boolean(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("predictions_per_candidate", sa.Integer(), nullable=False),
        sa.Column("predictions_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("run_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("code_commit", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("market = 'game_winner'", name="supported_market"),
        sa.CheckConstraint("length(trim(benchmark_version)) > 0", name="benchmark_version"),
        sa.CheckConstraint(
            "walk_forward_fingerprint ~ '^[0-9a-f]{64}$'", name="walk_forward_fingerprint"
        ),
        sa.CheckConstraint("jsonb_typeof(feature_spec) = 'object'", name="feature_spec_object"),
        sa.CheckConstraint(
            "jsonb_typeof(candidate_evaluations) = 'object'", name="candidates_object"
        ),
        sa.CheckConstraint("candidate_count >= 2", name="candidate_count"),
        sa.CheckConstraint(
            "selected_candidate IN ('gradient_boosting', 'hist_gradient_boosting')",
            name="selected_candidate",
        ),
        sa.CheckConstraint("jsonb_typeof(baseline_run_ids) = 'array'", name="baselines_array"),
        sa.CheckConstraint("jsonb_array_length(baseline_run_ids) = 3", name="baselines_count"),
        sa.CheckConstraint("jsonb_typeof(promotion_gate) = 'object'", name="gate_object"),
        sa.CheckConstraint("seed >= 0", name="seed"),
        sa.CheckConstraint("predictions_per_candidate >= 1", name="prediction_count"),
        sa.CheckConstraint(
            "predictions_fingerprint ~ '^[0-9a-f]{64}$'", name="predictions_fingerprint"
        ),
        sa.CheckConstraint("run_fingerprint ~ '^[0-9a-f]{64}$'", name="run_fingerprint"),
        sa.CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["ml.datasets.id"],
            name="fk_ml_tabular_benchmark_runs_dataset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_tabular_benchmark_runs"),
        sa.UniqueConstraint("run_fingerprint", name="uq_ml_tabular_benchmark_runs_fingerprint"),
        schema=ML_SCHEMA,
    )
    op.create_table(
        "tabular_benchmark_predictions",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_name", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("example_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fold_index", sa.Integer(), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label", sa.Boolean(), nullable=False),
        sa.Column("probability", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.CheckConstraint(
            "candidate_name IN ('gradient_boosting', 'hist_gradient_boosting')",
            name="candidate_name",
        ),
        sa.CheckConstraint("position >= 0", name="position"),
        sa.CheckConstraint("fold_index >= 0", name="fold_index"),
        sa.CheckConstraint("probability >= 0 AND probability <= 1", name="probability"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ml.tabular_benchmark_runs.id"],
            name="fk_ml_tabular_benchmark_predictions_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["example_id"],
            ["core.games.id"],
            name="fk_ml_tabular_benchmark_predictions_example",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "run_id", "candidate_name", "position", name="pk_ml_tabular_benchmark_predictions"
        ),
        sa.UniqueConstraint(
            "run_id",
            "candidate_name",
            "example_id",
            name="uq_tabular_benchmark_predictions_example",
        ),
        schema=ML_SCHEMA,
    )
    op.execute(
        """
        CREATE FUNCTION ml.prevent_tabular_benchmark_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'tabular benchmark is append-only';
        END;
        $$
        """
    )
    for table in ("tabular_benchmark_runs", "tabular_benchmark_predictions"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_prevent_mutation
            BEFORE UPDATE OR DELETE ON ml.{table}
            FOR EACH ROW EXECUTE FUNCTION ml.prevent_tabular_benchmark_mutation()
            """
        )


def downgrade() -> None:
    """Retirer les benchmarks publiés avec leurs protections."""

    for table in ("tabular_benchmark_predictions", "tabular_benchmark_runs"):
        op.execute(f"DROP TRIGGER trg_{table}_prevent_mutation ON ml.{table}")
    op.execute("DROP FUNCTION ml.prevent_tabular_benchmark_mutation()")
    op.drop_table("tabular_benchmark_predictions", schema=ML_SCHEMA)
    op.drop_table("tabular_benchmark_runs", schema=ML_SCHEMA)
