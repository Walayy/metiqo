"""Relier la probabilité de signal à une identité d'équipe immuable.

Revision ID: 20260908_0038
Revises: 20260908_0037
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260908_0038"
down_revision: str | None = "20260908_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "signals",
        sa.Column("selected_team_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="signals",
    )
    op.create_foreign_key(
        "fk_signals_selected_team",
        "signals",
        "teams",
        ["selected_team_id"],
        ["id"],
        source_schema="signals",
        referent_schema="core",
        ondelete="RESTRICT",
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION signals.validate_signal_sources()
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

          IF NEW.selected_team_id IS NULL OR NOT EXISTS (
            SELECT 1 FROM core.game_team_stats t
            WHERE t.game_id = mapping_event AND t.team_id = NEW.selected_team_id
              AND t.side = CASE NEW.selection_type WHEN 'TEAM_A' THEN 'Blue' ELSE 'Red' END
              AND t.processed_at <= NEW.computed_at
          ) OR NOT EXISTS (
            SELECT 1 FROM ml.prematch_predictions p WHERE p.id = NEW.prediction_id
              AND NEW.selected_team_id IN (p.team_a_id, p.team_b_id)
          ) THEN
            RAISE EXCEPTION 'signal selected team identity does not match its evidence';
          END IF;

          SELECT p.event_id, p.predicted_at, p.enabled,
                 CASE WHEN NEW.selected_team_id = p.team_a_id
                      THEN p.team_a_probability ELSE p.team_b_probability END,
                 CASE WHEN NEW.selected_team_id = p.team_a_id
                      THEN p.team_a_low ELSE p.team_b_low END,
                 CASE WHEN NEW.selected_team_id = p.team_a_id
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
        """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION signals.validate_signal_sources()
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
        """)
    op.drop_constraint("fk_signals_selected_team", "signals", schema="signals", type_="foreignkey")
    op.drop_column("signals", "selected_team_id", schema="signals")
