"""Bounded, sanitized operational journal for the three worker services.

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_log_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("script_id", sa.String(80)),
        sa.Column("run_id", sa.Uuid()),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("stage", sa.String(80), nullable=False),
        sa.Column("message", sa.String(255), nullable=False),
        sa.Column("event_id", sa.String(80)),
        sa.Column("context", JSONB(), nullable=False),
        sa.CheckConstraint("worker_id IN (1, 2, 3)", name="ck_worker_log_service"),
        sa.CheckConstraint("level IN ('info', 'warning', 'error')", name="ck_worker_log_level"),
    )
    op.create_index("ix_worker_logs_worker_id", "worker_log_entries", ["worker_id", "id"])
    op.create_index("ix_worker_logs_run_id", "worker_log_entries", ["run_id", "id"])
    op.create_index("ix_worker_logs_recorded_at", "worker_log_entries", ["recorded_at"])
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_api') THEN
            GRANT SELECT ON worker_log_entries TO metiquo_api;
        END IF;
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_worker') THEN
            GRANT SELECT, INSERT, DELETE ON worker_log_entries TO metiquo_worker;
            GRANT USAGE, SELECT ON SEQUENCE worker_log_entries_id_seq TO metiquo_worker;
        END IF;
    END $$""")


def downgrade() -> None:
    op.drop_index("ix_worker_logs_recorded_at", table_name="worker_log_entries")
    op.drop_index("ix_worker_logs_run_id", table_name="worker_log_entries")
    op.drop_index("ix_worker_logs_worker_id", table_name="worker_log_entries")
    op.drop_table("worker_log_entries")
