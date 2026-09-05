"""Créer les politiques de value versionnées et leur audit.

Revision ID: 20260907_0032
Revises: 20260907_0031
Create Date: 2026-09-07 21:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260907_0032"
down_revision: str | None = "20260907_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Créer le registre et ses changements append-only."""

    op.create_table(
        "value_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("min_edge", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("min_ev", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("min_conservative_ev", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("max_odds_age_seconds", sa.Integer(), nullable=False),
        sa.Column("min_mapping_confidence", sa.Numeric(precision=9, scale=8), nullable=False),
        sa.Column("tuned_through", sa.DateTime(timezone=True), nullable=False),
        sa.Column("final_test_starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(version)) > 0", name="ck_value_policies_version"),
        sa.CheckConstraint("min_edge BETWEEN 0 AND 1", name="ck_value_policies_min_edge"),
        sa.CheckConstraint("min_ev BETWEEN 0 AND 1", name="ck_value_policies_min_ev"),
        sa.CheckConstraint(
            "min_conservative_ev BETWEEN 0 AND 1",
            name="ck_value_policies_min_conservative_ev",
        ),
        sa.CheckConstraint(
            "max_odds_age_seconds > 0",
            name="ck_value_policies_max_odds_age_seconds",
        ),
        sa.CheckConstraint(
            "min_mapping_confidence BETWEEN 0 AND 1",
            name="ck_value_policies_mapping_confidence",
        ),
        sa.CheckConstraint(
            "tuned_through < final_test_starts_at",
            name="ck_value_policies_tuning_before_final_test",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(overrides) = 'object'",
            name="ck_value_policies_overrides_object",
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_value_policies_fingerprint",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_signals_value_policies"),
        sa.UniqueConstraint("version", name="uq_signals_value_policies_version"),
        schema="signals",
    )
    op.create_index(
        "ix_signals_value_policies_created",
        "value_policies",
        ["created_at"],
        schema="signals",
    )
    op.create_table(
        "value_policy_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('policy.created', 'policy.revised')",
            name="ck_value_policy_audits_action",
        ),
        sa.CheckConstraint("length(trim(actor)) > 0", name="ck_value_policy_audits_actor"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_value_policy_audits_reason"),
        sa.CheckConstraint(
            "jsonb_typeof(changes) = 'object'",
            name="ck_value_policy_audits_changes_object",
        ),
        sa.CheckConstraint(
            "idempotency_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_value_policy_audits_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["signals.value_policies.id"],
            name="fk_value_policy_audits_policy",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_policy_id"],
            ["signals.value_policies.id"],
            name="fk_value_policy_audits_previous_policy",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_signals_value_policy_audits"),
        sa.UniqueConstraint(
            "idempotency_fingerprint",
            name="uq_signals_value_policy_audits_idempotency",
        ),
        schema="signals",
    )
    op.create_index(
        "ix_signals_value_policy_audits_occurred",
        "value_policy_audits",
        ["occurred_at"],
        schema="signals",
    )
    op.execute(
        """
        CREATE FUNCTION signals.prevent_value_policy_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'value policies and audits are append-only';
        END;
        $$
        """
    )
    for table in ("value_policies", "value_policy_audits"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_prevent_mutation
            BEFORE UPDATE OR DELETE ON signals.{table}
            FOR EACH ROW EXECUTE FUNCTION signals.prevent_value_policy_mutation()
            """
        )


def downgrade() -> None:
    """Retirer les politiques et leurs protections."""

    for table in ("value_policy_audits", "value_policies"):
        op.execute(f"DROP TRIGGER trg_{table}_prevent_mutation ON signals.{table}")
    op.execute("DROP FUNCTION signals.prevent_value_policy_mutation()")
    op.drop_index(
        "ix_signals_value_policy_audits_occurred",
        table_name="value_policy_audits",
        schema="signals",
    )
    op.drop_table("value_policy_audits", schema="signals")
    op.drop_index(
        "ix_signals_value_policies_created",
        table_name="value_policies",
        schema="signals",
    )
    op.drop_table("value_policies", schema="signals")
