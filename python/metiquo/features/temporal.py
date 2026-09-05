"""Primitives as-of imposant un cutoff explicite à tous les calculs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast
from uuid import UUID

import polars as pl
from sqlalchemy import Engine, RowMapping, Select, Table, func, select
from sqlalchemy.sql.elements import ColumnElement

from metiquo.db.core_models import CanonicalEntityRevision, CanonicalEntitySource
from metiquo.foundation.time import normalize_utc_datetime


class CutoffViolationError(ValueError):
    """Une observation future ou tardivement connue a franchi le cutoff."""


@dataclass(frozen=True, slots=True, order=True)
class FeatureCutoff:
    """Cutoff de connaissance obligatoire, normalisé en UTC."""

    at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "at", normalize_utc_datetime(self.at))

    def audit(
        self,
        source_event_times: Iterable[datetime],
        *,
        source_knowledge_times: Iterable[datetime] = (),
    ) -> AsOfInputAudit:
        events = tuple(normalize_utc_datetime(value) for value in source_event_times)
        knowledge = tuple(normalize_utc_datetime(value) for value in source_knowledge_times)
        future_events = tuple(value for value in events if value >= self.at)
        if future_events:
            raise CutoffViolationError(
                "max(source_event_time_used) doit être strictement antérieur au cutoff"
            )
        future_knowledge = tuple(value for value in knowledge if value > self.at)
        if future_knowledge:
            raise CutoffViolationError(
                "une révision connue après le cutoff ne peut pas entrer dans les features"
            )
        return AsOfInputAudit(
            cutoff_at=self.at,
            max_input_time=max(events, default=None),
            max_knowledge_time=max(knowledge, default=None),
            input_count=len(events),
        )


@dataclass(frozen=True, slots=True)
class AsOfInputAudit:
    """Preuve temporelle calculée avec le lot de données utilisé."""

    cutoff_at: datetime
    max_input_time: datetime | None
    max_knowledge_time: datetime | None
    input_count: int

    def __post_init__(self) -> None:
        cutoff = normalize_utc_datetime(self.cutoff_at)
        object.__setattr__(self, "cutoff_at", cutoff)
        if self.max_input_time is not None:
            maximum = normalize_utc_datetime(self.max_input_time)
            object.__setattr__(self, "max_input_time", maximum)
            if maximum >= cutoff:
                raise CutoffViolationError(
                    "max_input_time doit être strictement antérieur au cutoff"
                )
        if self.max_knowledge_time is not None:
            maximum_knowledge = normalize_utc_datetime(self.max_knowledge_time)
            object.__setattr__(self, "max_knowledge_time", maximum_knowledge)
            if maximum_knowledge > cutoff:
                raise CutoffViolationError("max_knowledge_time dépasse le cutoff")
        if self.input_count < 0:
            raise ValueError("input_count ne peut pas être négatif")


@dataclass(frozen=True, slots=True)
class HistoricalTeamGame:
    team_stat_id: UUID
    team_id: UUID
    opponent_id: UUID | None
    side: str
    result: bool | None
    kills: int | None
    deaths: int | None
    gold: int | None
    towers: int | None
    dragons: int | None
    barons: int | None
    availability: Mapping[str, bool]
    source_revision_id: UUID
    source_snapshot_id: UUID
    source_run_id: UUID
    source_processed_at: datetime
    stats: Mapping[str, int | bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HistoricalPlayerGame:
    player_stat_id: UUID
    player_id: UUID
    team_id: UUID | None
    side: str
    position: str
    champion: str | None
    result: bool | None
    kills: int | None
    deaths: int | None
    assists: int | None
    creep_score: int | None
    gold: int | None
    availability: Mapping[str, bool]
    source_revision_id: UUID
    source_snapshot_id: UUID
    source_run_id: UUID
    source_processed_at: datetime


@dataclass(frozen=True, slots=True)
class HistoricalRosterObservation:
    observation_id: UUID
    team_id: UUID
    player_id: UUID
    role: str
    observed_at: datetime
    continuity_status: str
    confidence: Decimal
    source_revision_id: UUID
    source_snapshot_id: UUID
    source_run_id: UUID
    source_processed_at: datetime


@dataclass(frozen=True, slots=True)
class HistoricalGame:
    game_id: UUID
    source_game_id: str
    event_time: datetime
    competition_id: UUID | None
    patch_id: UUID | None
    series_id: UUID | None
    game_length_seconds: int | None
    best_of: int | None
    game_number: int | None
    usable_for_training: bool
    quality_status: str
    team_stats: tuple[HistoricalTeamGame, ...]
    source_revision_id: UUID
    source_snapshot_id: UUID
    source_run_id: UUID
    source_processed_at: datetime
    player_stats: tuple[HistoricalPlayerGame, ...] = ()
    roster_observations: tuple[HistoricalRosterObservation, ...] = ()


@dataclass(frozen=True, slots=True)
class AsOfGameBatch:
    games: tuple[HistoricalGame, ...]
    audit: AsOfInputAudit
    source_revision_ids: tuple[UUID, ...]
    source_snapshot_ids: tuple[UUID, ...]


def strictly_before_cutoff[T: tuple[Any, ...]](
    statement: Select[T],
    timestamp_column: ColumnElement[datetime],
    cutoff: FeatureCutoff,
) -> Select[T]:
    """Ajouter le prédicat SQL obligatoire et strict `timestamp < cutoff`."""

    if not isinstance(cutoff, FeatureCutoff):
        raise TypeError("un FeatureCutoff explicite est obligatoire")
    return statement.where(timestamp_column < cutoff.at)


def polars_strictly_before(
    frame: pl.DataFrame | pl.LazyFrame,
    *,
    timestamp_column: str,
    cutoff: FeatureCutoff,
) -> pl.LazyFrame:
    """Appliquer le même cutoff strict à un plan Polars avant tout agrégat."""

    if not isinstance(cutoff, FeatureCutoff):
        raise TypeError("un FeatureCutoff explicite est obligatoire")
    lazy = frame.lazy() if isinstance(frame, pl.DataFrame) else frame
    if timestamp_column not in lazy.collect_schema().names():
        raise ValueError(f"colonne temporelle absente: {timestamp_column}")
    return lazy.filter(pl.col(timestamp_column) < pl.lit(cutoff.at))


def latest_entity_revisions_as_of(
    entity_type: str,
    cutoff: FeatureCutoff,
) -> Select[tuple[Any, ...]]:
    """Sélectionner la dernière révision connue au cutoff pour chaque entité."""

    if not entity_type.strip():
        raise ValueError("entity_type requis")
    history = cast(Table, CanonicalEntityRevision.__table__)
    ranked = (
        select(
            history,
            func.row_number()
            .over(
                partition_by=history.c.entity_id,
                order_by=(history.c.processed_at.desc(), history.c.revision.desc()),
            )
            .label("as_of_rank"),
        )
        .where(
            history.c.entity_type == entity_type,
            history.c.processed_at <= cutoff.at,
        )
        .subquery()
    )
    return select(ranked).where(ranked.c.as_of_rank == 1)


@dataclass(frozen=True, slots=True)
class AsOfGameRepository:
    """Relire l'historique canonique tel qu'il était connu au cutoff."""

    engine: Engine

    def list_before(
        self,
        *,
        cutoff: FeatureCutoff,
        team_ids: frozenset[UUID] | None = None,
        usable_only: bool = True,
    ) -> AsOfGameBatch:
        if not isinstance(cutoff, FeatureCutoff):
            raise TypeError("un FeatureCutoff explicite est obligatoire")
        with self.engine.connect() as connection:
            game_rows = (
                connection.execute(latest_entity_revisions_as_of("game", cutoff)).mappings().all()
            )
            stat_rows = (
                connection.execute(latest_entity_revisions_as_of("game_team_stat", cutoff))
                .mappings()
                .all()
            )
            player_rows = (
                connection.execute(latest_entity_revisions_as_of("game_player_stat", cutoff))
                .mappings()
                .all()
            )
            roster_rows = (
                connection.execute(latest_entity_revisions_as_of("roster_observation", cutoff))
                .mappings()
                .all()
            )
            sources = cast(Table, CanonicalEntitySource.__table__)
            stat_revision_ids = tuple(cast(UUID, row["id"]) for row in stat_rows)
            source_rows = (
                connection.execute(
                    select(sources.c.entity_revision_id, sources.c.source_payload).where(
                        sources.c.entity_revision_id.in_(stat_revision_ids)
                    )
                )
                .mappings()
                .all()
                if stat_revision_ids
                else ()
            )
        source_payloads = {
            cast(UUID, row["entity_revision_id"]): cast(Mapping[str, object], row["source_payload"])
            for row in source_rows
        }
        stats_by_game = _team_stats(stat_rows, source_payloads)
        players_by_game = _player_stats(player_rows)
        rosters_by_game = _roster_observations(roster_rows)
        games: list[HistoricalGame] = []
        for row in game_rows:
            payload = _payload(row)
            event_time = _event_time(payload)
            if event_time >= cutoff.at:
                continue
            stats = stats_by_game.get(_uuid(payload, "id"), ())
            if team_ids is not None and not any(item.team_id in team_ids for item in stats):
                continue
            if usable_only and not bool(payload["usable_for_training"]):
                continue
            game_id = _uuid(payload, "id")
            games.append(
                _historical_game(
                    row,
                    payload,
                    event_time,
                    stats,
                    players_by_game.get(game_id, ()),
                    rosters_by_game.get(game_id, ()),
                )
            )
        games.sort(key=lambda item: (item.event_time, item.game_id))
        audit = cutoff.audit(
            (game.event_time for game in games),
            source_knowledge_times=(
                timestamp
                for game in games
                for timestamp in (
                    game.source_processed_at,
                    *(stat.source_processed_at for stat in game.team_stats),
                    *(player.source_processed_at for player in game.player_stats),
                    *(roster.source_processed_at for roster in game.roster_observations),
                )
            ),
        )
        revision_ids = tuple(
            sorted(
                {
                    revision_id
                    for game in games
                    for revision_id in (
                        game.source_revision_id,
                        *(stat.source_revision_id for stat in game.team_stats),
                        *(player.source_revision_id for player in game.player_stats),
                        *(roster.source_revision_id for roster in game.roster_observations),
                    )
                },
                key=str,
            )
        )
        snapshot_ids = tuple(
            sorted(
                {
                    snapshot_id
                    for game in games
                    for snapshot_id in (
                        game.source_snapshot_id,
                        *(stat.source_snapshot_id for stat in game.team_stats),
                        *(player.source_snapshot_id for player in game.player_stats),
                        *(roster.source_snapshot_id for roster in game.roster_observations),
                    )
                },
                key=str,
            )
        )
        return AsOfGameBatch(tuple(games), audit, revision_ids, snapshot_ids)


def _team_stats(
    rows: Iterable[RowMapping],
    source_payloads: Mapping[UUID, Mapping[str, object]],
) -> dict[UUID, tuple[HistoricalTeamGame, ...]]:
    grouped: dict[UUID, list[tuple[RowMapping, Mapping[str, object]]]] = {}
    for row in rows:
        payload = _payload(row)
        grouped.setdefault(_uuid(payload, "game_id"), []).append((row, payload))
    result: dict[UUID, tuple[HistoricalTeamGame, ...]] = {}
    for game_id, values in grouped.items():
        team_ids = tuple(_uuid(payload, "team_id") for _, payload in values)
        result[game_id] = tuple(
            sorted(
                (
                    _historical_team_game(
                        row,
                        payload,
                        next(
                            (item for item in team_ids if item != _uuid(payload, "team_id")), None
                        ),
                        source_payloads.get(cast(UUID, row["id"]), {}),
                    )
                    for row, payload in values
                ),
                key=lambda item: (item.side, item.team_id),
            )
        )
    return result


def _player_stats(rows: Iterable[RowMapping]) -> dict[UUID, tuple[HistoricalPlayerGame, ...]]:
    grouped: dict[UUID, list[HistoricalPlayerGame]] = {}
    for row in rows:
        payload = _payload(row)
        game_id = _uuid(payload, "game_id")
        availability = cast(Mapping[str, bool], payload.get("availability", {}))
        grouped.setdefault(game_id, []).append(
            HistoricalPlayerGame(
                player_stat_id=_uuid(payload, "id"),
                player_id=_uuid(payload, "player_id"),
                team_id=_optional_uuid(payload.get("team_id")),
                side=str(payload["side"]),
                position=str(payload["position"]),
                champion=_optional_str(payload.get("champion")),
                result=cast(bool | None, payload.get("result")),
                kills=_optional_int(payload.get("kills")),
                deaths=_optional_int(payload.get("deaths")),
                assists=_optional_int(payload.get("assists")),
                creep_score=_optional_int(payload.get("creep_score")),
                gold=_optional_int(payload.get("gold")),
                availability=MappingProxyType(dict(availability)),
                source_revision_id=cast(UUID, row["id"]),
                source_snapshot_id=cast(UUID, row["source_snapshot_id"]),
                source_run_id=cast(UUID, row["source_run_id"]),
                source_processed_at=_datetime(row["processed_at"]),
            )
        )
    return {
        game_id: tuple(sorted(values, key=lambda item: (item.side, item.position, item.player_id)))
        for game_id, values in grouped.items()
    }


def _roster_observations(
    rows: Iterable[RowMapping],
) -> dict[UUID, tuple[HistoricalRosterObservation, ...]]:
    grouped: dict[UUID, list[HistoricalRosterObservation]] = {}
    for row in rows:
        payload = _payload(row)
        game_id = _uuid(payload, "game_id")
        grouped.setdefault(game_id, []).append(
            HistoricalRosterObservation(
                observation_id=_uuid(payload, "id"),
                team_id=_uuid(payload, "team_id"),
                player_id=_uuid(payload, "player_id"),
                role=str(payload["role"]),
                observed_at=_datetime(payload["observed_at"]),
                continuity_status=str(payload["continuity_status"]),
                confidence=Decimal(str(payload["observation_confidence"])),
                source_revision_id=cast(UUID, row["id"]),
                source_snapshot_id=cast(UUID, row["source_snapshot_id"]),
                source_run_id=cast(UUID, row["source_run_id"]),
                source_processed_at=_datetime(row["processed_at"]),
            )
        )
    return {
        game_id: tuple(sorted(values, key=lambda item: (item.team_id, item.role)))
        for game_id, values in grouped.items()
    }


def _historical_team_game(
    row: RowMapping,
    payload: Mapping[str, object],
    opponent_id: UUID | None,
    source_payload: Mapping[str, object],
) -> HistoricalTeamGame:
    availability = cast(Mapping[str, bool], payload.get("availability", {}))
    return HistoricalTeamGame(
        team_stat_id=_uuid(payload, "id"),
        team_id=_uuid(payload, "team_id"),
        opponent_id=opponent_id,
        side=str(payload["side"]),
        result=cast(bool | None, payload.get("result")),
        kills=_optional_int(payload.get("kills")),
        deaths=_optional_int(payload.get("deaths")),
        gold=_optional_int(payload.get("gold")),
        towers=_optional_int(payload.get("towers")),
        dragons=_optional_int(payload.get("dragons")),
        barons=_optional_int(payload.get("barons")),
        availability=MappingProxyType(dict(availability)),
        source_revision_id=cast(UUID, row["id"]),
        source_snapshot_id=cast(UUID, row["source_snapshot_id"]),
        source_run_id=cast(UUID, row["source_run_id"]),
        source_processed_at=_datetime(row["processed_at"]),
        stats=MappingProxyType(_source_stats(source_payload)),
    )


def _historical_game(
    row: RowMapping,
    payload: Mapping[str, object],
    event_time: datetime,
    stats: tuple[HistoricalTeamGame, ...],
    player_stats: tuple[HistoricalPlayerGame, ...],
    roster_observations: tuple[HistoricalRosterObservation, ...],
) -> HistoricalGame:
    return HistoricalGame(
        game_id=_uuid(payload, "id"),
        source_game_id=str(payload["source_game_id"]),
        event_time=event_time,
        competition_id=_optional_uuid(payload.get("competition_id")),
        patch_id=_optional_uuid(payload.get("patch_id")),
        series_id=_optional_uuid(payload.get("series_id")),
        game_length_seconds=_optional_int(payload.get("game_length_seconds")),
        best_of=_optional_int(payload.get("best_of")),
        game_number=_optional_int(payload.get("game_number")),
        usable_for_training=bool(payload["usable_for_training"]),
        quality_status=str(payload["quality_status"]),
        team_stats=stats,
        source_revision_id=cast(UUID, row["id"]),
        source_snapshot_id=cast(UUID, row["source_snapshot_id"]),
        source_run_id=cast(UUID, row["source_run_id"]),
        source_processed_at=_datetime(row["processed_at"]),
        player_stats=player_stats,
        roster_observations=roster_observations,
    )


def _payload(row: RowMapping) -> Mapping[str, object]:
    return cast(Mapping[str, object], row["payload"])


def _event_time(payload: Mapping[str, object]) -> datetime:
    if start_at := payload.get("start_at"):
        return _datetime(start_at)
    if event_date := payload.get("event_date"):
        parsed = date.fromisoformat(str(event_date))
        return datetime.combine(parsed, time.min, tzinfo=UTC)
    raise CutoffViolationError("une game utilisée comme feature exige un instant source")


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return normalize_utc_datetime(value)
    normalized = str(value).replace("Z", "+00:00")
    return normalize_utc_datetime(datetime.fromisoformat(normalized))


def _uuid(payload: Mapping[str, object], key: str) -> UUID:
    value = payload.get(key)
    if isinstance(value, UUID):
        return value
    if value is None:
        raise ValueError(f"UUID canonique absent: {key}")
    return UUID(str(value))


def _optional_uuid(value: object) -> UUID | None:
    return None if value is None else UUID(str(value))


def _optional_int(value: object) -> int | None:
    return None if value is None else int(str(value))


def _optional_str(value: object) -> str | None:
    if value is None or not str(value).strip():
        return None
    return str(value)


_SOURCE_INTEGER_STATS = {
    f"{metric}_diff_at_{minute}": (f"{source}diffat{minute}",)
    for metric, source in (("gold", "gold"), ("xp", "xp"), ("cs", "cs"))
    for minute in (10, 15, 20, 25)
}
_SOURCE_BOOLEAN_STATS = {
    "first_baron": ("firstbaron",),
    "first_blood": ("firstblood",),
    "first_dragon": ("firstdragon",),
    "first_herald": ("firstherald",),
    "first_tower": ("firsttower",),
}


def _source_stats(payload: Mapping[str, object]) -> dict[str, int | bool]:
    values: dict[str, int | bool] = {}
    for name, aliases in _SOURCE_INTEGER_STATS.items():
        value = _first_source_int(payload, aliases)
        if value is not None:
            values[name] = value
    for name, aliases in _SOURCE_BOOLEAN_STATS.items():
        value = _first_source_bool(payload, aliases)
        if value is not None:
            values[name] = value
    return values


def _first_source_int(payload: Mapping[str, object], aliases: tuple[str, ...]) -> int | None:
    for alias in aliases:
        value = payload.get(alias)
        if value is None or str(value).strip() == "":
            continue
        try:
            return int(str(value))
        except ValueError:
            continue
    return None


def _first_source_bool(payload: Mapping[str, object], aliases: tuple[str, ...]) -> bool | None:
    for alias in aliases:
        value = str(payload.get(alias, "")).strip().casefold()
        if value in {"1", "true", "yes"}:
            return True
        if value in {"0", "false", "no"}:
            return False
    return None
