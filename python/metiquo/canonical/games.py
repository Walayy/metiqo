"""Projection des parties et statistiques depuis les lignes raw validées."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, RowMapping, Select, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.canonical.capabilities import CapabilityRegistry
from metiquo.canonical.dimensions import (
    LOL_DATASET,
    LOL_SLUG,
    ORACLES_ELIXIR_PROVIDER,
    CanonicalDimensionBuilder,
    normalize_identity,
)
from metiquo.canonical.history import CanonicalHistoryRecorder
from metiquo.db.core_models import (
    Competition,
    Game,
    GamePlayerStat,
    GameTeamStat,
    GameTitle,
    Patch,
    Player,
    Team,
)
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot
from metiquo.foundation.time import Clock, SystemClock

TRANSFORMATION_VERSION = "canonical-games-v1"
_POSITION_MAP = {
    "top": "top",
    "jng": "jng",
    "jungle": "jng",
    "mid": "mid",
    "bot": "bot",
    "adc": "bot",
    "sup": "sup",
    "support": "sup",
}


@dataclass(frozen=True, slots=True)
class CanonicalGameStatistics:
    """Cardinalités de la projection des faits canoniques."""

    source_rows: int
    games: int
    team_stats: int
    player_stats: int


@dataclass(frozen=True, slots=True)
class _DimensionMaps:
    game_title_id: UUID
    competitions: Mapping[str, UUID]
    teams: Mapping[str, UUID]
    players: Mapping[str, UUID]
    patches: Mapping[str, UUID]


class CanonicalGameBuilder:
    """Reconstruire les faits sans lire de fichier ou de source externe."""

    def __init__(self, *, engine: Engine, clock: Clock | None = None) -> None:
        self._engine = engine
        self._clock = clock or SystemClock()

    def build(
        self,
        *,
        provider: str = ORACLES_ELIXIR_PROVIDER,
        dataset: str = LOL_DATASET,
    ) -> CanonicalGameStatistics:
        CanonicalDimensionBuilder(engine=self._engine, clock=self._clock).build(
            provider=provider,
            dataset=dataset,
        )
        processed_at = self._clock.now().value
        with self._engine.begin() as connection:
            rows = connection.execute(self._validated_rows(provider, dataset)).mappings().all()
            if not rows:
                return CanonicalGameStatistics(0, 0, 0, 0)
            dimensions = self._dimension_maps(connection)
            grouped: dict[str, list[RowMapping]] = defaultdict(list)
            for row in rows:
                game_id = _display(_payload(row).get("gameid"))
                if game_id is not None:
                    grouped[game_id].append(row)

            team_count = 0
            player_count = 0
            for source_game_id, game_rows in grouped.items():
                counts = self._upsert_game(
                    connection,
                    source_game_id=source_game_id,
                    rows=game_rows,
                    dimensions=dimensions,
                    processed_at=processed_at,
                )
                team_count += counts[0]
                player_count += counts[1]
        statistics = CanonicalGameStatistics(
            source_rows=len(rows),
            games=len(grouped),
            team_stats=team_count,
            player_stats=player_count,
        )
        CanonicalHistoryRecorder(engine=self._engine).record(
            provider=provider,
            dataset=dataset,
            entity_types={"game", "game_team_stat", "game_player_stat"},
        )
        CapabilityRegistry(engine=self._engine, clock=self._clock).evaluate_current(
            provider=provider,
            dataset=dataset,
        )
        return statistics

    @staticmethod
    def _validated_rows(provider: str, dataset: str) -> Select[tuple[Any, ...]]:
        raw = CanonicalRow.__table__
        snapshots = Snapshot.__table__
        runs = IngestionRun.__table__
        return (
            select(
                raw.c.id,
                raw.c.natural_key,
                raw.c.row_hash,
                raw.c.revision,
                raw.c.payload,
                raw.c.event_date,
                raw.c.source_snapshot_id,
                raw.c.source_run_id,
            )
            .join(
                snapshots,
                (snapshots.c.id == raw.c.source_snapshot_id) & (snapshots.c.status == "validated"),
            )
            .join(
                runs,
                (runs.c.id == raw.c.source_run_id) & (runs.c.status == "succeeded"),
            )
            .where(raw.c.provider == provider, raw.c.dataset == dataset)
            .order_by(raw.c.event_date.asc().nulls_last(), raw.c.natural_key.asc())
        )

    @staticmethod
    def _dimension_maps(connection: Connection) -> _DimensionMaps:
        game_title_id = connection.execute(
            select(GameTitle.id).where(GameTitle.slug == LOL_SLUG)
        ).scalar_one()
        return _DimensionMaps(
            game_title_id=game_title_id,
            competitions={
                source_id: entity_id
                for source_id, entity_id in connection.execute(
                    select(Competition.source_competition_id, Competition.id).where(
                        Competition.game_title_id == game_title_id
                    )
                )
            },
            teams={
                source_id: entity_id
                for source_id, entity_id in connection.execute(
                    select(Team.source_team_id, Team.id).where(Team.game_title_id == game_title_id)
                )
            },
            players={
                source_id: entity_id
                for source_id, entity_id in connection.execute(
                    select(Player.source_player_id, Player.id).where(
                        Player.game_title_id == game_title_id
                    )
                )
            },
            patches={
                version: entity_id
                for version, entity_id in connection.execute(
                    select(Patch.version, Patch.id).where(Patch.game_title_id == game_title_id)
                )
            },
        )

    def _upsert_game(
        self,
        connection: Connection,
        *,
        source_game_id: str,
        rows: Sequence[RowMapping],
        dimensions: _DimensionMaps,
        processed_at: datetime,
    ) -> tuple[int, int]:
        payloads = [_payload(row) for row in rows]
        team_rows = [
            (row, payload)
            for row, payload in zip(rows, payloads, strict=True)
            if normalize_identity(payload.get("position")) == "team"
        ]
        player_rows = [
            (row, payload)
            for row, payload in zip(rows, payloads, strict=True)
            if normalize_identity(payload.get("position")) in _POSITION_MAP
        ]
        team_entities = [
            (
                row,
                payload,
                _side(payload.get("side")),
                dimensions.teams.get(_source_team_identity(payload)),
                _optional_bool(payload.get("result")),
            )
            for row, payload in team_rows
        ]
        valid_team_entities = [
            entity for entity in team_entities if entity[2] is not None and entity[3] is not None
        ]
        sides = {entity[2] for entity in valid_team_entities}
        teams = {entity[3] for entity in valid_team_entities}
        two_teams = len(valid_team_entities) == 2 and sides == {"Blue", "Red"} and len(teams) == 2
        results = [entity[4] for entity in valid_team_entities]
        coherent_result = (
            two_teams
            and all(result is not None for result in results)
            and sum(bool(result) for result in results) == 1
        )
        completeness = {normalize_identity(payload.get("datacompleteness")) for payload in payloads}
        source_complete = completeness == {"complete"}
        lengths = {
            value
            for payload in payloads
            if (value := _optional_int(payload.get("gamelength"))) is not None
        }
        game_length = next(iter(lengths)) if len(lengths) == 1 else None
        remake = game_length is not None and game_length < 600
        forfeit = any(_optional_bool(payload.get("forfeit")) is True for payload in payloads)
        complete = source_complete and two_teams and coherent_result
        usable = complete and not remake and not forfeit
        quality_status = (
            "remake"
            if remake
            else "forfeit"
            if forfeit
            else "complete"
            if complete
            else "incomplete"
        )
        first_row = rows[0]
        first_payload = payloads[0]
        event_date = _event_date(rows, first_payload)
        league = normalize_identity(first_payload.get("league"))
        patch = normalize_identity(first_payload.get("patch"))
        game_id = _canonical_id("game", normalize_identity(source_game_id))
        values: dict[str, object] = {
            "id": game_id,
            "game_title_id": dimensions.game_title_id,
            "competition_id": dimensions.competitions.get(league),
            "patch_id": dimensions.patches.get(patch),
            "source_game_id": source_game_id,
            "event_date": event_date,
            "start_at": _start_at(first_payload.get("date")),
            "game_length_seconds": game_length,
            "best_of": _first_int(payloads, "bestof"),
            "game_number": _first_int(payloads, "game"),
            "complete": complete,
            "remake": remake,
            "forfeit": forfeit,
            "usable_for_training": usable,
            "quality_status": quality_status,
            "availability": {
                "competition": dimensions.competitions.get(league) is not None,
                "event_date": event_date is not None,
                "game_length": game_length is not None,
                "patch": dimensions.patches.get(patch) is not None,
                "player_rows": _player_structure_available(player_rows),
                "result": coherent_result,
                "team_participants": two_teams,
            },
            **_provenance(first_row, processed_at),
        }
        game_table = cast(Table, Game.__table__)
        statement = insert(game_table).values(values)
        connection.execute(
            statement.on_conflict_do_update(
                constraint="uq_games_game_title_source_identity",
                set_={
                    key: statement.excluded[key]
                    for key in values
                    if key not in {"id", "game_title_id", "source_game_id"}
                },
            )
        )
        team_values = self._team_values(
            game_id=game_id,
            entities=valid_team_entities,
            processed_at=processed_at,
        )
        player_values = self._player_values(
            game_id=game_id,
            rows=player_rows,
            dimensions=dimensions,
            processed_at=processed_at,
        )
        _upsert_many(connection, GameTeamStat, "uq_game_team_stats_game_team", team_values)
        _upsert_many(connection, GamePlayerStat, "uq_game_player_stats_game_player", player_values)
        return len(team_values), len(player_values)

    @staticmethod
    def _team_values(
        *,
        game_id: UUID,
        entities: Sequence[
            tuple[RowMapping, Mapping[str, object], str | None, UUID | None, bool | None]
        ],
        processed_at: datetime,
    ) -> list[dict[str, object]]:
        values: list[dict[str, object]] = []
        for row, payload, side, team_id, result in entities:
            if side is None or team_id is None:
                continue
            fields = {
                "kills": _first_available_int(payload, ("kills", "teamkills")),
                "deaths": _first_available_int(payload, ("deaths", "teamdeaths")),
                "gold": _first_available_int(payload, ("earnedgold", "totalgold")),
                "towers": _optional_int(payload.get("towers")),
                "dragons": _optional_int(payload.get("dragons")),
                "barons": _optional_int(payload.get("barons")),
            }
            values.append(
                {
                    "id": _canonical_id("game-team-stat", f"{game_id}:{team_id}"),
                    "game_id": game_id,
                    "team_id": team_id,
                    "side": side,
                    "result": result,
                    **fields,
                    "availability": {
                        "result": result is not None,
                        **{name: value is not None for name, value in fields.items()},
                    },
                    "stats": {},
                    **_provenance(row, processed_at),
                }
            )
        return values

    @staticmethod
    def _player_values(
        *,
        game_id: UUID,
        rows: Sequence[tuple[RowMapping, Mapping[str, object]]],
        dimensions: _DimensionMaps,
        processed_at: datetime,
    ) -> list[dict[str, object]]:
        values: list[dict[str, object]] = []
        for row, payload in rows:
            side = _side(payload.get("side"))
            position = _POSITION_MAP.get(normalize_identity(payload.get("position")))
            player_id = dimensions.players.get(_source_player_identity(payload))
            if side is None or position is None or player_id is None:
                continue
            team_id = dimensions.teams.get(_source_team_identity(payload))
            result = _optional_bool(payload.get("result"))
            champion = _display(payload.get("champion"))
            fields = {
                "kills": _optional_int(payload.get("kills")),
                "deaths": _optional_int(payload.get("deaths")),
                "assists": _optional_int(payload.get("assists")),
                "creep_score": _first_available_int(payload, ("total cs", "cs")),
                "gold": _first_available_int(payload, ("earnedgold", "totalgold")),
            }
            values.append(
                {
                    "id": _canonical_id("game-player-stat", f"{game_id}:{player_id}"),
                    "game_id": game_id,
                    "player_id": player_id,
                    "team_id": team_id,
                    "side": side,
                    "position": position,
                    "champion": champion,
                    "result": result,
                    **fields,
                    "availability": {
                        "champion": champion is not None,
                        "result": result is not None,
                        "team": team_id is not None,
                        **{name: value is not None for name, value in fields.items()},
                    },
                    "stats": {},
                    **_provenance(row, processed_at),
                }
            )
        return values


def _upsert_many(
    connection: Connection,
    model: type[GameTeamStat] | type[GamePlayerStat],
    constraint: str,
    values: Sequence[Mapping[str, object]],
) -> None:
    if not values:
        return
    table = cast(Table, model.__table__)
    statement = insert(table).values(list(values))
    connection.execute(
        statement.on_conflict_do_update(
            constraint=constraint,
            set_={
                column: statement.excluded[column]
                for column in tuple(table.c.keys())
                if column not in {"id", "game_id", "team_id", "player_id"}
            },
        )
    )


def _payload(row: RowMapping) -> Mapping[str, object]:
    payload = row["payload"]
    if not isinstance(payload, Mapping):
        return {}
    return cast(Mapping[str, object], payload)


def _provenance(row: RowMapping, processed_at: datetime) -> dict[str, object]:
    return {
        "source_raw_row_id": row["id"],
        "source_snapshot_id": row["source_snapshot_id"],
        "source_run_id": row["source_run_id"],
        "source_natural_key": row["natural_key"],
        "source_row_hash": row["row_hash"],
        "source_row_revision": row["revision"],
        "transformation_version": TRANSFORMATION_VERSION,
        "processed_at": processed_at,
    }


def _canonical_id(kind: str, identity: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"metiquo:lol:{kind}:{identity}")


def _display(value: object) -> str | None:
    if value is None:
        return None
    displayed = " ".join(str(value).split())
    return displayed or None


def _source_team_identity(payload: Mapping[str, object]) -> str:
    return normalize_identity(payload.get("teamid") or payload.get("teamname"))


def _source_player_identity(payload: Mapping[str, object]) -> str:
    return normalize_identity(payload.get("playerid") or payload.get("playername"))


def _side(value: object) -> str | None:
    normalized = normalize_identity(value)
    return {"blue": "Blue", "red": "Red"}.get(normalized)


def _optional_bool(value: object) -> bool | None:
    normalized = normalize_identity(value)
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    return None


def _optional_int(value: object) -> int | None:
    displayed = _display(value)
    if displayed is None:
        return None
    try:
        parsed = Decimal(displayed)
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed != parsed.to_integral_value():
        return None
    return int(parsed)


def _first_available_int(payload: Mapping[str, object], fields: Sequence[str]) -> int | None:
    for field in fields:
        value = _optional_int(payload.get(field))
        if value is not None:
            return value
    return None


def _first_int(payloads: Sequence[Mapping[str, object]], field: str) -> int | None:
    for payload in payloads:
        value = _optional_int(payload.get(field))
        if value is not None:
            return value
    return None


def _start_at(value: object) -> datetime | None:
    displayed = _display(value)
    if displayed is None:
        return None
    candidate = displayed.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(candidate[:10])
        except ValueError:
            return None
        return datetime.combine(parsed_date, datetime.min.time(), tzinfo=UTC)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _event_date(rows: Sequence[RowMapping], payload: Mapping[str, object]) -> date | None:
    for row in rows:
        value = row["event_date"]
        if isinstance(value, date):
            return value
    displayed = _display(payload.get("date"))
    if displayed is None:
        return None
    try:
        return date.fromisoformat(displayed[:10])
    except ValueError:
        return None


def _player_structure_available(
    rows: Sequence[tuple[RowMapping, Mapping[str, object]]],
) -> bool:
    positions_by_side: dict[str, set[str]] = defaultdict(set)
    for _, payload in rows:
        side = _side(payload.get("side"))
        position = _POSITION_MAP.get(normalize_identity(payload.get("position")))
        if side is not None and position is not None:
            positions_by_side[side].add(position)
    return len(rows) == 10 and all(
        positions_by_side[side] == {"top", "jng", "mid", "bot", "sup"} for side in ("Blue", "Red")
    )
