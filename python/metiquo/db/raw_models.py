"""Modèle PostgreSQL de provenance pour les données brutes Oracle's Elixir."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from metiquo.db.base import Base, IdentityTimestampMixin, UtcDateTime

RAW_SCHEMA = "raw"


class SourceCatalog(IdentityTimestampMixin, Base):
    """Référence annuelle officielle, découverte ou amorcée explicitement."""

    __tablename__ = "source_catalog"
    __table_args__ = (
        CheckConstraint("year BETWEEN 2014 AND 2200", name="year_range"),
        CheckConstraint(
            "origin IN ('discovered', 'validated-bootstrap', 'manual')",
            name="origin",
        ),
        CheckConstraint(
            "status IN ('active', 'superseded', 'ambiguous', 'missing', 'unreachable')",
            name="status",
        ),
        CheckConstraint(
            "payload_sha256 IS NULL OR payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="payload_sha256",
        ),
        CheckConstraint(
            "last_confirmed_at IS NULL OR last_confirmed_at >= discovered_at",
            name="confirmation_time",
        ),
        UniqueConstraint(
            "provider", "dataset", "year", "source_file_id", name="uq_source_catalog_source"
        ),
        Index(
            "uq_source_catalog_active_year",
            "provider",
            "dataset",
            "year",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        {"schema": RAW_SCHEMA},
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    payload_sha256: Mapped[str | None] = mapped_column(String(64))
    mutable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())


class Snapshot(Base):
    """Objet source adressé par contenu et immuable après validation."""

    __tablename__ = "snapshots"
    __table_args__ = (
        CheckConstraint("year BETWEEN 2014 AND 2200", name="year_range"),
        CheckConstraint(
            "status IN ('received', 'validating', 'validated', 'quarantined', 'failed')",
            name="status",
        ),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
        CheckConstraint("byte_size >= 0", name="byte_size"),
        CheckConstraint(
            "(status = 'validated' AND validated_at IS NOT NULL AND failure_reason IS NULL) "
            "OR (status <> 'validated' AND validated_at IS NULL)",
            name="validation_state",
        ),
        UniqueConstraint("source_catalog_id", "sha256", name="uq_snapshots_catalog_hash"),
        UniqueConstraint("object_key", name="uq_snapshots_object_key"),
        {"schema": RAW_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_catalog_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.source_catalog.id", ondelete="RESTRICT"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    failure_reason: Mapped[str | None] = mapped_column(Text)
    manifest: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class IngestionRun(Base):
    """Tentative auditable de découverte, téléchargement, validation ou chargement."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(
            "run_kind IN ('catalog', 'backfill', 'sync', 'verify', 'load')", name="run_kind"
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="status",
        ),
        CheckConstraint("attempt >= 1", name="attempt"),
        CheckConstraint(
            "request_key_hash IS NULL OR request_key_hash ~ '^[0-9a-f]{64}$'",
            name="request_key_hash",
        ),
        CheckConstraint(
            "(status IN ('queued', 'running') AND finished_at IS NULL) "
            "OR (status IN ('succeeded', 'failed', 'cancelled') AND finished_at IS NOT NULL)",
            name="finished_state",
        ),
        UniqueConstraint("request_key_hash", name="uq_ingestion_runs_request_key_hash"),
        {"schema": RAW_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_catalog_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.source_catalog.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("raw.snapshots.id", ondelete="RESTRICT")
    )
    run_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    transport: Mapped[str | None] = mapped_column(String(64))
    request_key_hash: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_detail: Mapped[str | None] = mapped_column(Text)
    counters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class QualityIssue(Base):
    """Anomalie structurée rattachée à une exécution et, si connu, à un snapshot."""

    __tablename__ = "quality_issues"
    __table_args__ = (
        CheckConstraint("severity IN ('blocking', 'capability-only', 'warning')", name="severity"),
        CheckConstraint("row_number IS NULL OR row_number >= 1", name="row_number"),
        {"schema": RAW_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("raw.snapshots.id", ondelete="RESTRICT")
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    capability: Mapped[str | None] = mapped_column(String(128))
    row_number: Mapped[int | None] = mapped_column(BigInteger)
    natural_key: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )


class QuarantineItem(Base):
    """Objet écarté sans perte, avec décision de résolution explicitement auditée."""

    __tablename__ = "quarantine_items"
    __table_args__ = (
        CheckConstraint("payload_sha256 ~ '^[0-9a-f]{64}$'", name="payload_sha256"),
        CheckConstraint("status IN ('pending', 'accepted', 'rejected')", name="status"),
        CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL AND resolved_by IS NULL) "
            "OR (status IN ('accepted', 'rejected') AND resolved_at IS NOT NULL "
            "AND resolved_by IS NOT NULL)",
            name="resolution_state",
        ),
        UniqueConstraint("snapshot_id", name="uq_quarantine_items_snapshot_id"),
        UniqueConstraint("object_key", name="uq_quarantine_items_object_key"),
        {"schema": RAW_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    diagnostic: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    quarantined_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    resolution_reason: Mapped[str | None] = mapped_column(Text)


class RowRevision(Base):
    """Révision append-only d'une ligne naturelle provenant d'un snapshot."""

    __tablename__ = "row_revisions"
    __table_args__ = (
        CheckConstraint("row_hash ~ '^[0-9a-f]{64}$'", name="row_hash"),
        CheckConstraint("revision >= 1", name="revision"),
        CheckConstraint("operation IN ('inserted', 'updated')", name="operation"),
        CheckConstraint(
            "(revision = 1 AND previous_revision_id IS NULL) "
            "OR (revision > 1 AND previous_revision_id IS NOT NULL)",
            name="revision_chain",
        ),
        UniqueConstraint(
            "provider", "dataset", "natural_key", "revision", name="uq_row_revisions_revision"
        ),
        UniqueConstraint(
            "provider", "dataset", "natural_key", "row_hash", name="uq_row_revisions_hash"
        ),
        {"schema": RAW_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    natural_key: Mapped[str] = mapped_column(Text, nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_revision_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("raw.row_revisions.id", ondelete="RESTRICT")
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )
