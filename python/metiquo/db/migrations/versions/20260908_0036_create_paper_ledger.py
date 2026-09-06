"""Créer le ledger paper et ses révisions de règlement append-only.

Revision ID: 20260908_0036
Revises: 20260908_0035
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260908_0036"
down_revision: str | None = "20260908_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_bets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.signals.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "value_evaluation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.value_evaluations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ml.prematch_predictions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "odds_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("odds.snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "model_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ml.model_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "policy_version",
            sa.String(128),
            sa.ForeignKey("signals.value_policies.version", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "settlement_rules_version",
            sa.String(128),
            sa.ForeignKey("odds.market_rules.reference", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("entry_odds", sa.Numeric(20, 8), nullable=False),
        sa.Column("stake_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("placed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("decision_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_fingerprint", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.CheckConstraint("entry_odds >= 1 AND entry_odds < 'Infinity'::numeric", name="odds"),
        sa.CheckConstraint("stake_amount > 0 AND stake_amount < 'Infinity'::numeric", name="stake"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        sa.CheckConstraint("length(trim(actor)) > 0", name="actor"),
        sa.CheckConstraint("jsonb_typeof(decision_evidence) = 'object'", name="evidence"),
        sa.CheckConstraint("idempotency_fingerprint ~ '^[0-9a-f]{64}$'", name="idempotency"),
        sa.CheckConstraint("request_fingerprint ~ '^[0-9a-f]{64}$'", name="request"),
        sa.UniqueConstraint("signal_id", name="uq_paper_bets_signal"),
        sa.UniqueConstraint("idempotency_fingerprint", name="uq_paper_bets_idempotency"),
        schema="signals",
    )
    op.create_index("ix_paper_bets_placed", "paper_bets", ["placed_at", "id"], schema="signals")
    op.create_table(
        "settlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "paper_bet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.paper_bets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.settlements.id", ondelete="RESTRICT"),
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("profit_loss", sa.Numeric(30, 8)),
        sa.Column(
            "result_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("raw.snapshots.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "settlement_rules_version",
            sa.String(128),
            sa.ForeignKey("odds.market_rules.reference", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(512), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_fingerprint", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.CheckConstraint("revision >= 1", name="revision"),
        sa.CheckConstraint(
            "status IN ('pending_review', 'won', 'lost', 'push', 'void')", name="status"
        ),
        sa.CheckConstraint(
            "(status = 'pending_review' AND profit_loss IS NULL) OR "
            "(status <> 'pending_review' AND profit_loss IS NOT NULL "
            "AND profit_loss > '-Infinity'::numeric AND profit_loss < 'Infinity'::numeric "
            "AND result_snapshot_id IS NOT NULL)",
            name="result",
        ),
        sa.CheckConstraint("length(trim(reason)) > 0 AND length(trim(actor)) > 0", name="audit"),
        sa.CheckConstraint("jsonb_typeof(evidence) = 'object'", name="evidence"),
        sa.CheckConstraint("idempotency_fingerprint ~ '^[0-9a-f]{64}$'", name="idempotency"),
        sa.CheckConstraint("request_fingerprint ~ '^[0-9a-f]{64}$'", name="request"),
        sa.UniqueConstraint("paper_bet_id", "revision", name="uq_settlements_bet_revision"),
        sa.UniqueConstraint("idempotency_fingerprint", name="uq_settlements_idempotency"),
        schema="signals",
    )
    op.create_index(
        "ix_settlements_occurred", "settlements", ["occurred_at", "id"], schema="signals"
    )
    op.execute("""
        CREATE FUNCTION signals.validate_paper_bet() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE s signals.signals%ROWTYPE; e signals.value_evaluations%ROWTYPE;
          o odds.snapshots%ROWTYPE; p ml.prematch_predictions%ROWTYPE;
          m odds.market_mapping_attempts%ROWTYPE; g core.games%ROWTYPE;
        BEGIN
          SELECT * INTO STRICT s FROM signals.signals WHERE id = NEW.signal_id;
          SELECT * INTO STRICT e FROM signals.value_evaluations WHERE id = NEW.value_evaluation_id;
          SELECT * INTO STRICT o FROM odds.snapshots WHERE id = NEW.odds_snapshot_id;
          SELECT * INTO STRICT p FROM ml.prematch_predictions WHERE id = NEW.prediction_id;
          SELECT * INTO STRICT m FROM odds.market_mapping_attempts
            WHERE id = e.market_mapping_attempt_id;
          SELECT * INTO STRICT g FROM core.games WHERE id = p.event_id;
          IF o.captured_at IS NULL OR NOT o.timestamp_reliable OR o.informational_only THEN
            RAISE EXCEPTION 'paper bet requires reliably timestamped odds';
          END IF;
          IF NEW.odds_snapshot_id <> s.odds_snapshot_id OR NEW.prediction_id <> s.prediction_id
            OR NEW.entry_odds <> o.decimal_odds OR NEW.policy_version <> s.policy_version
            OR NEW.model_version_id <> p.model_version_id
            OR e.signal_id IS DISTINCT FROM s.id OR e.grade <> 'VALUE'
            OR s.grade NOT IN ('VALUE', 'STRONG_VALUE') OR NOT s.value_computed
            OR m.rules_reference IS DISTINCT FROM NEW.settlement_rules_version THEN
            RAISE EXCEPTION 'paper bet does not match admitted signal evidence';
          END IF;
          IF NEW.placed_at < GREATEST(o.captured_at, o.recorded_at, s.computed_at, e.computed_at)
            OR g.start_at IS NULL OR NEW.placed_at >= g.start_at
            OR o.event_status <> 'scheduled' OR o.market_status <> 'open' THEN
            RAISE EXCEPTION 'paper decision must follow evidence and precede event start';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER paper_bets_validate BEFORE INSERT ON signals.paper_bets
          FOR EACH ROW EXECUTE FUNCTION signals.validate_paper_bet();

        CREATE FUNCTION signals.validate_paper_settlement() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE b signals.paper_bets%ROWTYPE; previous signals.settlements%ROWTYPE;
          snapshot raw.snapshots%ROWTYPE; expected_pnl numeric;
        BEGIN
          SELECT * INTO STRICT b FROM signals.paper_bets WHERE id = NEW.paper_bet_id FOR UPDATE;
          SELECT * INTO previous FROM signals.settlements WHERE paper_bet_id = b.id
            ORDER BY revision DESC LIMIT 1;
          IF NEW.revision <> COALESCE(previous.revision, 0) + 1
            OR NEW.supersedes_id IS DISTINCT FROM previous.id THEN
            RAISE EXCEPTION 'settlement must extend the latest revision';
          END IF;
          IF NEW.occurred_at < GREATEST(b.placed_at, previous.occurred_at)
            OR NEW.settlement_rules_version <> b.settlement_rules_version THEN
            RAISE EXCEPTION 'settlement chronology or rules mismatch';
          END IF;
          IF NEW.status <> 'pending_review' THEN
            SELECT * INTO STRICT snapshot FROM raw.snapshots WHERE id = NEW.result_snapshot_id;
            IF snapshot.status <> 'validated' OR snapshot.validated_at IS NULL
              OR snapshot.validated_at > NEW.occurred_at THEN
              RAISE EXCEPTION 'final settlement requires a known validated OE snapshot';
            END IF;
            expected_pnl := CASE NEW.status
              WHEN 'won' THEN round(b.stake_amount * (b.entry_odds - 1), 8)
              WHEN 'lost' THEN -b.stake_amount ELSE 0 END;
            IF NEW.profit_loss IS DISTINCT FROM expected_pnl THEN
              RAISE EXCEPTION 'settlement profit must match observed odds and stake';
            END IF;
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER settlements_validate BEFORE INSERT ON signals.settlements
          FOR EACH ROW EXECUTE FUNCTION signals.validate_paper_settlement();

        CREATE FUNCTION signals.reject_paper_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'paper ledger is append-only; append an audited settlement revision';
        END $$;
        CREATE TRIGGER paper_bets_append_only BEFORE UPDATE OR DELETE ON signals.paper_bets
          FOR EACH ROW EXECUTE FUNCTION signals.reject_paper_mutation();
        CREATE TRIGGER settlements_append_only BEFORE UPDATE OR DELETE ON signals.settlements
          FOR EACH ROW EXECUTE FUNCTION signals.reject_paper_mutation();
    """)


def downgrade() -> None:
    op.drop_table("settlements", schema="signals")
    op.drop_table("paper_bets", schema="signals")
    op.execute("DROP FUNCTION signals.validate_paper_settlement()")
    op.execute("DROP FUNCTION signals.validate_paper_bet()")
    op.execute("DROP FUNCTION signals.reject_paper_mutation()")
