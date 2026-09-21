"""Retire the old live collector and schedule LoLTV without rewriting evidence."""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE script_schedules SET enabled = false WHERE id = 'sofascore-matches'")
    op.execute("""UPDATE script_runs SET status = 'interrupted', finished_at = now(),
        error = 'Collecteur remplacé par LoLTV.'
        WHERE script_id = 'sofascore-matches' AND status IN ('queued', 'running')""")
    op.execute("""INSERT INTO script_schedules
        (id, cron, timezone, enabled, next_run_at, revision)
        VALUES ('loltv-matches', '* * * * *', 'Europe/Paris', true,
                date_trunc('minute', now()) + interval '1 minute', 1)
        ON CONFLICT (id) DO NOTHING""")


def downgrade() -> None:
    # Keep execution history and never reactivate a retired network collector automatically.
    op.execute("UPDATE script_schedules SET enabled = false WHERE id = 'loltv-matches'")
