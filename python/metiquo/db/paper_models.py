"""Décisions fictives immuables et révisions de règlement séparées."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metiquo.db.base import Base, UtcDateTime


class PaperBetRecord(Base):
    __tablename__ = "paper_bets"
    __table_args__ = (
        CheckConstraint("entry_odds >= 1 AND entry_odds < 'Infinity'::numeric", name="odds"),
        CheckConstraint("stake_amount > 0 AND stake_amount < 'Infinity'::numeric", name="stake"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint("length(trim(actor)) > 0", name="actor"),
        CheckConstraint("jsonb_typeof(decision_evidence) = 'object'", name="evidence"),
        CheckConstraint("idempotency_fingerprint ~ '^[0-9a-f]{64}$'", name="idempotency"),
        CheckConstraint("request_fingerprint ~ '^[0-9a-f]{64}$'", name="request"),
        UniqueConstraint("signal_id", name="uq_paper_bets_signal"),
        UniqueConstraint("idempotency_fingerprint", name="uq_paper_bets_idempotency"),
        Index("ix_paper_bets_placed", "placed_at", "id"),
        {"schema": "signals"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    signal_id: Mapped[UUID] = mapped_column(
        ForeignKey("signals.signals.id", ondelete="RESTRICT"), nullable=False
    )
    value_evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("signals.value_evaluations.id", ondelete="RESTRICT"), nullable=False
    )
    prediction_id: Mapped[UUID] = mapped_column(
        ForeignKey("ml.prematch_predictions.id", ondelete="RESTRICT"), nullable=False
    )
    odds_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("odds.snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    model_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("ml.model_versions.id", ondelete="RESTRICT"), nullable=False
    )
    policy_version: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("signals.value_policies.version", ondelete="RESTRICT"),
        nullable=False,
    )
    settlement_rules_version: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("odds.market_rules.reference", ondelete="RESTRICT"),
        nullable=False,
    )
    entry_odds: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    stake_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    placed_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    decision_evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    idempotency_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class PaperSettlementRecord(Base):
    __tablename__ = "settlements"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision"),
        CheckConstraint(
            "status IN ('pending_review', 'won', 'lost', 'push', 'void')", name="status"
        ),
        CheckConstraint(
            "(status = 'pending_review' AND profit_loss IS NULL) OR "
            "(status <> 'pending_review' AND profit_loss IS NOT NULL "
            "AND profit_loss > '-Infinity'::numeric AND profit_loss < 'Infinity'::numeric "
            "AND result_snapshot_id IS NOT NULL)",
            name="result",
        ),
        CheckConstraint("length(trim(reason)) > 0 AND length(trim(actor)) > 0", name="audit"),
        CheckConstraint("jsonb_typeof(evidence) = 'object'", name="evidence"),
        CheckConstraint("idempotency_fingerprint ~ '^[0-9a-f]{64}$'", name="idempotency"),
        CheckConstraint("request_fingerprint ~ '^[0-9a-f]{64}$'", name="request"),
        UniqueConstraint("paper_bet_id", "revision", name="uq_settlements_bet_revision"),
        UniqueConstraint("idempotency_fingerprint", name="uq_settlements_idempotency"),
        Index("ix_settlements_occurred", "occurred_at", "id"),
        {"schema": "signals"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    paper_bet_id: Mapped[UUID] = mapped_column(
        ForeignKey("signals.paper_bets.id", ondelete="RESTRICT"), nullable=False
    )
    revision: Mapped[int] = mapped_column(nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("signals.settlements.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    profit_loss: Mapped[Decimal | None] = mapped_column(Numeric(30, 8))
    result_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("raw.snapshots.id", ondelete="RESTRICT")
    )
    settlement_rules_version: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("odds.market_rules.reference", ondelete="RESTRICT"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    idempotency_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
