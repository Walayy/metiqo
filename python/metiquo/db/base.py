"""Conventions SQLAlchemy partagées par les futurs modèles persistés."""

from datetime import datetime
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from metiquo.foundation.time import normalize_utc_datetime

NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class UtcDateTime(TypeDecorator[datetime]):
    """Persister seulement des instants conscients et les normaliser en UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        del dialect
        if value is None:
            return None
        return normalize_utc_datetime(value)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("PostgreSQL a renvoyé un datetime sans fuseau")
        return normalize_utc_datetime(value)


class Base(DeclarativeBase):
    """Base déclarative unique avec noms de contraintes déterministes."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdentityTimestampMixin:
    """Convention UUID et timestamps UTC pour les entités modifiables."""

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, server_default=func.now(), onupdate=func.now()
    )
