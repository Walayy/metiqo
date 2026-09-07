"""Conserver les états d'alerte et leur délai de rappel entre redémarrages."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260908_0042"
down_revision = "20260908_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_states",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(details) = 'object'", name="ck_alert_states_details_object"
        ),
        sa.CheckConstraint(
            "changed_at <= observed_at AND last_notified_at <= observed_at",
            name="ck_alert_states_times",
        ),
        schema="ops",
    )


def downgrade() -> None:
    op.drop_table("alert_states", schema="ops")
