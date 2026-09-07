"""File PostgreSQL avec requêtes stables et propriété temporaire des exécutions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from metiquo.db.base import Base, UtcDateTime


class BackupRunRecord(Base):
    __tablename__ = "backup_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running','succeeded','failed')", name="status"),
        CheckConstraint("(status = 'running') = (finished_at IS NULL)", name="finished_state"),
        CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="times"),
        CheckConstraint("sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
        CheckConstraint("status <> 'succeeded' OR sha256 IS NOT NULL", name="success_proof"),
        Index("ix_backup_runs_repository", "repository_fingerprint", "started_at"),
        {"schema": "ops"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    repository_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    sha256: Mapped[str | None] = mapped_column(String(64))
    encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    retained: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))


class AlertStateRecord(Base):
    __tablename__ = "alert_states"
    __table_args__ = (
        CheckConstraint("jsonb_typeof(details) = 'object'", name="details_object"),
        CheckConstraint(
            "changed_at <= observed_at AND last_notified_at <= observed_at", name="times"
        ),
        {"schema": "ops"},
    )
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    last_notified_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(before_refs) = 'object' AND jsonb_typeof(after_refs) = 'object'",
            name="references",
        ),
        CheckConstraint("length(trim(actor)) > 0 AND length(trim(action)) > 0", name="identity"),
        Index("ix_ops_audit_target", "target_type", "target_id", "occurred_at"),
        Index("ix_ops_audit_trace", "trace_id", "occurred_at"),
        {"schema": "ops"},
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    before_refs: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    after_refs: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    trace_id: Mapped[UUID] = mapped_column(nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class JobRecord(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled','dead')", name="status"
        ),
        CheckConstraint(
            "attempt >= 0 AND max_attempts BETWEEN 1 AND 20 AND attempt <= max_attempts",
            name="attempts",
        ),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object' AND jsonb_typeof(result) = 'object'", name="documents"
        ),
        CheckConstraint(
            "idempotency_fingerprint ~ '^[0-9a-f]{64}$' AND request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="fingerprints",
        ),
        CheckConstraint(
            "(status = 'running' AND owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL "
            "AND started_at IS NOT NULL AND finished_at IS NULL) OR "
            "(status <> 'running' AND owner IS NULL AND lease_token IS NULL "
            "AND lease_expires_at IS NULL)",
            name="ownership",
        ),
        CheckConstraint(
            "(status IN ('succeeded','failed','cancelled','dead')) = (finished_at IS NOT NULL)",
            name="terminal_time",
        ),
        UniqueConstraint("idempotency_fingerprint", name="uq_ops_jobs_idempotency"),
        Index("ix_ops_jobs_claim", "status", "scheduled_at", "id"),
        Index("ix_ops_jobs_lease", "status", "lease_expires_at"),
        {"schema": "ops"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    trace_id: Mapped[UUID] = mapped_column(nullable=False)
    idempotency_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(nullable=False)
    max_attempts: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    heartbeat_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    lease_expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    owner: Mapped[str | None] = mapped_column(String(255))
    lease_token: Mapped[UUID | None] = mapped_column()
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    rerun_of: Mapped[UUID | None] = mapped_column(ForeignKey("ops.jobs.id"))
    reason: Mapped[str | None] = mapped_column(String(400))
