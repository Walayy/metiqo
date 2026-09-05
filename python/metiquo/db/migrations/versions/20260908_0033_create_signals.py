"""Créer les signaux de value append-only.

Revision ID: 20260908_0033
Revises: 20260907_0032
Create Date: 2026-09-08 00:30:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260908_0033"
down_revision: str | None = "20260907_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Conserver chaque décision avec ses entrées exactes."""

    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("odds_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prediction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_mapping_attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("selection_type", sa.String(length=16), nullable=False),
        sa.Column("offered_odds", sa.Numeric(precision=38, scale=28), nullable=False),
        sa.Column(
            "raw_implied_probability",
            sa.Numeric(precision=38, scale=28),
            nullable=False,
        ),
        sa.Column("model_probability", sa.Numeric(precision=38, scale=28), nullable=False),
        sa.Column("model_probability_low", sa.Numeric(precision=38, scale=28), nullable=False),
        sa.Column("model_probability_high", sa.Numeric(precision=38, scale=28), nullable=False),
        sa.Column("value_computed", sa.Boolean(), nullable=False),
        sa.Column("pricing_policy_version", sa.String(length=128), nullable=True),
        sa.Column("no_vig_policy_version", sa.String(length=128), nullable=True),
        sa.Column("no_vig_probability", sa.Numeric(precision=38, scale=28), nullable=True),
        sa.Column("fair_odds", sa.Numeric(precision=38, scale=28), nullable=True),
        sa.Column("edge", sa.Numeric(precision=38, scale=28), nullable=True),
        sa.Column("expected_value", sa.Numeric(precision=38, scale=28), nullable=True),
        sa.Column(
            "conservative_expected_value",
            sa.Numeric(precision=38, scale=28),
            nullable=True,
        ),
        sa.Column("grade", sa.String(length=16), nullable=False),
        sa.Column(
            "abstention_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("mapping_confidence", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("source_freshness", sa.String(length=16), nullable=False),
        sa.Column("odds_age_seconds", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_fingerprint", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "selection_type IN ('TEAM_A', 'TEAM_B')",
            name="ck_signals_selection_type",
        ),
        sa.CheckConstraint("offered_odds >= 1", name="ck_signals_offered_odds"),
        sa.CheckConstraint(
            "raw_implied_probability BETWEEN 0 AND 1",
            name="ck_signals_raw_implied_probability",
        ),
        sa.CheckConstraint(
            "model_probability_low BETWEEN 0 AND model_probability",
            name="ck_signals_model_probability_low",
        ),
        sa.CheckConstraint(
            "model_probability_high BETWEEN model_probability AND 1",
            name="ck_signals_model_probability_high",
        ),
        sa.CheckConstraint(
            "grade IN ('VALUE', 'STRONG_VALUE', 'WATCH', 'NO_EDGE', 'BLOCKED')",
            name="ck_signals_grade",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(abstention_reasons) = 'array'",
            name="ck_signals_reasons_array",
        ),
        sa.CheckConstraint(
            "(grade IN ('VALUE', 'STRONG_VALUE', 'WATCH') "
            "AND jsonb_array_length(abstention_reasons) = 0) OR "
            "(grade IN ('NO_EDGE', 'BLOCKED') "
            "AND jsonb_array_length(abstention_reasons) >= 1)",
            name="ck_signals_grade_reasons",
        ),
        sa.CheckConstraint(
            "(value_computed AND pricing_policy_version IS NOT NULL "
            "AND no_vig_policy_version IS NOT NULL AND no_vig_probability IS NOT NULL "
            "AND edge IS NOT NULL AND expected_value IS NOT NULL "
            "AND conservative_expected_value IS NOT NULL) OR "
            "(NOT value_computed AND pricing_policy_version IS NULL "
            "AND no_vig_policy_version IS NULL AND no_vig_probability IS NULL "
            "AND fair_odds IS NULL AND edge IS NULL AND expected_value IS NULL "
            "AND conservative_expected_value IS NULL)",
            name="ck_signals_value_state",
        ),
        sa.CheckConstraint(
            "NOT value_computed OR ((model_probability = 0 AND fair_odds IS NULL) OR "
            "(model_probability > 0 AND fair_odds >= 1))",
            name="ck_signals_fair_odds",
        ),
        sa.CheckConstraint(
            "no_vig_probability IS NULL OR no_vig_probability BETWEEN 0 AND 1",
            name="ck_signals_no_vig_probability",
        ),
        sa.CheckConstraint("edge IS NULL OR edge BETWEEN -1 AND 1", name="ck_signals_edge"),
        sa.CheckConstraint(
            "expected_value IS NULL OR expected_value >= -1",
            name="ck_signals_expected_value",
        ),
        sa.CheckConstraint(
            "conservative_expected_value IS NULL OR conservative_expected_value >= -1",
            name="ck_signals_conservative_expected_value",
        ),
        sa.CheckConstraint(
            "grade <> 'NO_EDGE' OR value_computed",
            name="ck_signals_no_edge_has_value",
        ),
        sa.CheckConstraint(
            "mapping_confidence BETWEEN 0 AND 1",
            name="ck_signals_mapping_confidence",
        ),
        sa.CheckConstraint("odds_age_seconds >= 0", name="ck_signals_odds_age_seconds"),
        sa.CheckConstraint(
            "source_freshness IN ('fresh', 'stale', 'degraded', 'failed', 'quarantined')",
            name="ck_signals_source_freshness",
        ),
        sa.CheckConstraint(
            "signal_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_signals_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["odds_snapshot_id"],
            ["odds.snapshots.id"],
            name="fk_signals_odds_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["prediction_id"],
            ["ml.prematch_predictions.id"],
            name="fk_signals_prediction",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_mapping_attempt_id"],
            ["odds.event_mapping_attempts.id"],
            name="fk_signals_event_mapping_attempt",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_version"],
            ["signals.value_policies.version"],
            name="fk_signals_policy_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_signals_signals"),
        sa.UniqueConstraint(
            "signal_fingerprint",
            name="uq_signals_signals_fingerprint",
        ),
        schema="signals",
    )
    op.create_index(
        "ix_signals_signals_prediction_computed",
        "signals",
        ["prediction_id", "computed_at"],
        schema="signals",
    )
    op.create_index(
        "ix_signals_signals_odds_computed",
        "signals",
        ["odds_snapshot_id", "computed_at"],
        schema="signals",
    )
    op.execute(
        """
        CREATE FUNCTION signals.validate_signal_sources()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          snapshot_odds numeric;
          snapshot_captured timestamptz;
          snapshot_reliable boolean;
          snapshot_informational boolean;
          snapshot_selection text;
          snapshot_event uuid;
          prediction_event uuid;
          prediction_time timestamptz;
          prediction_enabled boolean;
          prediction_probability numeric;
          prediction_low numeric;
          prediction_high numeric;
          event_start timestamptz;
          mapping_provider_event uuid;
          mapping_status text;
          mapping_event uuid;
          mapping_score numeric;
          mapping_inverted boolean;
          mapping_evaluated timestamptz;
        BEGIN
          SELECT s.decimal_odds, s.captured_at, s.timestamp_reliable, s.informational_only,
                 sel.selection_type, s.event_id
          INTO snapshot_odds, snapshot_captured, snapshot_reliable,
               snapshot_informational, snapshot_selection, snapshot_event
          FROM odds.snapshots s
          JOIN odds.selections sel ON sel.id = s.selection_id
          WHERE s.id = NEW.odds_snapshot_id;
          IF snapshot_captured IS NULL OR NOT snapshot_reliable THEN
            RAISE EXCEPTION 'signal odds snapshot must have a reliable timestamp';
          END IF;
          IF snapshot_odds <> NEW.offered_odds THEN
            RAISE EXCEPTION 'signal odds snapshot does not match stored inputs';
          END IF;

          SELECT a.provider_event_id, a.result_status,
                 COALESCE(a.selected_event_id, r.selected_event_id),
                 COALESCE(c.total_score, a.top_score),
                 COALESCE(c.selections_inverted, a.selections_inverted),
                 COALESCE(r.reviewed_at, a.evaluated_at)
          INTO mapping_provider_event, mapping_status, mapping_event,
               mapping_score, mapping_inverted, mapping_evaluated
          FROM odds.event_mapping_attempts a
          LEFT JOIN odds.mapping_reviews r
            ON r.attempt_id = a.id AND r.status = 'approved'
          LEFT JOIN odds.event_mapping_candidate_scores c
            ON c.attempt_id = a.id
           AND c.canonical_event_id = COALESCE(a.selected_event_id, r.selected_event_id)
          WHERE a.id = NEW.event_mapping_attempt_id;
          IF mapping_provider_event IS NULL
             OR mapping_provider_event <> snapshot_event
             OR (mapping_status <> 'auto_matched' AND mapping_event IS NULL) THEN
            RAISE EXCEPTION 'signal event mapping is not resolved for the odds snapshot';
          END IF;
          IF mapping_score <> NEW.mapping_confidence THEN
            RAISE EXCEPTION 'signal mapping confidence does not match stored input';
          END IF;
          IF mapping_evaluated IS NULL OR mapping_evaluated > NEW.computed_at THEN
            RAISE EXCEPTION 'signal cannot precede its event mapping';
          END IF;
          IF mapping_inverted THEN
            snapshot_selection := CASE snapshot_selection
              WHEN 'TEAM_A' THEN 'TEAM_B'
              WHEN 'TEAM_B' THEN 'TEAM_A'
              ELSE snapshot_selection
            END;
          END IF;
          IF snapshot_selection <> NEW.selection_type THEN
            RAISE EXCEPTION 'signal mapped selection does not match stored input';
          END IF;

          SELECT p.event_id, p.predicted_at, p.enabled,
                 CASE WHEN NEW.selection_type = 'TEAM_A'
                      THEN p.team_a_probability ELSE p.team_b_probability END,
                 CASE WHEN NEW.selection_type = 'TEAM_A'
                      THEN p.team_a_low ELSE p.team_b_low END,
                 CASE WHEN NEW.selection_type = 'TEAM_A'
                      THEN p.team_a_high ELSE p.team_b_high END
          INTO prediction_event, prediction_time, prediction_enabled,
               prediction_probability, prediction_low, prediction_high
          FROM ml.prematch_predictions p
          WHERE p.id = NEW.prediction_id;
          IF prediction_event IS NULL OR prediction_event <> mapping_event THEN
            RAISE EXCEPTION 'signal prediction does not match mapped event';
          END IF;
          IF prediction_probability <> NEW.model_probability
             OR prediction_low <> NEW.model_probability_low
             OR prediction_high <> NEW.model_probability_high THEN
            RAISE EXCEPTION 'signal prediction does not match stored inputs';
          END IF;

          SELECT start_at INTO event_start FROM core.games WHERE id = prediction_event;
          IF NEW.computed_at < snapshot_captured OR NEW.computed_at < prediction_time THEN
            RAISE EXCEPTION 'signal cannot precede its inputs';
          END IF;
          IF event_start IS NULL OR NEW.computed_at >= event_start THEN
            RAISE EXCEPTION 'signal must be computed before event start';
          END IF;
          IF NEW.grade IN ('VALUE', 'STRONG_VALUE', 'WATCH') AND NOT prediction_enabled THEN
            RAISE EXCEPTION 'admitted signal requires an enabled prediction';
          END IF;
          IF snapshot_informational AND NEW.grade <> 'BLOCKED' THEN
            RAISE EXCEPTION 'informational odds can only produce a blocked signal';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION signals.prevent_signal_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'signals are append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_signals_validate_sources
        BEFORE INSERT ON signals.signals
        FOR EACH ROW EXECUTE FUNCTION signals.validate_signal_sources()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_signals_prevent_mutation
        BEFORE UPDATE OR DELETE ON signals.signals
        FOR EACH ROW EXECUTE FUNCTION signals.prevent_signal_mutation()
        """
    )


def downgrade() -> None:
    """Retirer les signaux et leurs protections."""

    op.execute("DROP TRIGGER trg_signals_prevent_mutation ON signals.signals")
    op.execute("DROP TRIGGER trg_signals_validate_sources ON signals.signals")
    op.execute("DROP FUNCTION signals.prevent_signal_mutation()")
    op.execute("DROP FUNCTION signals.validate_signal_sources()")
    op.drop_index(
        "ix_signals_signals_odds_computed",
        table_name="signals",
        schema="signals",
    )
    op.drop_index(
        "ix_signals_signals_prediction_computed",
        table_name="signals",
        schema="signals",
    )
    op.drop_table("signals", schema="signals")
