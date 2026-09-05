"""Modèles canoniques League of Legends dérivés exclusivement du raw Oracle's Elixir."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from metiquo.db.base import Base, UtcDateTime

CORE_SCHEMA = "core"


class CanonicalProvenanceMixin:
    """Trace minimale obligatoire vers la ligne raw validée source."""

    source_raw_row_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.canonical_rows.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_snapshot_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_run_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("raw.ingestion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_natural_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    transformation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)


class GameTitle(CanonicalProvenanceMixin, Base):
    __tablename__ = "game_titles"
    __table_args__ = (
        CheckConstraint("source_row_hash ~ '^[0-9a-f]{64}$'", name="source_row_hash"),
        CheckConstraint("source_row_revision >= 1", name="source_row_revision"),
        CheckConstraint("length(trim(transformation_version)) > 0", name="transformation_version"),
        UniqueConstraint("slug", name="uq_game_titles_slug"),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)


class Competition(CanonicalProvenanceMixin, Base):
    __tablename__ = "competitions"
    __table_args__ = (
        CheckConstraint("source_row_hash ~ '^[0-9a-f]{64}$'", name="source_row_hash"),
        CheckConstraint("source_row_revision >= 1", name="source_row_revision"),
        CheckConstraint("length(trim(transformation_version)) > 0", name="transformation_version"),
        UniqueConstraint(
            "game_title_id",
            "source_competition_id",
            name="uq_competitions_game_title_source_identity",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    game_title_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.game_titles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_competition_id: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))


class Team(CanonicalProvenanceMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (
        CheckConstraint("source_row_hash ~ '^[0-9a-f]{64}$'", name="source_row_hash"),
        CheckConstraint("source_row_revision >= 1", name="source_row_revision"),
        CheckConstraint("length(trim(transformation_version)) > 0", name="transformation_version"),
        CheckConstraint(
            "source_identity_kind IN ('teamid', 'teamname')", name="source_identity_kind"
        ),
        UniqueConstraint(
            "game_title_id",
            "source_team_id",
            name="uq_teams_game_title_source_identity",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    game_title_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.game_titles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_team_id: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    source_identity_kind: Mapped[str] = mapped_column(String(32), nullable=False)


class Player(CanonicalProvenanceMixin, Base):
    __tablename__ = "players"
    __table_args__ = (
        CheckConstraint("source_row_hash ~ '^[0-9a-f]{64}$'", name="source_row_hash"),
        CheckConstraint("source_row_revision >= 1", name="source_row_revision"),
        CheckConstraint("length(trim(transformation_version)) > 0", name="transformation_version"),
        CheckConstraint(
            "source_identity_kind IN ('playerid', 'playername')",
            name="source_identity_kind",
        ),
        UniqueConstraint(
            "game_title_id",
            "source_player_id",
            name="uq_players_game_title_source_identity",
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    game_title_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.game_titles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_player_id: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    source_identity_kind: Mapped[str] = mapped_column(String(32), nullable=False)


class Patch(CanonicalProvenanceMixin, Base):
    __tablename__ = "patches"
    __table_args__ = (
        CheckConstraint("source_row_hash ~ '^[0-9a-f]{64}$'", name="source_row_hash"),
        CheckConstraint("source_row_revision >= 1", name="source_row_revision"),
        CheckConstraint("length(trim(transformation_version)) > 0", name="transformation_version"),
        UniqueConstraint("game_title_id", "version", name="uq_patches_game_title_source_identity"),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    game_title_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.game_titles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
