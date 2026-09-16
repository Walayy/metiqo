"""Administrator users, durable schedules, queue and audit.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op
from croniter import croniter

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_users", sa.Column("disabled", sa.Boolean(), server_default="false", nullable=False)
    )
    schedules = op.create_table(
        "script_schedules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("cron", sa.String(100), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "script_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("script_id", sa.String(), sa.ForeignKey("script_schedules.id"), nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("ingestion_run_id", sa.Uuid(), sa.ForeignKey("ingestion_runs.id")),
        sa.Column("error", sa.String()),
        sa.CheckConstraint("trigger IN ('manual', 'schedule')"),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')"),
    )
    op.create_index("ix_script_runs_requested", "script_runs", ["script_id", "requested_at"])
    op.create_index(
        "uq_script_runs_active",
        "script_runs",
        ["script_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "worker_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "scripts",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
    )
    op.create_table(
        "admin_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("app_users.id"), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("details", sa.dialects.postgresql.JSONB(), nullable=False),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        schedules,
        [
            {
                "id": key,
                "cron": cron,
                "timezone": "Europe/Paris",
                "enabled": True,
                "next_run_at": croniter(cron, now.astimezone(ZoneInfo("Europe/Paris"))).get_next(
                    datetime
                ),
                "revision": 1,
            }
            for key, cron in {
                "lol-catalog": "0 4 * * *",
                "oracle-latest": "0 */6 * * *",
                "oracle-full": "0 3 * * 0",
            }.items()
        ],
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_api') THEN
        GRANT UPDATE (role, disabled) ON app_users TO metiquo_api;
        GRANT SELECT ON script_schedules, script_runs, worker_status, admin_audit TO metiquo_api;
        GRANT UPDATE (cron, timezone, enabled, next_run_at, revision)
          ON script_schedules TO metiquo_api;
        GRANT INSERT (id, script_id, trigger, status, requested_at, available_at)
          ON script_runs TO metiquo_api;
        GRANT INSERT ON admin_audit TO metiquo_api;
      END IF;
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_worker') THEN
        GRANT SELECT, INSERT, UPDATE
          ON script_schedules, script_runs, worker_status TO metiquo_worker;
        REVOKE ALL ON admin_audit FROM metiquo_worker;
      END IF;
    END $$""")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_api') THEN
        REVOKE UPDATE (role, disabled) ON app_users FROM metiquo_api;
      END IF;
    END $$""")
    for table in ("admin_audit", "worker_status", "script_runs", "script_schedules"):
        op.drop_table(table)
    op.drop_column("app_users", "disabled")
