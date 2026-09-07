"""Relier les relances à leur requête originale sans réécrire l'historique.

Revision ID: 20260908_0040
Revises: 20260908_0039
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260908_0040"
down_revision: str | None = "20260908_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("rerun_of", postgresql.UUID(as_uuid=True), sa.ForeignKey("ops.jobs.id")),
        schema="ops",
    )
    op.add_column("jobs", sa.Column("reason", sa.String(400)), schema="ops")
    op.execute("""
      CREATE FUNCTION ops.prevent_job_rerun_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF (NEW.rerun_of, NEW.reason) IS DISTINCT FROM (OLD.rerun_of, OLD.reason)
        THEN RAISE EXCEPTION 'job rerun request is immutable'; END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER trg_jobs_rerun_immutable BEFORE UPDATE ON ops.jobs
      FOR EACH ROW EXECUTE FUNCTION ops.prevent_job_rerun_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_jobs_rerun_immutable ON ops.jobs")
    op.execute("DROP FUNCTION ops.prevent_job_rerun_mutation()")
    op.drop_column("jobs", "reason", schema="ops")
    op.drop_column("jobs", "rerun_of", schema="ops")
