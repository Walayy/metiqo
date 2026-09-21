"""Index bounded Oracle history lookups without blocking concurrent imports.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_oracle_rows_version_date",
            "oracle_rows",
            ["version_id", sa.text("left(payload ->> 'date', 10)")],
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index("ix_oracle_rows_version_date", postgresql_concurrently=True)
