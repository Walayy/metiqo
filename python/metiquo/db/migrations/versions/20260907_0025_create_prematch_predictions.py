"""Créer les prédictions pré-match immuables.

Revision ID: 20260907_0025
Revises: 20260907_0024
Create Date: 2026-09-07 05:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260907_0025"
down_revision: str | None = "20260907_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persister chaque inférence avec son snapshot et sa version exacte."""

    op.create_table(
        "prematch_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("calibrator_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uncertainty_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("team_a_probability", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("team_a_low", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("team_a_high", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("team_b_probability", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("team_b_low", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("team_b_high", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("code_commit", sa.String(length=64), nullable=False),
        sa.Column("inference_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("prediction_fingerprint", sa.String(length=64), nullable=False),
        sa.CheckConstraint("market = 'game_winner'", name="supported_market"),
        sa.CheckConstraint("cutoff_at <= predicted_at", name="prediction_after_cutoff"),
        sa.CheckConstraint("team_a_id <> team_b_id", name="distinct_teams"),
        sa.CheckConstraint("team_a_probability >= 0 AND team_a_probability <= 1", name="team_a"),
        sa.CheckConstraint("team_b_probability >= 0 AND team_b_probability <= 1", name="team_b"),
        sa.CheckConstraint("team_a_probability + team_b_probability = 1", name="probability_sum"),
        sa.CheckConstraint("team_a_low + team_b_high = 1", name="lower_complement"),
        sa.CheckConstraint("team_a_high + team_b_low = 1", name="upper_complement"),
        sa.CheckConstraint(
            "team_a_low >= 0 AND team_a_low <= team_a_probability", name="team_a_lower"
        ),
        sa.CheckConstraint(
            "team_a_high >= team_a_probability AND team_a_high <= 1", name="team_a_upper"
        ),
        sa.CheckConstraint(
            "team_b_low >= 0 AND team_b_low <= team_b_probability", name="team_b_lower"
        ),
        sa.CheckConstraint(
            "team_b_high >= team_b_probability AND team_b_high <= 1", name="team_b_upper"
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
        sa.CheckConstraint("jsonb_typeof(reason_codes) = 'array'", name="reasons_array"),
        sa.CheckConstraint(
            "(enabled AND jsonb_array_length(reason_codes) = 0) OR "
            "(NOT enabled AND jsonb_array_length(reason_codes) >= 1)",
            name="enabled_reasons",
        ),
        sa.CheckConstraint("code_commit ~ '^[0-9a-f]{7,64}$'", name="code_commit"),
        sa.CheckConstraint("inference_fingerprint ~ '^[0-9a-f]{64}$'", name="inference_hash"),
        sa.CheckConstraint("prediction_fingerprint ~ '^[0-9a-f]{64}$'", name="prediction_hash"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["core.games.id"],
            name="fk_ml_prematch_predictions_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_a_id"],
            ["core.teams.id"],
            name="fk_ml_prematch_predictions_team_a",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_b_id"],
            ["core.teams.id"],
            name="fk_ml_prematch_predictions_team_b",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["feature_snapshot_id"],
            ["features.feature_snapshots.id"],
            name="fk_ml_prematch_predictions_feature_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["ml.model_versions.id"],
            name="fk_ml_prematch_predictions_model",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["calibrator_artifact_id"],
            ["ml.calibrator_artifacts.id"],
            name="fk_ml_prematch_predictions_calibrator",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_prematch_predictions"),
        sa.UniqueConstraint(
            "prediction_fingerprint", name="uq_ml_prematch_predictions_fingerprint"
        ),
        schema="ml",
    )
    op.create_index(
        "ix_ml_prematch_predictions_event_predicted",
        "prematch_predictions",
        ["event_id", "predicted_at"],
        schema="ml",
    )
    op.execute(
        """
        CREATE FUNCTION ml.validate_prematch_prediction()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          event_start timestamptz;
          feature_valid boolean;
          model_valid boolean;
        BEGIN
          SELECT start_at INTO event_start FROM core.games WHERE id = NEW.event_id;
          IF event_start IS NULL OR NEW.cutoff_at >= event_start THEN
            RAISE EXCEPTION 'prematch cutoff must precede event start';
          END IF;
          IF NEW.predicted_at >= event_start THEN
            RAISE EXCEPTION 'prematch prediction must precede event start';
          END IF;
          SELECT EXISTS (
            SELECT 1 FROM features.feature_snapshots
            WHERE id = NEW.feature_snapshot_id
              AND event_id = NEW.event_id
              AND team_a_id = NEW.team_a_id
              AND team_b_id = NEW.team_b_id
              AND cutoff_at = NEW.cutoff_at
          ) INTO feature_valid;
          IF NOT feature_valid THEN
            RAISE EXCEPTION 'feature snapshot does not match prediction context';
          END IF;
          SELECT EXISTS (
            SELECT 1 FROM ml.model_versions
            WHERE id = NEW.model_version_id
              AND status = 'champion'
              AND market = NEW.market
              AND calibrator_artifact_id = NEW.calibrator_artifact_id
              AND uncertainty_artifact_id = NEW.uncertainty_artifact_id
          ) INTO model_valid;
          IF NOT model_valid THEN
            RAISE EXCEPTION 'prediction model is not the matching champion';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION ml.prevent_prematch_prediction_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'prematch predictions are append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_prematch_predictions_validate
        BEFORE INSERT ON ml.prematch_predictions
        FOR EACH ROW EXECUTE FUNCTION ml.validate_prematch_prediction()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_prematch_predictions_prevent_mutation
        BEFORE UPDATE OR DELETE ON ml.prematch_predictions
        FOR EACH ROW EXECUTE FUNCTION ml.prevent_prematch_prediction_mutation()
        """
    )


def downgrade() -> None:
    """Retirer la persistance des prédictions pré-match."""

    op.execute("DROP TRIGGER trg_prematch_predictions_prevent_mutation ON ml.prematch_predictions")
    op.execute("DROP TRIGGER trg_prematch_predictions_validate ON ml.prematch_predictions")
    op.execute("DROP FUNCTION ml.prevent_prematch_prediction_mutation()")
    op.execute("DROP FUNCTION ml.validate_prematch_prediction()")
    op.drop_index(
        "ix_ml_prematch_predictions_event_predicted",
        table_name="prematch_predictions",
        schema="ml",
    )
    op.drop_table("prematch_predictions", schema="ml")
