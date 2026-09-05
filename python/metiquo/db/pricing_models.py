"""Politiques de value et audits append-only."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint
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
