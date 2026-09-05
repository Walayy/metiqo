"""Aliases fournisseurs datés vers les dimensions canoniques."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, Numeric, String, Text, func, literal_column
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from metiquo.db.base import Base, UtcDateTime

CORE_SCHEMA = "core"


class EntityAlias(Base):
    """Liaison explicite et temporelle entre un libellé source et une entité canonique."""

    __tablename__ = "entity_aliases"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    canonical_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(UtcDateTime())
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('team', 'competition', 'player')",
            name="entity_type",
        ),
        CheckConstraint("length(trim(provider)) > 0", name="provider"),
        CheckConstraint("length(trim(raw_alias)) > 0", name="raw_alias"),
        CheckConstraint("length(trim(normalized_alias)) > 0", name="normalized_alias"),
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="validity"),
        CheckConstraint("source IN ('auto', 'seeded', 'manual')", name="source"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence"),
        CheckConstraint(
            "(approved_by IS NULL) = (approved_at IS NULL)",
            name="approval_pair",
        ),
        CheckConstraint(
            "source <> 'manual' OR approved_by IS NOT NULL",
            name="manual_approval",
        ),
        ExcludeConstraint(
            (entity_type, "="),
            (provider, "="),
            (normalized_alias, "="),
            (
                func.tstzrange(valid_from, valid_to, literal_column("'[)'")),
                "&&",
            ),
            name="ex_core_entity_aliases_temporal_identity",
            using="gist",
        ),
        Index(
            "ix_core_entity_aliases_canonical_validity",
            "entity_type",
            "canonical_id",
            "valid_from",
            "valid_to",
        ),
        {"schema": CORE_SCHEMA},
    )
