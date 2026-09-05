"""Créer les jobs et audits des mutations de modèles.

Revision ID: 20260907_0026
Revises: 20260907_0025
Create Date: 2026-09-07 07:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260907_0026"
down_revision: str | None = "20260907_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persister l'état des jobs et une trace immuable de chaque demande."""

    op.create_table(
        "model_action_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("action IN ('train', 'promote', 'retire')", name="action"),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="status"),
        sa.CheckConstraint("length(trim(name)) > 0", name="name"),
        sa.CheckConstraint("request_fingerprint ~ '^[0-9a-f]{64}$'", name="request_fingerprint"),
        sa.CheckConstraint(
            "idempotency_fingerprint ~ '^[0-9a-f]{64}$'",
            name="idempotency_fingerprint",
        ),
        sa.CheckConstraint("jsonb_typeof(request_payload) = 'object'", name="request_object"),
        sa.CheckConstraint("jsonb_typeof(result_payload) = 'object'", name="result_object"),
        sa.CheckConstraint("jsonb_typeof(error_payload) = 'object'", name="error_object"),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL) OR "
            "(status IN ('succeeded', 'failed') AND finished_at IS NOT NULL)",
            name="finished_status",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["ml.model_versions.id"],
            name="fk_ml_model_action_jobs_model",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_model_action_jobs"),
        sa.UniqueConstraint("request_fingerprint", name="uq_ml_model_action_jobs_request"),
        sa.UniqueConstraint(
            "action",
            "idempotency_fingerprint",
            name="uq_ml_model_action_jobs_idempotency",
        ),
        schema="ml",
    )
    op.create_table(
        "model_action_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('model.train', 'model.promote', 'model.retire')",
            name="action",
        ),
        sa.CheckConstraint("length(trim(resource_id)) > 0", name="resource_id"),
        sa.CheckConstraint(
            "idempotency_fingerprint ~ '^[0-9a-f]{64}$'",
            name="idempotency_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ml.model_action_jobs.id"],
            name="fk_ml_model_action_audits_job",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_model_action_audits"),
        sa.UniqueConstraint("job_id", name="uq_ml_model_action_audits_job"),
        schema="ml",
    )
    op.execute("ALTER TABLE ml.model_status_events DROP CONSTRAINT ck_model_status_events_action")
    op.create_check_constraint(
        "action",
        "model_status_events",
        "action IN ('promote', 'retire', 'retire_for_promotion', 'rollback', "
        "'retire_for_rollback', 'block')",
        schema="ml",
    )
    op.execute(
        """
        CREATE TRIGGER trg_model_action_audits_prevent_mutation
        BEFORE UPDATE OR DELETE ON ml.model_action_audits
        FOR EACH ROW EXECUTE FUNCTION ml.prevent_model_lifecycle_mutation()
        """
    )


def downgrade() -> None:
    """Retirer les jobs/audits et restaurer les actions du cycle précédent."""

    op.execute("DROP TRIGGER trg_model_action_audits_prevent_mutation ON ml.model_action_audits")
    op.execute("ALTER TABLE ml.model_status_events DROP CONSTRAINT ck_model_status_events_action")
    op.execute(
        "ALTER TABLE ml.model_status_events "
        "ADD CONSTRAINT ck_model_status_events_action "
        "CHECK (action IN ('promote', 'retire_for_promotion', 'rollback', "
        "'retire_for_rollback', 'block')) NOT VALID"
    )
    op.drop_table("model_action_audits", schema="ml")
    op.drop_table("model_action_jobs", schema="ml")
