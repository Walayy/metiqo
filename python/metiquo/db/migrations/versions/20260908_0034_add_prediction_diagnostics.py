"""Conserver les diagnostics nécessaires à la projection des opportunités.

Revision ID: 20260908_0034
Revises: 20260908_0033
Create Date: 2026-09-08 01:30:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_0034"
down_revision: str | None = "20260908_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Ajouter les diagnostics exacts sans inventer ceux des anciennes lignes."""

    op.add_column(
        "prematch_predictions",
        sa.Column("data_coverage", sa.Numeric(precision=9, scale=8), nullable=True),
        schema="ml",
    )
    op.add_column(
        "prematch_predictions",
        sa.Column(
            "out_of_distribution_distance",
            sa.Numeric(precision=20, scale=8),
            nullable=True,
        ),
        schema="ml",
    )
    op.create_check_constraint(
        "ck_prematch_predictions_data_coverage",
        "prematch_predictions",
        "data_coverage IS NULL OR data_coverage BETWEEN 0 AND 1",
        schema="ml",
    )
    op.create_check_constraint(
        "ck_prematch_predictions_out_of_distribution_distance",
        "prematch_predictions",
        "out_of_distribution_distance IS NULL OR out_of_distribution_distance >= 0",
        schema="ml",
    )
    op.execute(_validation_function(require_diagnostics=True))


def downgrade() -> None:
    """Revenir au validateur antérieur avant de retirer les colonnes."""

    op.execute(_validation_function(require_diagnostics=False))
    op.drop_constraint(
        "ck_prematch_predictions_out_of_distribution_distance",
        "prematch_predictions",
        schema="ml",
        type_="check",
    )
    op.drop_constraint(
        "ck_prematch_predictions_data_coverage",
        "prematch_predictions",
        schema="ml",
        type_="check",
    )
    op.drop_column("prematch_predictions", "out_of_distribution_distance", schema="ml")
    op.drop_column("prematch_predictions", "data_coverage", schema="ml")


def _validation_function(*, require_diagnostics: bool) -> str:
    diagnostic_guard = (
        """
          IF NEW.data_coverage IS NULL OR NEW.out_of_distribution_distance IS NULL THEN
            RAISE EXCEPTION 'new prematch predictions require exact diagnostics';
          END IF;
        """
        if require_diagnostics
        else ""
    )
    return f"""
        CREATE OR REPLACE FUNCTION ml.validate_prematch_prediction()
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
          {diagnostic_guard}
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
