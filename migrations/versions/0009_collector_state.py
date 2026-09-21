"""Durable SofaScore pacing, cooldown and discovery checkpoint.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collector_state",
        sa.Column("source", sa.String(), primary_key=True),
        sa.Column("data", postgresql.JSONB(), nullable=False),
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_api') THEN
        GRANT SELECT ON collector_state TO metiquo_api;
      END IF;
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_worker') THEN
        GRANT SELECT, INSERT, UPDATE ON collector_state TO metiquo_worker;
      END IF;
    END $$""")


def downgrade() -> None:
    op.drop_table("collector_state")
