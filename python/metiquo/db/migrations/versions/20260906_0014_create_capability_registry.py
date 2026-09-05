"""Créer le registre versionné des capacités par snapshot.

Revision ID: 20260906_0014
Revises: 20260906_0013
Create Date: 2026-09-06 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0014"
down_revision: str | None = "20260906_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CORE_SCHEMA = "core"


def upgrade() -> None:
    """Créer une suite d'évaluations append-only pour chaque capacité."""

    op.create_table(
        "capability_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capability", sa.String(length=128), nullable=False),
        sa.Column("capability_kind", sa.String(length=16), nullable=False),
        sa.Column("threshold_version", sa.String(length=64), nullable=False),
        sa.Column("evaluation_revision", sa.Integer(), nullable=False),
        sa.Column("previous_evaluation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("required_columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("observed_columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("minimum_completeness", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("observed_completeness", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("minimum_sample_size", sa.Integer(), nullable=False),
        sa.Column("observed_sample_size", sa.Integer(), nullable=False),
        sa.Column("gates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "capability_kind IN ('label', 'feature', 'market')",
            name="ck_capability_evaluations_kind",
        ),
        sa.CheckConstraint(
            "status IN ('enabled', 'disabled', 'pending')",
            name="ck_capability_evaluations_status",
        ),
        sa.CheckConstraint(
            "evaluation_revision >= 1",
            name="ck_capability_evaluations_evaluation_revision",
        ),
        sa.CheckConstraint(
            "minimum_completeness BETWEEN 0 AND 1",
            name="ck_capability_evaluations_minimum_completeness",
        ),
        sa.CheckConstraint(
            "observed_completeness BETWEEN 0 AND 1",
            name="ck_capability_evaluations_observed_completeness",
        ),
        sa.CheckConstraint(
            "minimum_sample_size >= 0",
            name="ck_capability_evaluations_minimum_sample_size",
        ),
        sa.CheckConstraint(
            "observed_sample_size >= 0",
            name="ck_capability_evaluations_observed_sample_size",
        ),
        sa.CheckConstraint(
            "evidence_hash ~ '^[0-9a-f]{64}$'",
            name="ck_capability_evaluations_evidence_hash",
        ),
        sa.CheckConstraint(
            "length(trim(capability)) > 0",
            name="ck_capability_evaluations_capability",
        ),
        sa.CheckConstraint(
            "length(trim(threshold_version)) > 0",
            name="ck_capability_evaluations_threshold_version",
        ),
        sa.CheckConstraint(
            "(evaluation_revision = 1 AND previous_evaluation_id IS NULL) "
            "OR (evaluation_revision > 1 AND previous_evaluation_id IS NOT NULL)",
            name="ck_capability_evaluations_revision_chain",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_cap_eval_snapshot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_evaluation_id"],
            ["core.capability_evaluations.id"],
            name="fk_cap_eval_previous",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_capability_evaluations"),
        sa.UniqueConstraint(
            "snapshot_id",
            "capability",
            "threshold_version",
            "evaluation_revision",
            name="uq_capability_evaluations_snapshot_capability_revision",
        ),
        schema=CORE_SCHEMA,
    )
    op.create_index(
        "ix_core_capability_evaluations_lookup",
        "capability_evaluations",
        ["snapshot_id", "capability", "evaluated_at"],
        schema=CORE_SCHEMA,
    )
    op.execute(
        """
        CREATE FUNCTION core.prevent_capability_evaluation_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'capability evaluation % is append-only', OLD.id;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_capability_evaluations_prevent_mutation
        BEFORE UPDATE OR DELETE ON core.capability_evaluations
        FOR EACH ROW EXECUTE FUNCTION core.prevent_capability_evaluation_mutation()
        """
    )


def downgrade() -> None:
    """Retirer le registre après sa protection append-only."""

    op.execute(
        "DROP TRIGGER trg_capability_evaluations_prevent_mutation ON core.capability_evaluations"
    )
    op.execute("DROP FUNCTION core.prevent_capability_evaluation_mutation()")
    op.drop_index(
        "ix_core_capability_evaluations_lookup",
        table_name="capability_evaluations",
        schema=CORE_SCHEMA,
    )
    op.drop_table("capability_evaluations", schema=CORE_SCHEMA)
