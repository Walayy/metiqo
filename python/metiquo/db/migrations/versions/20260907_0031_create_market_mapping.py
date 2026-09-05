"""Créer les règles et tentatives de mapping marché.

Revision ID: 20260907_0031
Revises: 20260907_0030
Create Date: 2026-09-07 19:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260907_0031"
down_revision: str | None = "20260907_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Créer le registre immuable et les décisions brutes append-only."""

    op.create_table(
        "market_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference", sa.String(length=128), nullable=False),
        sa.Column("market_type", sa.String(length=64), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("line_required", sa.Boolean(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("selection_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("remake_policy", sa.String(length=16), nullable=False),
        sa.Column("forfeit_policy", sa.String(length=16), nullable=False),
        sa.Column("cancelled_policy", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(reference)) > 0", name="ck_market_rules_reference"),
        sa.CheckConstraint("market_type = 'MATCH_WINNER'", name="ck_market_rules_market_type"),
        sa.CheckConstraint(
            "period IN ('SERIES', 'GAME_1', 'GAME_2', 'GAME_3', 'GAME_4', 'GAME_5')",
            name="ck_market_rules_period",
        ),
        sa.CheckConstraint("length(trim(unit)) > 0", name="ck_market_rules_unit"),
        sa.CheckConstraint(
            "jsonb_typeof(selection_types) = 'array'",
            name="ck_market_rules_selections_array",
        ),
        sa.CheckConstraint(
            "jsonb_array_length(selection_types) >= 2",
            name="ck_market_rules_selections_count",
        ),
        sa.CheckConstraint(
            "remake_policy IN ('settle', 'void', 'review')",
            name="ck_market_rules_remake_policy",
        ),
        sa.CheckConstraint(
            "forfeit_policy IN ('settle', 'void', 'review')",
            name="ck_market_rules_forfeit_policy",
        ),
        sa.CheckConstraint(
            "cancelled_policy IN ('settle', 'void', 'review')",
            name="ck_market_rules_cancelled_policy",
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_market_rules_fingerprint",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_market_rules"),
        sa.UniqueConstraint("reference", name="uq_odds_market_rules_reference"),
        schema="odds",
    )
    op.create_table(
        "market_mapping_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_market_id", sa.String(length=255), nullable=False),
        sa.Column("raw_label", sa.String(length=255), nullable=False),
        sa.Column("raw_descriptor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_status", sa.String(length=16), nullable=False),
        sa.Column("canonical_market_type", sa.String(length=64), nullable=True),
        sa.Column("canonical_period", sa.String(length=16), nullable=True),
        sa.Column("canonical_line", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("rules_reference", sa.String(length=128), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(provider_market_id)) > 0",
            name="ck_market_mapping_attempts_provider_market_id",
        ),
        sa.CheckConstraint(
            "length(trim(raw_label)) > 0",
            name="ck_market_mapping_attempts_raw_label",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(raw_descriptor) = 'object'",
            name="ck_market_mapping_attempts_raw_descriptor_object",
        ),
        sa.CheckConstraint(
            "result_status IN ('mapped', 'unknown')",
            name="ck_market_mapping_attempts_result_status",
        ),
        sa.CheckConstraint(
            "(result_status = 'mapped' AND canonical_market_type IS NOT NULL "
            "AND canonical_period IS NOT NULL AND rules_reference IS NOT NULL) OR "
            "(result_status = 'unknown' AND canonical_market_type IS NULL "
            "AND canonical_period IS NULL AND rules_reference IS NULL)",
            name="ck_market_mapping_attempts_mapping_state",
        ),
        sa.CheckConstraint(
            "length(trim(reason_code)) > 0",
            name="ck_market_mapping_attempts_reason_code",
        ),
        sa.ForeignKeyConstraint(
            ["provider_event_id"],
            ["odds.events.id"],
            name="fk_market_mapping_attempts_provider_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rules_reference"],
            ["odds.market_rules.reference"],
            name="fk_market_mapping_attempts_rules_reference",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_market_mapping_attempts"),
        schema="odds",
    )
    op.create_index(
        "ix_odds_market_mapping_attempts_event_market_time",
        "market_mapping_attempts",
        ["provider_event_id", "provider_market_id", "evaluated_at"],
        schema="odds",
    )
    for table in ("market_rules", "market_mapping_attempts"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_prevent_mutation
            BEFORE UPDATE OR DELETE ON odds.{table}
            FOR EACH ROW EXECUTE FUNCTION odds.prevent_observation_mutation()
            """
        )


def downgrade() -> None:
    """Retirer les mappings marché et leur registre."""

    for table in ("market_mapping_attempts", "market_rules"):
        op.execute(f"DROP TRIGGER trg_{table}_prevent_mutation ON odds.{table}")
    op.drop_index(
        "ix_odds_market_mapping_attempts_event_market_time",
        table_name="market_mapping_attempts",
        schema="odds",
    )
    op.drop_table("market_mapping_attempts", schema="odds")
    op.drop_table("market_rules", schema="odds")
