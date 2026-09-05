"""Créer l'état durable des backfills multi-années.

Revision ID: 20260906_0008
Revises: 20260906_0007
Create Date: 2026-09-06 01:10:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0008"
down_revision: str | None = "20260906_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RAW_SCHEMA = "raw"
SHA256_PATTERN = "^[0-9a-f]{64}$"


def upgrade() -> None:
    """Créer un job unique et ses checkpoints annuels."""

    op.create_table(
        "backfill_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("dataset", sa.String(length=128), nullable=False),
        sa.Column("from_year", sa.Integer(), nullable=False),
        sa.Column("to_year", sa.Integer(), nullable=False),
        sa.Column("request_key_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "from_year BETWEEN 2014 AND 2200 AND to_year BETWEEN from_year AND 2200",
            name="ck_backfill_jobs_year_range",
        ),
        sa.CheckConstraint(
            f"request_key_hash ~ '{SHA256_PATTERN}'",
            name="ck_backfill_jobs_request_key_hash",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="ck_backfill_jobs_status",
        ),
        sa.CheckConstraint(
            "(status = 'running' AND finished_at IS NULL) OR "
            "(status IN ('succeeded', 'failed') AND finished_at IS NOT NULL)",
            name="ck_backfill_jobs_finished_state",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_backfill_jobs"),
        sa.UniqueConstraint("request_key_hash", name="uq_backfill_jobs_request_key_hash"),
        schema=RAW_SCHEMA,
    )
    op.create_table(
        "backfill_years",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("year BETWEEN 2014 AND 2200", name="ck_backfill_years_year"),
        sa.CheckConstraint("attempts >= 0", name="ck_backfill_years_attempts"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_backfill_years_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND started_at IS NULL AND finished_at IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status IN ('succeeded', 'failed') AND started_at IS NOT NULL "
            "AND finished_at IS NOT NULL)",
            name="ck_backfill_years_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["raw.backfill_jobs.id"],
            name="fk_backfill_years_job_id_backfill_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["last_run_id"],
            ["raw.ingestion_runs.id"],
            name="fk_backfill_years_last_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_backfill_years"),
        sa.UniqueConstraint("job_id", "year", name="uq_backfill_years_job_year"),
        schema=RAW_SCHEMA,
    )


def downgrade() -> None:
    """Supprimer checkpoints puis jobs."""

    op.drop_table("backfill_years", schema=RAW_SCHEMA)
    op.drop_table("backfill_jobs", schema=RAW_SCHEMA)
