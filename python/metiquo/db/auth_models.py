"""Identité Owner unique et sessions opaques sous forme d'empreintes."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from metiquo.db.base import Base, UtcDateTime


class HttpRateLimitRecord(Base):
    __tablename__ = "http_rate_limits"
    __table_args__ = (CheckConstraint("attempts >= 1", name="attempts"), {"schema": "ops"})

    bucket: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    attempts: Mapped[int] = mapped_column(nullable=False)


class OwnerAccountRecord(Base):
    __tablename__ = "owner_accounts"
    __table_args__ = (
        CheckConstraint("singleton", name="singleton"),
        CheckConstraint("revision >= 1", name="revision"),
        UniqueConstraint("singleton", name="uq_owner_singleton"),
        {"schema": "ops"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    singleton: Mapped[bool] = mapped_column(Boolean, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(1024), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class OwnerSessionRecord(Base):
    __tablename__ = "owner_sessions"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash"),
        CheckConstraint("status IN ('active','revoked')", name="status"),
        CheckConstraint("(status = 'revoked') = (revoked_at IS NOT NULL)", name="revocation"),
        CheckConstraint("expires_at > created_at AND last_seen_at >= created_at", name="times"),
        UniqueConstraint("token_hash", name="uq_owner_session_token_hash"),
        {"schema": "ops"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("ops.owner_accounts.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    rotate_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    reason_code: Mapped[str | None] = mapped_column(String(64))
    replacement_id: Mapped[UUID | None] = mapped_column(ForeignKey("ops.owner_sessions.id"))
    grace_until: Mapped[datetime | None] = mapped_column(UtcDateTime())
