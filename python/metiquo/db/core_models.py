"""Modèles canoniques League of Legends dérivés exclusivement du raw Oracle's Elixir."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
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


class Game(CanonicalProvenanceMixin, Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint("length(trim(source_game_id)) > 0", name="source_game_id"),
        CheckConstraint("source_row_hash ~ '^[0-9a-f]{64}$'", name="source_row_hash"),
        CheckConstraint("source_row_revision >= 1", name="source_row_revision"),
        CheckConstraint("length(trim(transformation_version)) > 0", name="transformation_version"),
        CheckConstraint(
            "quality_status IN ('complete', 'incomplete', 'remake', 'forfeit')",
            name="quality_status",
        ),
        CheckConstraint(
            "series_resolution_status IN ('resolved', 'ambiguous', 'missing_context')",
            name="series_resolution_status",
        ),
        CheckConstraint("game_length_seconds IS NULL OR game_length_seconds > 0", name="length"),
        CheckConstraint("best_of IS NULL OR best_of >= 1", name="best_of"),
        CheckConstraint("game_number IS NULL OR game_number >= 1", name="game_number"),
        CheckConstraint(
            "NOT usable_for_training OR (complete AND NOT remake AND NOT forfeit)",
            name="training_eligibility",
        ),
        UniqueConstraint(
            "game_title_id", "source_game_id", name="uq_games_game_title_source_identity"
        ),
        Index("ix_core_games_event_date", "event_date"),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    game_title_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.game_titles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    competition_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.competitions.id", ondelete="RESTRICT"),
    )
    patch_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.patches.id", ondelete="RESTRICT"),
    )
    series_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.series.id", ondelete="RESTRICT"),
    )
    source_game_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_date: Mapped[date | None] = mapped_column()
    start_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    game_length_seconds: Mapped[int | None] = mapped_column(Integer)
    best_of: Mapped[int | None] = mapped_column(Integer)
    game_number: Mapped[int | None] = mapped_column(Integer)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    remake: Mapped[bool] = mapped_column(Boolean, nullable=False)
    forfeit: Mapped[bool] = mapped_column(Boolean, nullable=False)
    usable_for_training: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    series_resolution_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="missing_context"
    )
    availability: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False)


class Series(CanonicalProvenanceMixin, Base):
    __tablename__ = "series"
    __table_args__ = (
        CheckConstraint("length(trim(series_key)) > 0", name="series_key"),
        CheckConstraint("identity_strategy IN ('oe', 'fallback')", name="identity_strategy"),
        CheckConstraint("team_one_id <> team_two_id", name="distinct_teams"),
        CheckConstraint("best_of IS NULL OR best_of >= 1", name="best_of"),
        CheckConstraint(
            "(best_of IS NULL AND allows_draw IS NULL) OR "
            "(best_of IS NOT NULL AND allows_draw = (mod(best_of, 2) = 0))",
            name="draw_format",
        ),
        CheckConstraint("score_one IS NULL OR score_one >= 0", name="score_one"),
        CheckConstraint("score_two IS NULL OR score_two >= 0", name="score_two"),
        CheckConstraint(
            "result_status IN ('team_one', 'team_two', 'draw', 'unresolved')",
            name="result_status",
        ),
        CheckConstraint(
            "(result_status IN ('team_one', 'team_two') AND winner_team_id IS NOT NULL) OR "
            "(result_status IN ('draw', 'unresolved') AND winner_team_id IS NULL)",
            name="winner_state",
        ),
        CheckConstraint("quality_status IN ('complete', 'incomplete')", name="quality_status"),
        CheckConstraint("source_row_hash ~ '^[0-9a-f]{64}$'", name="source_row_hash"),
        CheckConstraint("source_row_revision >= 1", name="source_row_revision"),
        CheckConstraint("length(trim(transformation_version)) > 0", name="transformation_version"),
        UniqueConstraint("game_title_id", "series_key", name="uq_series_game_title_series_key"),
        Index("ix_core_series_scheduled_date", "scheduled_date"),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    game_title_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.game_titles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    competition_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.competitions.id", ondelete="RESTRICT"),
    )
    team_one_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    team_two_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    winner_team_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.teams.id", ondelete="RESTRICT"),
    )
    series_key: Mapped[str] = mapped_column(String(512), nullable=False)
    source_series_id: Mapped[str | None] = mapped_column(String(255))
    identity_strategy: Mapped[str] = mapped_column(String(16), nullable=False)
    scheduled_date: Mapped[date | None] = mapped_column()
    best_of: Mapped[int | None] = mapped_column(Integer)
    allows_draw: Mapped[bool | None] = mapped_column(Boolean)
    score_one: Mapped[int | None] = mapped_column(Integer)
    score_two: Mapped[int | None] = mapped_column(Integer)
    result_status: Mapped[str] = mapped_column(String(16), nullable=False)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(16), nullable=False)
    availability: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False)


class GameTeamStat(CanonicalProvenanceMixin, Base):
    __tablename__ = "game_team_stats"
    __table_args__ = (
        CheckConstraint("side IN ('Blue', 'Red')", name="side"),
        CheckConstraint("kills IS NULL OR kills >= 0", name="kills_non_negative"),
        CheckConstraint("deaths IS NULL OR deaths >= 0", name="deaths_non_negative"),
        CheckConstraint("gold IS NULL OR gold >= 0", name="gold_non_negative"),
        CheckConstraint("towers IS NULL OR towers >= 0", name="towers_non_negative"),
        CheckConstraint("dragons IS NULL OR dragons >= 0", name="dragons_non_negative"),
        CheckConstraint("barons IS NULL OR barons >= 0", name="barons_non_negative"),
        CheckConstraint("source_row_hash ~ '^[0-9a-f]{64}$'", name="source_row_hash"),
        CheckConstraint("source_row_revision >= 1", name="source_row_revision"),
        CheckConstraint("length(trim(transformation_version)) > 0", name="transformation_version"),
        UniqueConstraint("game_id", "team_id", name="uq_game_team_stats_game_team"),
        UniqueConstraint("game_id", "side", name="uq_game_team_stats_game_side"),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    team_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    result: Mapped[bool | None] = mapped_column(Boolean)
    kills: Mapped[int | None] = mapped_column(Integer)
    deaths: Mapped[int | None] = mapped_column(Integer)
    gold: Mapped[int | None] = mapped_column(BigInteger)
    towers: Mapped[int | None] = mapped_column(Integer)
    dragons: Mapped[int | None] = mapped_column(Integer)
    barons: Mapped[int | None] = mapped_column(Integer)
    availability: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class GamePlayerStat(CanonicalProvenanceMixin, Base):
    __tablename__ = "game_player_stats"
    __table_args__ = (
        CheckConstraint("side IN ('Blue', 'Red')", name="side"),
        CheckConstraint("position IN ('top', 'jng', 'mid', 'bot', 'sup')", name="position"),
        CheckConstraint("kills IS NULL OR kills >= 0", name="kills_non_negative"),
        CheckConstraint("deaths IS NULL OR deaths >= 0", name="deaths_non_negative"),
        CheckConstraint("assists IS NULL OR assists >= 0", name="assists_non_negative"),
        CheckConstraint("creep_score IS NULL OR creep_score >= 0", name="creep_score_non_negative"),
        CheckConstraint("gold IS NULL OR gold >= 0", name="gold_non_negative"),
        CheckConstraint("source_row_hash ~ '^[0-9a-f]{64}$'", name="source_row_hash"),
        CheckConstraint("source_row_revision >= 1", name="source_row_revision"),
        CheckConstraint("length(trim(transformation_version)) > 0", name="transformation_version"),
        UniqueConstraint("game_id", "player_id", name="uq_game_player_stats_game_player"),
        UniqueConstraint(
            "game_id", "side", "position", name="uq_game_player_stats_game_side_position"
        ),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    player_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    team_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.teams.id", ondelete="RESTRICT"),
    )
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    position: Mapped[str] = mapped_column(String(8), nullable=False)
    champion: Mapped[str | None] = mapped_column(String(128))
    result: Mapped[bool | None] = mapped_column(Boolean)
    kills: Mapped[int | None] = mapped_column(Integer)
    deaths: Mapped[int | None] = mapped_column(Integer)
    assists: Mapped[int | None] = mapped_column(Integer)
    creep_score: Mapped[int | None] = mapped_column(Integer)
    gold: Mapped[int | None] = mapped_column(BigInteger)
    availability: Mapped[dict[str, bool]] = mapped_column(JSONB, nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class RosterObservation(CanonicalProvenanceMixin, Base):
    __tablename__ = "roster_observations"
    __table_args__ = (
        CheckConstraint("role IN ('top', 'jng', 'mid', 'bot', 'sup')", name="role"),
        CheckConstraint(
            "continuity_status IN ('first_seen', 'confirmed', 'substitution_observed')",
            name="continuity_status",
        ),
        CheckConstraint(
            "observation_confidence >= 0 AND observation_confidence <= 1",
            name="observation_confidence",
        ),
        CheckConstraint("source_row_hash ~ '^[0-9a-f]{64}$'", name="source_row_hash"),
        CheckConstraint("source_row_revision >= 1", name="source_row_revision"),
        CheckConstraint("length(trim(transformation_version)) > 0", name="transformation_version"),
        UniqueConstraint(
            "game_id", "team_id", "role", name="uq_roster_observations_game_team_role"
        ),
        UniqueConstraint("game_id", "player_id", name="uq_roster_observations_game_player"),
        Index("ix_core_roster_observations_team_observed", "team_id", "observed_at"),
        {"schema": CORE_SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.games.id", ondelete="RESTRICT"),
        nullable=False,
    )
    team_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.teams.id", ondelete="RESTRICT"),
        nullable=False,
    )
    player_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core.players.id", ondelete="RESTRICT"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(UtcDateTime(), nullable=False)
    role: Mapped[str] = mapped_column(String(8), nullable=False)
    continuity_status: Mapped[str] = mapped_column(String(32), nullable=False)
    observation_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
