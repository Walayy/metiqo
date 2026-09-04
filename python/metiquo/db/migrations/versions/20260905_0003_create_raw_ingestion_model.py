"""Créer le modèle raw de provenance et de qualité.

Revision ID: 20260905_0003
Revises: 20260904_0002
Create Date: 2026-09-05 10:00:00+00:00
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0003"
down_revision: str | None = "20260904_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RAW_SCHEMA = "raw"
SHA256_PATTERN = "^[0-9a-f]{64}$"


def _timestamps(*, updated: bool = False) -> list[sa.Column[Any]]:
    columns: list[sa.Column[Any]] = [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        )
    ]
    if updated:
        columns.append(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            )
        )
    return columns


def upgrade() -> None:
    """Créer les tables, liens et garde-fous de la zone raw."""

    op.create_table(
        "source_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("dataset", sa.String(length=128), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("source_file_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=True),
        sa.Column("mutable", sa.Boolean(), server_default=sa.false(), nullable=False),
        *_timestamps(updated=True),
        sa.CheckConstraint("year BETWEEN 2014 AND 2200", name="ck_source_catalog_year_range"),
        sa.CheckConstraint(
            "origin IN ('discovered', 'validated-bootstrap', 'manual')",
            name="ck_source_catalog_origin",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'ambiguous', 'missing', 'unreachable')",
            name="ck_source_catalog_status",
        ),
        sa.CheckConstraint(
            f"payload_sha256 IS NULL OR payload_sha256 ~ '{SHA256_PATTERN}'",
            name="ck_source_catalog_payload_sha256",
        ),
        sa.CheckConstraint(
            "last_confirmed_at IS NULL OR last_confirmed_at >= discovered_at",
            name="ck_source_catalog_confirmation_time",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_catalog"),
        sa.UniqueConstraint(
            "provider",
            "dataset",
            "year",
            "source_file_id",
            name="uq_source_catalog_source",
        ),
        schema=RAW_SCHEMA,
    )
    op.create_index(
        "uq_source_catalog_active_year",
        "source_catalog",
        ["provider", "dataset", "year"],
        unique=True,
        schema=RAW_SCHEMA,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_catalog_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("source_file_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "manifest", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        *_timestamps(),
        sa.CheckConstraint("year BETWEEN 2014 AND 2200", name="ck_snapshots_year_range"),
        sa.CheckConstraint(
            "status IN ('received', 'validating', 'validated', 'quarantined', 'failed')",
            name="ck_snapshots_status",
        ),
        sa.CheckConstraint(f"sha256 ~ '{SHA256_PATTERN}'", name="ck_snapshots_sha256"),
        sa.CheckConstraint("byte_size >= 0", name="ck_snapshots_byte_size"),
        sa.CheckConstraint(
            "(status = 'validated' AND validated_at IS NOT NULL AND failure_reason IS NULL) "
            "OR (status <> 'validated' AND validated_at IS NULL)",
            name="ck_snapshots_validation_state",
        ),
        sa.ForeignKeyConstraint(
            ["source_catalog_id"],
            ["raw.source_catalog.id"],
            name="fk_snapshots_source_catalog_id_source_catalog",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_snapshots"),
        sa.UniqueConstraint("source_catalog_id", "sha256", name="uq_snapshots_catalog_hash"),
        sa.UniqueConstraint("object_key", name="uq_snapshots_object_key"),
        schema=RAW_SCHEMA,
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_catalog_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("transport", sa.String(length=64), nullable=True),
        sa.Column("request_key_hash", sa.String(length=64), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "counters", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "run_kind IN ('catalog', 'backfill', 'sync', 'verify', 'load')",
            name="ck_ingestion_runs_run_kind",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_ingestion_runs_status",
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_ingestion_runs_attempt"),
        sa.CheckConstraint(
            f"request_key_hash IS NULL OR request_key_hash ~ '{SHA256_PATTERN}'",
            name="ck_ingestion_runs_request_key_hash",
        ),
        sa.CheckConstraint(
            "(status IN ('queued', 'running') AND finished_at IS NULL) "
            "OR (status IN ('succeeded', 'failed', 'cancelled') AND finished_at IS NOT NULL)",
            name="ck_ingestion_runs_finished_state",
        ),
        sa.ForeignKeyConstraint(
            ["source_catalog_id"],
            ["raw.source_catalog.id"],
            name="fk_ingestion_runs_source_catalog_id_source_catalog",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_ingestion_runs_snapshot_id_snapshots",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_runs"),
        sa.UniqueConstraint("request_key_hash", name="uq_ingestion_runs_request_key_hash"),
        schema=RAW_SCHEMA,
    )

    op.create_table(
        "quality_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("capability", sa.String(length=128), nullable=True),
        sa.Column("row_number", sa.BigInteger(), nullable=True),
        sa.Column("natural_key", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "context", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        *_timestamps(),
        sa.CheckConstraint(
            "severity IN ('blocking', 'capability-only', 'warning')",
            name="ck_quality_issues_severity",
        ),
        sa.CheckConstraint(
            "row_number IS NULL OR row_number >= 1", name="ck_quality_issues_row_number"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["raw.ingestion_runs.id"],
            name="fk_quality_issues_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_quality_issues_snapshot_id_snapshots",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quality_issues"),
        schema=RAW_SCHEMA,
    )

    op.create_table(
        "quarantine_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "diagnostic", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"payload_sha256 ~ '{SHA256_PATTERN}'", name="ck_quarantine_items_payload_sha256"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')", name="ck_quarantine_items_status"
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL AND resolved_by IS NULL) "
            "OR (status IN ('accepted', 'rejected') AND resolved_at IS NOT NULL "
            "AND resolved_by IS NOT NULL)",
            name="ck_quarantine_items_resolution_state",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_quarantine_items_snapshot_id_snapshots",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["raw.ingestion_runs.id"],
            name="fk_quarantine_items_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quarantine_items"),
        sa.UniqueConstraint("snapshot_id", name="uq_quarantine_items_snapshot_id"),
        sa.UniqueConstraint("object_key", name="uq_quarantine_items_object_key"),
        schema=RAW_SCHEMA,
    )

    op.create_table(
        "row_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("dataset", sa.String(length=128), nullable=False),
        sa.Column("natural_key", sa.Text(), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("previous_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(f"row_hash ~ '{SHA256_PATTERN}'", name="ck_row_revisions_row_hash"),
        sa.CheckConstraint("revision >= 1", name="ck_row_revisions_revision"),
        sa.CheckConstraint(
            "operation IN ('inserted', 'updated')", name="ck_row_revisions_operation"
        ),
        sa.CheckConstraint(
            "(revision = 1 AND previous_revision_id IS NULL) "
            "OR (revision > 1 AND previous_revision_id IS NOT NULL)",
            name="ck_row_revisions_revision_chain",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["raw.snapshots.id"],
            name="fk_row_revisions_snapshot_id_snapshots",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["raw.ingestion_runs.id"],
            name="fk_row_revisions_run_id_ingestion_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_revision_id"],
            ["raw.row_revisions.id"],
            name="fk_row_revisions_previous_revision_id_row_revisions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_row_revisions"),
        sa.UniqueConstraint(
            "provider",
            "dataset",
            "natural_key",
            "revision",
            name="uq_row_revisions_revision",
        ),
        sa.UniqueConstraint(
            "provider", "dataset", "natural_key", "row_hash", name="uq_row_revisions_hash"
        ),
        schema=RAW_SCHEMA,
    )

    op.execute(
        """
        CREATE FUNCTION raw.prevent_validated_snapshot_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF OLD.status = 'validated' THEN
            RAISE EXCEPTION 'validated snapshot % is immutable', OLD.id
              USING ERRCODE = '55000';
          END IF;
          RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_snapshots_prevent_validated_mutation
        BEFORE UPDATE OR DELETE ON raw.snapshots
        FOR EACH ROW EXECUTE FUNCTION raw.prevent_validated_snapshot_mutation()
        """
    )


def downgrade() -> None:
    """Supprimer le modèle raw dans l'ordre inverse des dépendances."""

    op.execute("DROP TRIGGER trg_snapshots_prevent_validated_mutation ON raw.snapshots")
    op.execute("DROP FUNCTION raw.prevent_validated_snapshot_mutation()")
    op.drop_table("row_revisions", schema=RAW_SCHEMA)
    op.drop_table("quarantine_items", schema=RAW_SCHEMA)
    op.drop_table("quality_issues", schema=RAW_SCHEMA)
    op.drop_table("ingestion_runs", schema=RAW_SCHEMA)
    op.drop_table("snapshots", schema=RAW_SCHEMA)
    op.drop_index("uq_source_catalog_active_year", table_name="source_catalog", schema=RAW_SCHEMA)
    op.drop_table("source_catalog", schema=RAW_SCHEMA)
