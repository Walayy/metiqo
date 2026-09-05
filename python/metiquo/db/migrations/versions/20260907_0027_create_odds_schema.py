"""Créer les identités et observations de cotes immuables.

Revision ID: 20260907_0027
Revises: 20260907_0026
Create Date: 2026-09-07 14:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260907_0027"
down_revision: str | None = "20260907_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Créer le socle provider/event/market/selection et les preuves append-only."""

    op.create_table(
        "providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(code)) > 0", name="code"),
        sa.CheckConstraint("length(trim(display_name)) > 0", name="display_name"),
        sa.CheckConstraint(
            "provider_type IN ('mock', 'manual_import', 'licensed_feed', 'stake_authorized')",
            name="provider_type",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_providers"),
        sa.UniqueConstraint("code", name="uq_odds_providers_code"),
        schema="odds",
    )
    op.create_table(
        "provider_health",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.String(length=512), nullable=True),
        sa.CheckConstraint(
            "status IN ('operational', 'degraded', 'unavailable', 'disabled')",
            name="status",
        ),
        sa.CheckConstraint(
            "last_success_at IS NULL OR last_success_at <= checked_at",
            name="success_before_check",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["odds.providers.id"],
            name="fk_odds_provider_health_provider_id_providers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_provider_health"),
        schema="odds",
    )
    op.create_index(
        "ix_odds_provider_health_provider_checked",
        "provider_health",
        ["provider_id", "checked_at"],
        schema="odds",
    )
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column("game_title", sa.String(length=32), nullable=False),
        sa.Column("competition_name", sa.String(length=255), nullable=False),
        sa.Column("participants", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("best_of", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_reference", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(provider_event_id)) > 0", name="provider_event_id"),
        sa.CheckConstraint("game_title = 'lol'", name="game_title"),
        sa.CheckConstraint("length(trim(competition_name)) > 0", name="competition_name"),
        sa.CheckConstraint("jsonb_typeof(participants) = 'array'", name="participants_array"),
        sa.CheckConstraint("jsonb_array_length(participants) >= 2", name="participants_count"),
        sa.CheckConstraint("best_of IS NULL OR best_of BETWEEN 1 AND 9", name="best_of"),
        sa.CheckConstraint(
            "status IN ('scheduled', 'live', 'finished', 'cancelled')",
            name="status",
        ),
        sa.CheckConstraint("length(trim(source_reference)) > 0", name="source_reference"),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["odds.providers.id"],
            name="fk_odds_events_provider_id_providers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_events"),
        sa.UniqueConstraint("provider_id", "provider_event_id", name="uq_odds_events_identity"),
        sa.UniqueConstraint("id", "provider_id", name="uq_odds_events_id_provider"),
        schema="odds",
    )
    op.create_index(
        "ix_odds_events_provider_start",
        "events",
        ["provider_id", "starts_at"],
        schema="odds",
    )
    op.create_table(
        "markets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_market_id", sa.String(length=255), nullable=False),
        sa.Column("raw_label", sa.String(length=255), nullable=False),
        sa.Column("market_type", sa.String(length=64), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("line", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("settlement_rules_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(provider_market_id)) > 0", name="provider_market_id"),
        sa.CheckConstraint("length(trim(raw_label)) > 0", name="raw_label"),
        sa.CheckConstraint("market_type = 'MATCH_WINNER'", name="market_type"),
        sa.CheckConstraint(
            "period IN ('SERIES', 'GAME_1', 'GAME_2', 'GAME_3', 'GAME_4', 'GAME_5')",
            name="period",
        ),
        sa.CheckConstraint("length(trim(settlement_rules_version)) > 0", name="rules_version"),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["odds.events.id"],
            name="fk_odds_markets_event_id_events",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_markets"),
        sa.UniqueConstraint("event_id", "provider_market_id", name="uq_odds_markets_identity"),
        sa.UniqueConstraint("id", "event_id", name="uq_odds_markets_id_event"),
        schema="odds",
    )
    op.create_index("ix_odds_markets_event", "markets", ["event_id"], schema="odds")
    op.create_table(
        "selections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_selection_id", sa.String(length=255), nullable=False),
        sa.Column("raw_label", sa.String(length=255), nullable=False),
        sa.Column("selection_type", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(provider_selection_id)) > 0",
            name="provider_selection_id",
        ),
        sa.CheckConstraint("length(trim(raw_label)) > 0", name="raw_label"),
        sa.CheckConstraint(
            "selection_type IN ('TEAM_A', 'TEAM_B', 'DRAW', 'OVER', 'UNDER')",
            name="selection_type",
        ),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["odds.markets.id"],
            name="fk_odds_selections_market_id_markets",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_selections"),
        sa.UniqueConstraint(
            "market_id",
            "provider_selection_id",
            name="uq_odds_selections_identity",
        ),
        sa.UniqueConstraint("id", "market_id", name="uq_odds_selections_id_market"),
        schema="odds",
    )
    op.create_index("ix_odds_selections_market", "selections", ["market_id"], schema="odds")
    op.create_table(
        "snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("selection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_status", sa.String(length=16), nullable=False),
        sa.Column("event_status", sa.String(length=16), nullable=False),
        sa.Column("market_status", sa.String(length=16), nullable=False),
        sa.Column("selection_label", sa.String(length=255), nullable=False),
        sa.Column("line", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("decimal_odds", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timestamp_reliable", sa.Boolean(), nullable=False),
        sa.Column("informational_only", sa.Boolean(), nullable=False),
        sa.Column("raw_payload_reference", sa.String(length=1024), nullable=False),
        sa.Column("raw_payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("provenance_reference", sa.String(length=1024), nullable=False),
        sa.Column("observation_fingerprint", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "provider_status IN ('operational', 'degraded', 'unavailable', 'disabled')",
            name="provider_status",
        ),
        sa.CheckConstraint(
            "event_status IN ('scheduled', 'live', 'finished', 'cancelled')",
            name="event_status",
        ),
        sa.CheckConstraint(
            "market_status IN ('open', 'suspended', 'settled', 'void')",
            name="market_status",
        ),
        sa.CheckConstraint("decimal_odds >= 1", name="decimal_odds"),
        sa.CheckConstraint(
            "captured_at IS NULL OR captured_at <= recorded_at",
            name="capture_order",
        ),
        sa.CheckConstraint(
            "NOT timestamp_reliable OR captured_at IS NOT NULL",
            name="reliable_timestamp",
        ),
        sa.CheckConstraint(
            "informational_only OR (timestamp_reliable AND captured_at IS NOT NULL)",
            name="signal_timestamp",
        ),
        sa.CheckConstraint("length(trim(selection_label)) > 0", name="selection_label"),
        sa.CheckConstraint("length(trim(raw_payload_reference)) > 0", name="raw_reference"),
        sa.CheckConstraint(
            "length(trim(provenance_reference)) > 0",
            name="provenance_reference",
        ),
        sa.CheckConstraint(
            "raw_payload_sha256 IS NULL OR raw_payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="raw_hash",
        ),
        sa.CheckConstraint(
            "observation_fingerprint ~ '^[0-9a-f]{64}$'",
            name="observation_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["event_id", "provider_id"],
            ["odds.events.id", "odds.events.provider_id"],
            name="fk_odds_snapshots_event_provider",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["market_id", "event_id"],
            ["odds.markets.id", "odds.markets.event_id"],
            name="fk_odds_snapshots_market_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["selection_id", "market_id"],
            ["odds.selections.id", "odds.selections.market_id"],
            name="fk_odds_snapshots_selection_market",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_snapshots"),
        sa.UniqueConstraint(
            "observation_fingerprint",
            name="uq_odds_snapshots_observation_fingerprint",
        ),
        schema="odds",
    )
    op.create_index(
        "ix_odds_snapshots_event_market_selection_captured",
        "snapshots",
        ["event_id", "market_id", "selection_id", "captured_at"],
        schema="odds",
    )
    op.execute(
        """
        CREATE FUNCTION odds.prevent_observation_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'odds observations are append-only';
        END;
        $$
        """
    )
    for table in ("provider_health", "snapshots"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_prevent_mutation
            BEFORE UPDATE OR DELETE ON odds.{table}
            FOR EACH ROW EXECUTE FUNCTION odds.prevent_observation_mutation()
            """
        )


def downgrade() -> None:
    """Retirer le socle odds et ses protections append-only."""

    for table in ("snapshots", "provider_health"):
        op.execute(f"DROP TRIGGER trg_{table}_prevent_mutation ON odds.{table}")
    op.execute("DROP FUNCTION odds.prevent_observation_mutation()")
    op.drop_index(
        "ix_odds_snapshots_event_market_selection_captured",
        table_name="snapshots",
        schema="odds",
    )
    op.drop_table("snapshots", schema="odds")
    op.drop_index(
        "ix_odds_selections_market",
        table_name="selections",
        schema="odds",
    )
    op.drop_table("selections", schema="odds")
    op.drop_index("ix_odds_markets_event", table_name="markets", schema="odds")
    op.drop_table("markets", schema="odds")
    op.drop_index("ix_odds_events_provider_start", table_name="events", schema="odds")
    op.drop_table("events", schema="odds")
    op.drop_index(
        "ix_odds_provider_health_provider_checked",
        table_name="provider_health",
        schema="odds",
    )
    op.drop_table("provider_health", schema="odds")
    op.drop_table("providers", schema="odds")
