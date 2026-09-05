"""Créer la file de revue et son audit.

Revision ID: 20260907_0030
Revises: 20260907_0029
Create Date: 2026-09-07 18:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260907_0030"
down_revision: str | None = "20260907_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Créer l'état de revue modifiable et les décisions immuables."""

    op.create_table(
        "mapping_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("selected_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer", sa.String(length=255), nullable=True),
        sa.Column("decision_reason", sa.String(length=512), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_mapping_reviews_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND selected_event_id IS NULL AND reviewed_at IS NULL "
            "AND reviewer IS NULL AND decision_reason IS NULL) OR "
            "(status = 'approved' AND selected_event_id IS NOT NULL AND reviewed_at IS NOT NULL "
            "AND reviewer IS NOT NULL AND decision_reason IS NOT NULL) OR "
            "(status = 'rejected' AND selected_event_id IS NULL AND reviewed_at IS NOT NULL "
            "AND reviewer IS NOT NULL AND decision_reason IS NOT NULL)",
            name="ck_mapping_reviews_decision_state",
        ),
        sa.CheckConstraint(
            "reviewed_at IS NULL OR reviewed_at >= created_at",
            name="ck_mapping_reviews_review_order",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["odds.event_mapping_attempts.id"],
            name="fk_mapping_reviews_attempt",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_mapping_reviews"),
        sa.UniqueConstraint("attempt_id", name="uq_odds_mapping_reviews_attempt"),
        schema="odds",
    )
    op.create_index(
        "ix_odds_mapping_reviews_status_created",
        "mapping_reviews",
        ["status", "created_at"],
        schema="odds",
    )
    op.create_table(
        "mapping_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_alias_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=False),
        sa.Column("impact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('mapping.approved', 'mapping.rejected', 'alias.create')",
            name="ck_mapping_audits_action",
        ),
        sa.CheckConstraint(
            "length(trim(resource_id)) > 0",
            name="ck_mapping_audits_resource_id",
        ),
        sa.CheckConstraint("length(trim(actor)) > 0", name="ck_mapping_audits_actor"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_mapping_audits_reason"),
        sa.CheckConstraint(
            "idempotency_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_mapping_audits_idempotency_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["odds.mapping_reviews.id"],
            name="fk_mapping_audits_review",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_odds_mapping_audits"),
        sa.UniqueConstraint(
            "idempotency_fingerprint",
            name="uq_odds_mapping_audits_idempotency",
        ),
        schema="odds",
    )
    op.create_index(
        "ix_odds_mapping_audits_occurred",
        "mapping_audits",
        ["occurred_at"],
        schema="odds",
    )
    op.execute(
        """
        CREATE TRIGGER trg_mapping_audits_prevent_mutation
        BEFORE UPDATE OR DELETE ON odds.mapping_audits
        FOR EACH ROW EXECUTE FUNCTION odds.prevent_observation_mutation()
        """
    )


def downgrade() -> None:
    """Retirer la file de revue et son audit."""

    op.execute("DROP TRIGGER trg_mapping_audits_prevent_mutation ON odds.mapping_audits")
    op.drop_index(
        "ix_odds_mapping_audits_occurred",
        table_name="mapping_audits",
        schema="odds",
    )
    op.drop_table("mapping_audits", schema="odds")
    op.drop_index(
        "ix_odds_mapping_reviews_status_created",
        table_name="mapping_reviews",
        schema="odds",
    )
    op.drop_table("mapping_reviews", schema="odds")
