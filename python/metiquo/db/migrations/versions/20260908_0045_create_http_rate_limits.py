"""Compteurs HTTP partagés et bornés entre instances API."""

import sqlalchemy as sa
from alembic import op

revision = "20260908_0045"
down_revision = "20260908_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "http_rate_limits",
        sa.Column("bucket", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint("attempts >= 1", name="attempts"),
        schema="ops",
    )


def downgrade() -> None:
    op.drop_table("http_rate_limits", schema="ops")
