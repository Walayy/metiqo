"""Identités fournisseur et observations de cotes append-only."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from metiquo.db.base import Base, UtcDateTime

ODDS_SCHEMA = "odds"


class OddsProviderRecord(Base):
    """Fournisseur logique sans secret ni endpoint implicite."""

    __tablename__ = "providers"
    __table_args__ = (
        CheckConstraint("length(trim(code)) > 0", name="code"),
        CheckConstraint("length(trim(display_name)) > 0", name="display_name"),
        CheckConstraint(
            "provider_type IN ('mock', 'manual_import', 'licensed_feed', 'stake_authorized')",
            name="provider_type",
        ),
        UniqueConstraint("code", name="uq_odds_providers_code"),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class OddsProviderHealth(Base):
    """Contrôle de santé historique, jamais réécrit."""

    __tablename__ = "provider_health"
    __table_args__ = (
        CheckConstraint(
            "status IN ('operational', 'degraded', 'unavailable', 'disabled')",
            name="status",
        ),
        CheckConstraint(
            "last_success_at IS NULL OR last_success_at <= checked_at",
            name="success_before_check",
        ),
        Index("ix_odds_provider_health_provider_checked", "provider_id", "checked_at"),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("odds.providers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    detail: Mapped[str | None] = mapped_column(String(512))


class ProviderOddsEvent(Base):
    """Identité d'événement telle qu'exposée par un fournisseur."""

    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("length(trim(provider_event_id)) > 0", name="provider_event_id"),
        CheckConstraint("game_title = 'lol'", name="game_title"),
        CheckConstraint("length(trim(competition_name)) > 0", name="competition_name"),
        CheckConstraint("jsonb_typeof(participants) = 'array'", name="participants_array"),
        CheckConstraint("jsonb_array_length(participants) >= 2", name="participants_count"),
        CheckConstraint("best_of IS NULL OR best_of BETWEEN 1 AND 9", name="best_of"),
        CheckConstraint(
            "status IN ('scheduled', 'live', 'finished', 'cancelled')",
            name="status",
        ),
        CheckConstraint("length(trim(source_reference)) > 0", name="source_reference"),
        UniqueConstraint("provider_id", "provider_event_id", name="uq_odds_events_identity"),
        UniqueConstraint("id", "provider_id", name="uq_odds_events_id_provider"),
        Index("ix_odds_events_provider_start", "provider_id", "starts_at"),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("odds.providers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    game_title: Mapped[str] = mapped_column(String(32), nullable=False)
    competition_name: Mapped[str] = mapped_column(String(255), nullable=False)
    participants: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    best_of: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class ProviderOddsMarket(Base):
    """Identité et règles d'un marché fournisseur."""

    __tablename__ = "markets"
    __table_args__ = (
        CheckConstraint("length(trim(provider_market_id)) > 0", name="provider_market_id"),
        CheckConstraint("length(trim(raw_label)) > 0", name="raw_label"),
        CheckConstraint("market_type = 'MATCH_WINNER'", name="market_type"),
        CheckConstraint(
            "period IN ('SERIES', 'GAME_1', 'GAME_2', 'GAME_3', 'GAME_4', 'GAME_5')",
            name="period",
        ),
        CheckConstraint("length(trim(settlement_rules_version)) > 0", name="rules_version"),
        UniqueConstraint("event_id", "provider_market_id", name="uq_odds_markets_identity"),
        UniqueConstraint("id", "event_id", name="uq_odds_markets_id_event"),
        Index("ix_odds_markets_event", "event_id"),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("odds.events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_market_id: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_label: Mapped[str] = mapped_column(String(255), nullable=False)
    market_type: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    line: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    settlement_rules_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class ProviderOddsSelection(Base):
    """Issue fournisseur conservée avant sa résolution canonique."""

    __tablename__ = "selections"
    __table_args__ = (
        CheckConstraint("length(trim(provider_selection_id)) > 0", name="provider_selection_id"),
        CheckConstraint("length(trim(raw_label)) > 0", name="raw_label"),
        CheckConstraint(
            "selection_type IN ('TEAM_A', 'TEAM_B', 'DRAW', 'OVER', 'UNDER')",
            name="selection_type",
        ),
        UniqueConstraint(
            "market_id",
            "provider_selection_id",
            name="uq_odds_selections_identity",
        ),
        UniqueConstraint("id", "market_id", name="uq_odds_selections_id_market"),
        Index("ix_odds_selections_market", "market_id"),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    market_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("odds.markets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_selection_id: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_label: Mapped[str] = mapped_column(String(255), nullable=False)
    selection_type: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class OddsSnapshotRecord(Base):
    """Observation de prix horodatée, cohérente et immuable."""

    __tablename__ = "snapshots"
    __table_args__ = (
        CheckConstraint(
            "provider_status IN ('operational', 'degraded', 'unavailable', 'disabled')",
            name="provider_status",
        ),
        CheckConstraint(
            "event_status IN ('scheduled', 'live', 'finished', 'cancelled')",
            name="event_status",
        ),
        CheckConstraint(
            "market_status IN ('open', 'suspended', 'settled', 'void')",
            name="market_status",
        ),
        CheckConstraint("decimal_odds >= 1", name="decimal_odds"),
        CheckConstraint("captured_at IS NULL OR captured_at <= recorded_at", name="capture_order"),
        CheckConstraint(
            "NOT timestamp_reliable OR captured_at IS NOT NULL",
            name="reliable_timestamp",
        ),
        CheckConstraint(
            "informational_only OR (timestamp_reliable AND captured_at IS NOT NULL)",
            name="signal_timestamp",
        ),
        CheckConstraint("length(trim(selection_label)) > 0", name="selection_label"),
        CheckConstraint("length(trim(raw_payload_reference)) > 0", name="raw_reference"),
        CheckConstraint("length(trim(provenance_reference)) > 0", name="provenance_reference"),
        CheckConstraint(
            "raw_payload_sha256 IS NULL OR raw_payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="raw_hash",
        ),
        CheckConstraint(
            "observation_fingerprint ~ '^[0-9a-f]{64}$'",
            name="observation_fingerprint",
        ),
        ForeignKeyConstraint(
            ["event_id", "provider_id"],
            ["odds.events.id", "odds.events.provider_id"],
            name="fk_odds_snapshots_event_provider",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["market_id", "event_id"],
            ["odds.markets.id", "odds.markets.event_id"],
            name="fk_odds_snapshots_market_event",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["selection_id", "market_id"],
            ["odds.selections.id", "odds.selections.market_id"],
            name="fk_odds_snapshots_selection_market",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "observation_fingerprint",
            name="uq_odds_snapshots_observation_fingerprint",
        ),
        Index(
            "ix_odds_snapshots_event_market_selection_captured",
            "event_id",
            "market_id",
            "selection_id",
            "captured_at",
        ),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    event_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    market_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    selection_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    provider_status: Mapped[str] = mapped_column(String(16), nullable=False)
    event_status: Mapped[str] = mapped_column(String(16), nullable=False)
    market_status: Mapped[str] = mapped_column(String(16), nullable=False)
    selection_label: Mapped[str] = mapped_column(String(255), nullable=False)
    line: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    decimal_odds: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    recorded_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )
    timestamp_reliable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    informational_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    raw_payload_reference: Mapped[str] = mapped_column(String(1024), nullable=False)
    raw_payload_sha256: Mapped[str | None] = mapped_column(String(64))
    provenance_reference: Mapped[str] = mapped_column(String(1024), nullable=False)
    observation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class EventMappingAttempt(Base):
    """Décision append-only de résolution d'un événement fournisseur."""

    __tablename__ = "event_mapping_attempts"
    __table_args__ = (
        CheckConstraint(
            "result_status IN ('auto_matched', 'review', 'rejected')",
            name="result_status",
        ),
        CheckConstraint("top_score BETWEEN 0 AND 1", name="top_score"),
        CheckConstraint(
            "(result_status = 'auto_matched') = (selected_event_id IS NOT NULL)",
            name="selected_event",
        ),
        CheckConstraint("length(trim(weights_version)) > 0", name="weights_version"),
        CheckConstraint("length(trim(reason_code)) > 0", name="reason_code"),
        Index(
            "ix_odds_event_mapping_attempts_provider_event_time",
            "provider_event_id",
            "evaluated_at",
        ),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_event_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("odds.events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    result_status: Mapped[str] = mapped_column(String(16), nullable=False)
    selected_event_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    top_score: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    selections_inverted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    weights_version: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class EventMappingCandidateScore(Base):
    """Composantes auditables d'un candidat de matching événement."""

    __tablename__ = "event_mapping_candidate_scores"
    __table_args__ = (
        CheckConstraint("rank >= 1", name="rank"),
        CheckConstraint("team_score BETWEEN 0 AND 1", name="team_score"),
        CheckConstraint("time_score BETWEEN 0 AND 1", name="time_score"),
        CheckConstraint("competition_score BETWEEN 0 AND 1", name="competition_score"),
        CheckConstraint("format_score BETWEEN 0 AND 1", name="format_score"),
        CheckConstraint("total_score BETWEEN 0 AND 1", name="total_score"),
        UniqueConstraint("attempt_id", "rank", name="uq_odds_event_mapping_candidate_rank"),
        UniqueConstraint(
            "attempt_id",
            "canonical_event_id",
            name="uq_odds_event_mapping_candidate_event",
        ),
        Index(
            "ix_odds_event_mapping_candidates_event_score",
            "canonical_event_id",
            "total_score",
        ),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "odds.event_mapping_attempts.id",
            name="fk_event_mapping_scores_attempt",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    canonical_event_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(nullable=False)
    team_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    time_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    competition_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    format_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    total_score: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    selections_inverted: Mapped[bool] = mapped_column(Boolean, nullable=False)


class MappingReviewRecord(Base):
    """État courant d'une revue manuelle adossée à une tentative immuable."""

    __tablename__ = "mapping_reviews"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status"),
        CheckConstraint(
            "(status = 'pending' AND selected_event_id IS NULL AND reviewed_at IS NULL "
            "AND reviewer IS NULL AND decision_reason IS NULL) OR "
            "(status = 'approved' AND selected_event_id IS NOT NULL AND reviewed_at IS NOT NULL "
            "AND reviewer IS NOT NULL AND decision_reason IS NOT NULL) OR "
            "(status = 'rejected' AND selected_event_id IS NULL AND reviewed_at IS NOT NULL "
            "AND reviewer IS NOT NULL AND decision_reason IS NOT NULL)",
            name="decision_state",
        ),
        CheckConstraint(
            "reviewed_at IS NULL OR reviewed_at >= created_at",
            name="review_order",
        ),
        UniqueConstraint("attempt_id", name="uq_odds_mapping_reviews_attempt"),
        Index("ix_odds_mapping_reviews_status_created", "status", "created_at"),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "odds.event_mapping_attempts.id",
            name="fk_mapping_reviews_attempt",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    selected_event_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    reviewer: Mapped[str | None] = mapped_column(String(255))
    decision_reason: Mapped[str | None] = mapped_column(String(512))


class MappingAuditRecord(Base):
    """Audit append-only des décisions et créations d'alias."""

    __tablename__ = "mapping_audits"
    __table_args__ = (
        CheckConstraint(
            "action IN ('mapping.approved', 'mapping.rejected', 'alias.create')",
            name="action",
        ),
        CheckConstraint("length(trim(resource_id)) > 0", name="resource_id"),
        CheckConstraint("length(trim(actor)) > 0", name="actor"),
        CheckConstraint("length(trim(reason)) > 0", name="reason"),
        CheckConstraint(
            "idempotency_fingerprint ~ '^[0-9a-f]{64}$'",
            name="idempotency_fingerprint",
        ),
        UniqueConstraint(
            "idempotency_fingerprint",
            name="uq_odds_mapping_audits_idempotency",
        ),
        Index("ix_odds_mapping_audits_occurred", "occurred_at"),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    review_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "odds.mapping_reviews.id",
            name="fk_mapping_audits_review",
            ondelete="RESTRICT",
        ),
    )
    entity_alias_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    impact: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    idempotency_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class MarketRulesRecord(Base):
    """Référence de règlement immuable autorisant un mapping de marché."""

    __tablename__ = "market_rules"
    __table_args__ = (
        CheckConstraint("length(trim(reference)) > 0", name="reference"),
        CheckConstraint("market_type = 'MATCH_WINNER'", name="market_type"),
        CheckConstraint(
            "period IN ('SERIES', 'GAME_1', 'GAME_2', 'GAME_3', 'GAME_4', 'GAME_5')",
            name="period",
        ),
        CheckConstraint("length(trim(unit)) > 0", name="unit"),
        CheckConstraint("jsonb_typeof(selection_types) = 'array'", name="selections_array"),
        CheckConstraint("jsonb_array_length(selection_types) >= 2", name="selections_count"),
        CheckConstraint(
            "remake_policy IN ('settle', 'void', 'review')",
            name="remake_policy",
        ),
        CheckConstraint(
            "forfeit_policy IN ('settle', 'void', 'review')",
            name="forfeit_policy",
        ),
        CheckConstraint(
            "cancelled_policy IN ('settle', 'void', 'review')",
            name="cancelled_policy",
        ),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        UniqueConstraint("reference", name="uq_odds_market_rules_reference"),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    reference: Mapped[str] = mapped_column(String(128), nullable=False)
    market_type: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    line_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    selection_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    remake_policy: Mapped[str] = mapped_column(String(16), nullable=False)
    forfeit_policy: Mapped[str] = mapped_column(String(16), nullable=False)
    cancelled_policy: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class MarketMappingAttempt(Base):
    """Décision append-only conservant le descripteur provider complet."""

    __tablename__ = "market_mapping_attempts"
    __table_args__ = (
        CheckConstraint("length(trim(provider_market_id)) > 0", name="provider_market_id"),
        CheckConstraint("length(trim(raw_label)) > 0", name="raw_label"),
        CheckConstraint("jsonb_typeof(raw_descriptor) = 'object'", name="raw_descriptor_object"),
        CheckConstraint("result_status IN ('mapped', 'unknown')", name="result_status"),
        CheckConstraint(
            "(result_status = 'mapped' AND canonical_market_type IS NOT NULL "
            "AND canonical_period IS NOT NULL AND rules_reference IS NOT NULL) OR "
            "(result_status = 'unknown' AND canonical_market_type IS NULL "
            "AND canonical_period IS NULL AND rules_reference IS NULL)",
            name="mapping_state",
        ),
        CheckConstraint("length(trim(reason_code)) > 0", name="reason_code"),
        Index(
            "ix_odds_market_mapping_attempts_event_market_time",
            "provider_event_id",
            "provider_market_id",
            "evaluated_at",
        ),
        {"schema": ODDS_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_event_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey(
            "odds.events.id",
            name="fk_market_mapping_attempts_provider_event",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    provider_market_id: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_label: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_descriptor: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    result_status: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_market_type: Mapped[str | None] = mapped_column(String(64))
    canonical_period: Mapped[str | None] = mapped_column(String(16))
    canonical_line: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    rules_reference: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey(
            "odds.market_rules.reference",
            name="fk_market_mapping_attempts_rules_reference",
            ondelete="RESTRICT",
        ),
    )
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
