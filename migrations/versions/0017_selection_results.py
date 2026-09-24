"""Revisable public selection outcomes with immutable decision evidence.

Revision ID: 0017
Revises: 0016
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op
from croniter import croniter
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bookmaker_selection_results",
        sa.Column(
            "selection_id", sa.Uuid(), sa.ForeignKey("bookmaker_selections.id"), primary_key=True
        ),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("bookmaker_events.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("market_kind", sa.String(), nullable=False),
        sa.Column("map_number", sa.Integer()),
        sa.Column("picked_team_id", sa.String(), sa.ForeignKey("teams.id")),
        sa.Column("source", sa.String()),
        sa.Column("source_snapshot_id", sa.Uuid(), sa.ForeignKey("match_snapshots.id")),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'won', 'lost', 'void')"),
        sa.CheckConstraint("market_kind IN ('match_winner', 'map_winner')"),
        sa.CheckConstraint(
            "(market_kind = 'match_winner' AND map_number IS NULL) OR "
            "(market_kind = 'map_winner' AND map_number BETWEEN 1 AND 5)"
        ),
    )
    op.create_index(
        "ix_bookmaker_selection_results_event_id", "bookmaker_selection_results", ["event_id"]
    )
    op.create_table(
        "bookmaker_selection_result_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "selection_id", sa.Uuid(), sa.ForeignKey("bookmaker_selections.id"), nullable=False
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("evidence", JSONB(), nullable=False),
    )
    op.create_index(
        "ix_bookmaker_selection_result_decisions_selection_id",
        "bookmaker_selection_result_decisions",
        ["selection_id"],
    )
    op.execute("""CREATE TRIGGER keep_selection_result_evidence
      BEFORE UPDATE OR DELETE ON bookmaker_selection_result_decisions
      FOR EACH ROW EXECUTE FUNCTION keep_match_evidence()""")
    now = datetime.now(UTC)
    cron = "* * * * *"
    op.get_bind().execute(
        sa.text("""INSERT INTO script_schedules (id, cron, timezone, enabled, next_run_at, revision)
          VALUES ('settle-selections', :cron, 'Europe/Paris', true, :next_run, 1)
          ON CONFLICT (id) DO NOTHING"""),
        {
            "cron": cron,
            "next_run": croniter(cron, now.astimezone(ZoneInfo("Europe/Paris"))).get_next(datetime),
        },
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT FROM pg_roles WHERE rolname='metiquo_api') THEN
        GRANT SELECT ON bookmaker_selection_results, bookmaker_selection_result_decisions
          TO metiquo_api;
      END IF;
      IF EXISTS (SELECT FROM pg_roles WHERE rolname='metiquo_worker') THEN
        GRANT SELECT, INSERT, UPDATE ON bookmaker_selection_results TO metiquo_worker;
        GRANT SELECT, INSERT ON bookmaker_selection_result_decisions TO metiquo_worker;
        GRANT USAGE, SELECT ON SEQUENCE bookmaker_selection_result_decisions_id_seq
          TO metiquo_worker;
        REVOKE UPDATE, DELETE ON bookmaker_selection_result_decisions FROM metiquo_worker;
        REVOKE DELETE ON bookmaker_selection_results FROM metiquo_worker;
      END IF;
    END $$""")


def downgrade() -> None:
    op.execute("DELETE FROM script_runs WHERE script_id='settle-selections'")
    op.execute("DELETE FROM script_schedules WHERE id='settle-selections'")
    op.drop_table("bookmaker_selection_result_decisions")
    op.drop_table("bookmaker_selection_results")
