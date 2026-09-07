"""Conserver les preuves du gate value et les refus avant calcul.

Revision ID: 20260908_0035
Revises: 20260908_0034
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260908_0035"
down_revision: str | None = "20260908_0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "value_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "odds_snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("odds.snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "event_mapping_attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("odds.event_mapping_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "market_mapping_attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("odds.market_mapping_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ml.prematch_predictions.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "policy_version",
            sa.String(128),
            sa.ForeignKey("signals.value_policies.version", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signals.signals.id", ondelete="RESTRICT"),
        ),
        sa.Column("engine_version", sa.String(128), nullable=False),
        sa.Column("grade", sa.String(16), nullable=False),
        sa.Column("abstention_reasons", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.CheckConstraint("grade IN ('VALUE', 'NO_EDGE', 'BLOCKED')", name="grade"),
        sa.CheckConstraint("jsonb_typeof(evidence) = 'object'", name="evidence_object"),
        sa.CheckConstraint("jsonb_typeof(abstention_reasons) = 'array'", name="reasons_array"),
        sa.CheckConstraint(
            "(grade = 'VALUE' AND jsonb_array_length(abstention_reasons) = 0) OR "
            "(grade <> 'VALUE' AND jsonb_array_length(abstention_reasons) > 0)",
            name="grade_reasons",
        ),
        sa.CheckConstraint("grade = 'BLOCKED' OR signal_id IS NOT NULL", name="signal_required"),
        sa.CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
        sa.UniqueConstraint("fingerprint", name="uq_value_evaluations_fingerprint"),
        schema="signals",
    )
    op.create_index(
        "ix_signals_value_evaluations_computed",
        "value_evaluations",
        ["computed_at"],
        schema="signals",
    )
    op.execute("""
        CREATE FUNCTION signals.reject_value_evaluation_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'value evaluations are append-only';
        END $$;
        CREATE TRIGGER value_evaluations_append_only BEFORE UPDATE OR DELETE
        ON signals.value_evaluations FOR EACH ROW
        EXECUTE FUNCTION signals.reject_value_evaluation_mutation();
    """)


def downgrade() -> None:
    op.drop_table("value_evaluations", schema="signals")
    op.execute("DROP FUNCTION signals.reject_value_evaluation_mutation()")
