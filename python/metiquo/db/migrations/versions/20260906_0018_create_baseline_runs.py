"""Créer les runs de baselines OOF comparables.

Revision ID: 20260906_0018
Revises: 20260906_0017
Create Date: 2026-09-06 18:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0018"
down_revision: str | None = "20260906_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ML_SCHEMA = "ml"


def upgrade() -> None:
    """Publier les métriques et probabilités OOF sans mutation ultérieure."""

    op.create_table(
        "baseline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("baseline_name", sa.String(length=64), nullable=False),
        sa.Column("baseline_version", sa.String(length=64), nullable=False),
        sa.Column("evaluation_split", sa.String(length=32), nullable=False),
        sa.Column("walk_forward_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prediction_count", sa.Integer(), nullable=False),
        sa.Column("predictions_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("run_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("code_commit", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("market = 'game_winner'", name="supported_market"),
        sa.CheckConstraint(
            "baseline_name IN ('competition_prior', 'recent_form')",
            name="supported_baseline",
        ),
        sa.CheckConstraint("length(trim(baseline_version)) > 0", name="baseline_version"),
        sa.CheckConstraint("evaluation_split = 'oof_validation'", name="evaluation_split"),
        sa.CheckConstraint(
            "walk_forward_fingerprint ~ '^[0-9a-f]{64}$'",
            name="walk_forward_fingerprint",
        ),
        sa.CheckConstraint("jsonb_typeof(parameters) = 'object'", name="parameters_object"),
        sa.CheckConstraint("jsonb_typeof(metrics) = 'object'", name="metrics_object"),
        sa.CheckConstraint("prediction_count >= 1", name="prediction_count"),
        sa.CheckConstraint(
            "predictions_fingerprint ~ '^[0-9a-f]{64}$'",
            name="predictions_fingerprint",
        ),
        sa.CheckConstraint("run_fingerprint ~ '^[0-9a-f]{64}$'", name="run_fingerprint"),
        sa.CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["ml.datasets.id"],
            name="fk_ml_baseline_runs_dataset",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_baseline_runs"),
        sa.UniqueConstraint("run_fingerprint", name="uq_ml_baseline_runs_fingerprint"),
        schema=ML_SCHEMA,
    )
    op.create_table(
        "baseline_predictions",
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
            ["ml.baseline_runs.id"],
            name="fk_ml_baseline_predictions_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["example_id"],
            ["core.games.id"],
            name="fk_ml_baseline_predictions_example",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("run_id", "position", name="pk_ml_baseline_predictions"),
        sa.UniqueConstraint(
            "run_id",
            "example_id",
            name="uq_baseline_predictions_example",
        ),
        schema=ML_SCHEMA,
    )
    op.execute(
        """
        CREATE FUNCTION ml.prevent_baseline_run_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'published baseline run is append-only';
        END;
        $$
        """
    )
    for table in ("baseline_runs", "baseline_predictions"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_prevent_mutation
            BEFORE UPDATE OR DELETE ON ml.{table}
            FOR EACH ROW EXECUTE FUNCTION ml.prevent_baseline_run_mutation()
            """
        )


def downgrade() -> None:
    """Retirer les runs après leurs protections append-only."""

    for table in ("baseline_predictions", "baseline_runs"):
        op.execute(f"DROP TRIGGER trg_{table}_prevent_mutation ON ml.{table}")
    op.execute("DROP FUNCTION ml.prevent_baseline_run_mutation()")
    op.drop_table("baseline_predictions", schema=ML_SCHEMA)
    op.drop_table("baseline_runs", schema=ML_SCHEMA)
