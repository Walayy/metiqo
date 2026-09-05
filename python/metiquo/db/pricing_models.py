"""Politiques de value et audits append-only."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from metiquo.db.base import Base, UtcDateTime

SIGNALS_SCHEMA = "signals"


class ValuePolicyRecord(Base):
    """Version immuable de seuils et de leurs surcharges."""

    __tablename__ = "value_policies"
    __table_args__ = (
        CheckConstraint("length(trim(version)) > 0", name="version"),
        CheckConstraint("min_edge BETWEEN 0 AND 1", name="min_edge"),
        CheckConstraint("min_ev BETWEEN 0 AND 1", name="min_ev"),
        CheckConstraint("min_conservative_ev BETWEEN 0 AND 1", name="min_conservative_ev"),
        CheckConstraint("max_odds_age_seconds > 0", name="max_odds_age_seconds"),
        CheckConstraint("min_mapping_confidence BETWEEN 0 AND 1", name="mapping_confidence"),
        CheckConstraint("tuned_through < final_test_starts_at", name="tuning_before_final_test"),
        CheckConstraint("jsonb_typeof(overrides) = 'object'", name="overrides_object"),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        UniqueConstraint("version", name="uq_signals_value_policies_version"),
        Index("ix_signals_value_policies_created", "created_at"),
        {"schema": SIGNALS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    min_edge: Mapped[Decimal] = mapped_column(Numeric(9, 8), nullable=False)
    min_ev: Mapped[Decimal] = mapped_column(Numeric(9, 8), nullable=False)
    min_conservative_ev: Mapped[Decimal] = mapped_column(Numeric(9, 8), nullable=False)
    max_odds_age_seconds: Mapped[int] = mapped_column(nullable=False)
    min_mapping_confidence: Mapped[Decimal] = mapped_column(Numeric(9, 8), nullable=False)
    tuned_through: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    final_test_starts_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    overrides: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class ValuePolicyAuditRecord(Base):
    """Création ou révision de politique, sans mutation possible."""

    __tablename__ = "value_policy_audits"
    __table_args__ = (
        CheckConstraint("action IN ('policy.created', 'policy.revised')", name="action"),
        CheckConstraint("length(trim(actor)) > 0", name="actor"),
        CheckConstraint("length(trim(reason)) > 0", name="reason"),
        CheckConstraint("jsonb_typeof(changes) = 'object'", name="changes_object"),
        CheckConstraint("idempotency_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        UniqueConstraint(
            "idempotency_fingerprint",
            name="uq_signals_value_policy_audits_idempotency",
        ),
        Index("ix_signals_value_policy_audits_occurred", "occurred_at"),
        {"schema": SIGNALS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "signals.value_policies.id",
            name="fk_value_policy_audits_policy",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    previous_policy_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "signals.value_policies.id",
            name="fk_value_policy_audits_previous_policy",
            ondelete="RESTRICT",
        ),
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    changes: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    idempotency_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class SignalRecord(Base):
    """Signal immuable rattaché à ses preuves de prédiction, cote et politique."""

    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint("selection_type IN ('TEAM_A', 'TEAM_B')", name="selection_type"),
        CheckConstraint("offered_odds >= 1", name="offered_odds"),
        CheckConstraint(
            "raw_implied_probability BETWEEN 0 AND 1",
            name="raw_implied_probability",
        ),
        CheckConstraint(
            "model_probability_low BETWEEN 0 AND model_probability",
            name="model_probability_low",
        ),
        CheckConstraint(
            "model_probability_high BETWEEN model_probability AND 1",
            name="model_probability_high",
        ),
        CheckConstraint(
            "grade IN ('VALUE', 'STRONG_VALUE', 'WATCH', 'NO_EDGE', 'BLOCKED')",
            name="grade",
        ),
        CheckConstraint("jsonb_typeof(abstention_reasons) = 'array'", name="reasons_array"),
        CheckConstraint(
            "(grade IN ('VALUE', 'STRONG_VALUE', 'WATCH') "
            "AND jsonb_array_length(abstention_reasons) = 0) OR "
            "(grade IN ('NO_EDGE', 'BLOCKED') "
            "AND jsonb_array_length(abstention_reasons) >= 1)",
            name="grade_reasons",
        ),
        CheckConstraint(
            "(value_computed AND pricing_policy_version IS NOT NULL "
            "AND no_vig_policy_version IS NOT NULL AND no_vig_probability IS NOT NULL "
            "AND edge IS NOT NULL AND expected_value IS NOT NULL "
            "AND conservative_expected_value IS NOT NULL) OR "
            "(NOT value_computed AND pricing_policy_version IS NULL "
            "AND no_vig_policy_version IS NULL AND no_vig_probability IS NULL "
            "AND fair_odds IS NULL AND edge IS NULL AND expected_value IS NULL "
            "AND conservative_expected_value IS NULL)",
            name="value_state",
        ),
        CheckConstraint(
            "NOT value_computed OR ((model_probability = 0 AND fair_odds IS NULL) OR "
            "(model_probability > 0 AND fair_odds >= 1))",
            name="fair_odds",
        ),
        CheckConstraint(
            "no_vig_probability IS NULL OR no_vig_probability BETWEEN 0 AND 1",
            name="no_vig_probability",
        ),
        CheckConstraint("edge IS NULL OR edge BETWEEN -1 AND 1", name="edge"),
        CheckConstraint("expected_value IS NULL OR expected_value >= -1", name="expected_value"),
        CheckConstraint(
            "conservative_expected_value IS NULL OR conservative_expected_value >= -1",
            name="conservative_expected_value",
        ),
        CheckConstraint("grade <> 'NO_EDGE' OR value_computed", name="no_edge_has_value"),
        CheckConstraint("mapping_confidence BETWEEN 0 AND 1", name="mapping_confidence"),
        CheckConstraint("odds_age_seconds >= 0", name="odds_age_seconds"),
        CheckConstraint(
            "source_freshness IN ('fresh', 'stale', 'degraded', 'failed', 'quarantined')",
            name="source_freshness",
        ),
        CheckConstraint("signal_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        UniqueConstraint("signal_fingerprint", name="uq_signals_signals_fingerprint"),
        Index("ix_signals_signals_prediction_computed", "prediction_id", "computed_at"),
        Index("ix_signals_signals_odds_computed", "odds_snapshot_id", "computed_at"),
        {"schema": SIGNALS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    odds_snapshot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("odds.snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    prediction_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("ml.prematch_predictions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    event_mapping_attempt_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("odds.event_mapping_attempts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_version: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("signals.value_policies.version", ondelete="RESTRICT"),
        nullable=False,
    )
    selection_type: Mapped[str] = mapped_column(String(16), nullable=False)
    offered_odds: Mapped[Decimal] = mapped_column(Numeric(38, 28), nullable=False)
    raw_implied_probability: Mapped[Decimal] = mapped_column(Numeric(38, 28), nullable=False)
    model_probability: Mapped[Decimal] = mapped_column(Numeric(38, 28), nullable=False)
    model_probability_low: Mapped[Decimal] = mapped_column(Numeric(38, 28), nullable=False)
    model_probability_high: Mapped[Decimal] = mapped_column(Numeric(38, 28), nullable=False)
    value_computed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    pricing_policy_version: Mapped[str | None] = mapped_column(String(128))
    no_vig_policy_version: Mapped[str | None] = mapped_column(String(128))
    no_vig_probability: Mapped[Decimal | None] = mapped_column(Numeric(38, 28))
    fair_odds: Mapped[Decimal | None] = mapped_column(Numeric(38, 28))
    edge: Mapped[Decimal | None] = mapped_column(Numeric(38, 28))
    expected_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 28))
    conservative_expected_value: Mapped[Decimal | None] = mapped_column(Numeric(38, 28))
    grade: Mapped[str] = mapped_column(String(16), nullable=False)
    abstention_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    mapping_confidence: Mapped[Decimal] = mapped_column(Numeric(9, 8), nullable=False)
    source_freshness: Mapped[str] = mapped_column(String(16), nullable=False)
    odds_age_seconds: Mapped[int] = mapped_column(nullable=False)
    computed_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    signal_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
