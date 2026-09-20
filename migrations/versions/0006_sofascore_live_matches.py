"""SofaScore scraped match links and immutable live snapshots.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op
from croniter import croniter
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    now = datetime.now(UTC)
    op.create_table(
        "match_source_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("match_id", sa.Uuid(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("source_names", postgresql.JSONB(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "source_id"),
    )
    op.create_index("ix_match_source_links_match", "match_source_links", ["match_id"])
    op.create_table(
        "match_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("match_id", sa.Uuid(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("match_id", "sha256"),
    )
    op.create_index("ix_match_snapshots_latest", "match_snapshots", ["match_id", "observed_at"])
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_api') THEN
        GRANT SELECT ON match_source_links, match_snapshots TO metiquo_api;
      END IF;
      IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'metiquo_worker') THEN
        GRANT SELECT, INSERT, UPDATE ON match_source_links TO metiquo_worker;
        GRANT SELECT, INSERT ON match_snapshots TO metiquo_worker;
        REVOKE UPDATE, DELETE ON match_snapshots FROM metiquo_worker;
      END IF;
    END $$""")
    schedules = sa.table(
        "script_schedules",
        sa.column("id", sa.String()),
        sa.column("cron", sa.String()),
        sa.column("timezone", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("next_run_at", sa.DateTime(timezone=True)),
        sa.column("revision", sa.Integer()),
    )
    op.bulk_insert(
        schedules,
        [
            {
                "id": "sofascore-matches",
                "cron": "*/1 * * * *",
                "timezone": "Europe/Paris",
                "enabled": True,
                "next_run_at": croniter(
                    "*/1 * * * *", now.astimezone(ZoneInfo("Europe/Paris"))
                ).get_next(datetime),
                "revision": 1,
            }
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM script_schedules WHERE id = 'sofascore-matches'")
    op.drop_index("ix_match_snapshots_latest", table_name="match_snapshots")
    op.drop_table("match_snapshots")
    op.drop_index("ix_match_source_links_match", table_name="match_source_links")
    op.drop_table("match_source_links")
