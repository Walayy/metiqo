"""Matérialiser les rapports financiers et leurs preuves immuables.

Revision ID: 20260908_0037
Revises: 20260908_0036
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260908_0037"
down_revision: str | None = "20260908_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("method_version", sa.String(128), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("input_evidence", postgresql.JSONB(), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("report_fingerprint", sa.String(64), nullable=False),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
        sa.CheckConstraint(
            "jsonb_typeof(document) = 'object' AND jsonb_typeof(input_evidence) = 'object'",
            name="documents",
        ),
        sa.CheckConstraint(
            "input_fingerprint ~ '^[0-9a-f]{64}$' AND report_fingerprint ~ '^[0-9a-f]{64}$'",
            name="fingerprints",
        ),
        sa.UniqueConstraint("input_fingerprint", name="uq_financial_reports_inputs"),
        schema="signals",
    )
    op.create_index(
        "ix_financial_reports_currency_computed",
        "financial_reports",
        ["currency", "computed_at"],
        schema="signals",
    )
    op.execute("""
        CREATE FUNCTION signals.reject_financial_report_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'financial reports are append-only';
        END $$;
        CREATE TRIGGER financial_reports_append_only BEFORE UPDATE OR DELETE
        ON signals.financial_reports FOR EACH ROW
        EXECUTE FUNCTION signals.reject_financial_report_mutation();
    """)


def downgrade() -> None:
    op.drop_table("financial_reports", schema="signals")
    op.execute("DROP FUNCTION signals.reject_financial_report_mutation()")
