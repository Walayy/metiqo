"""Keep fixtures whose independently sourced series format is still unknown.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("matches", "format", existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    # PostgreSQL refuses this downgrade if unknown formats exist: do not invent BO1.
    op.alter_column("matches", "format", existing_type=sa.String(), nullable=False)
