"""Modèles de persistance du domaine features."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from metiquo.db.base import Base, UtcDateTime

FEATURES_SCHEMA = "features"


class FeatureInvalidation(Base):
    """Plage de features à reconstruire après des révisions source."""

    __tablename__ = "invalidations"
    __table_args__ = (
        CheckConstraint("changed_through >= affected_from", name="date_range"),
        CheckConstraint("revision_count >= 1", name="revision_count"),
        UniqueConstraint("source_run_id", name="uq_invalidations_source_run_id"),
        Index("ix_invalidations_affected_from", "affected_from"),
        {"schema": FEATURES_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_snapshot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    affected_from: Mapped[date] = mapped_column(nullable=False)
    changed_through: Mapped[date] = mapped_column(nullable=False)
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )
