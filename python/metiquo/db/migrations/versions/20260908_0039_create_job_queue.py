"""Créer une file de jobs PostgreSQL avec baux d'exécution.

Revision ID: 20260908_0039
Revises: 20260908_0038
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260908_0039"
down_revision: str | None = "20260908_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_fingerprint", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("owner", sa.String(255)),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True)),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled','dead')", name="status"
        ),
        sa.CheckConstraint(
            "attempt >= 0 AND max_attempts BETWEEN 1 AND 20 AND attempt <= max_attempts",
            name="attempts",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND jsonb_typeof(result) = 'object'", name="documents"
        ),
        sa.CheckConstraint(
            "idempotency_fingerprint ~ '^[0-9a-f]{64}$' AND request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="fingerprints",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL "
            "AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status <> 'running' AND owner IS NULL AND lease_token IS NULL "
            "AND lease_expires_at IS NULL)",
            name="ownership",
        ),
        sa.CheckConstraint(
            "(status IN ('succeeded','failed','cancelled','dead')) = (finished_at IS NOT NULL)",
            name="terminal_time",
        ),
        sa.UniqueConstraint("idempotency_fingerprint", name="uq_ops_jobs_idempotency"),
        schema="ops",
    )
    op.create_index("ix_ops_jobs_claim", "jobs", ["status", "scheduled_at", "id"], schema="ops")
    op.create_index("ix_ops_jobs_lease", "jobs", ["status", "lease_expires_at"], schema="ops")
    op.execute("""
        CREATE FUNCTION ops.prevent_job_request_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'job history cannot be deleted'; END IF;
          IF (NEW.id, NEW.job_type, NEW.scope, NEW.payload, NEW.actor, NEW.trace_id,
              NEW.idempotency_fingerprint, NEW.request_fingerprint,
              NEW.created_at, NEW.max_attempts)
             IS DISTINCT FROM
             (OLD.id, OLD.job_type, OLD.scope, OLD.payload, OLD.actor, OLD.trace_id,
              OLD.idempotency_fingerprint, OLD.request_fingerprint,
              OLD.created_at, OLD.max_attempts)
          THEN RAISE EXCEPTION 'job request is immutable'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_jobs_request_immutable BEFORE UPDATE OR DELETE ON ops.jobs
        FOR EACH ROW EXECUTE FUNCTION ops.prevent_job_request_mutation();
    """)


def downgrade() -> None:
    op.drop_table("jobs", schema="ops")
    op.execute("DROP FUNCTION ops.prevent_job_request_mutation()")
