"""Reconstruction déterministe des séries à partir des games canoniques."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, RowMapping, Select, Table, select, update
from sqlalchemy.dialects.postgresql import insert

from metiquo.canonical.dimensions import (
    LOL_DATASET,
    ORACLES_ELIXIR_PROVIDER,
    normalize_identity,
)
from metiquo.canonical.games import CanonicalGameBuilder
from metiquo.db.core_models import Game, GameTeamStat, Series, Team
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot
from metiquo.foundation.time import Clock, SystemClock

TRANSFORMATION_VERSION = "canonical-series-v1"


@dataclass(frozen=True, slots=True)
class CanonicalSeriesStatistics:
    """Résultat d'une reconstruction de séries."""

    source_games: int
    series: int
    resolved_games: int
    ambiguous_games: int
    missing_context_games: int


@dataclass(frozen=True, slots=True)
class _Candidate:
    game_id: UUID
    source_game_id: str
    competition_id: UUID | None
    event_date: date | None
    team_ids: tuple[UUID, ...]
    source_series_id: str | None
    best_of: int | None
    game_number: int | None
    rows: tuple[RowMapping, ...]


class CanonicalSeriesBuilder:
    """Préférer l'identifiant OE et refuser tout fallback ambigu."""

    def __init__(self, *, engine: Engine, clock: Clock | None = None) -> None:
        self._engine = engine
        self._clock = clock or SystemClock()

    def build(
        self,
        *,
        provider: str = ORACLES_ELIXIR_PROVIDER,
        dataset: str = LOL_DATASET,
    ) -> CanonicalSeriesStatistics:
        CanonicalGameBuilder(engine=self._engine, clock=self._clock).build(
            provider=provider,
            dataset=dataset,
        )
        processed_at = self._clock.now().value
        with self._engine.begin() as connection:
            rows = connection.execute(self._validated_rows(provider, dataset)).mappings().all()
            candidates = self._candidates(connection, rows)
            grouped: dict[str, list[_Candidate]] = defaultdict(list)
            missing: list[_Candidate] = []
            for candidate in candidates:
                key = _series_key(candidate)
                if key is None:
                    missing.append(candidate)
                else:
                    grouped[key].append(candidate)

            resolved = 0
            ambiguous = 0
            created = 0
            for key, group in grouped.items():
                if _ambiguous(key, group):
                    self._mark_games(connection, group, None, "ambiguous")
                    ambiguous += len(group)
                    continue
                series_id = self._upsert_series(
                    connection,
                    key=key,
                    candidates=group,
                    processed_at=processed_at,
                )
                self._mark_games(connection, group, series_id, "resolved")
                created += 1
                resolved += len(group)
            self._mark_games(connection, missing, None, "missing_context")

        return CanonicalSeriesStatistics(
            source_games=len(candidates),
            series=created,
            resolved_games=resolved,
            ambiguous_games=ambiguous,
            missing_context_games=len(missing),
        )

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
    def _candidates(connection: Connection, rows: Sequence[RowMapping]) -> list[_Candidate]:
        grouped: dict[str, list[RowMapping]] = defaultdict(list)
        for row in rows:
            game_id = _display(_payload(row).get("gameid"))
            if game_id is not None:
                grouped[game_id].append(row)
        source_game_ids = tuple(grouped)
        if not source_game_ids:
            return []
        games = {
            source_game_id: (game_id, competition_id, event_date)
            for source_game_id, game_id, competition_id, event_date in connection.execute(
                select(Game.source_game_id, Game.id, Game.competition_id, Game.event_date).where(
                    Game.source_game_id.in_(source_game_ids)
                )
            )
        }
        teams = {
            source_id: team_id
            for source_id, team_id in connection.execute(select(Team.source_team_id, Team.id))
        }
        candidates: list[_Candidate] = []
        for source_game_id, game_rows in grouped.items():
            canonical = games.get(source_game_id)
            if canonical is None:
                continue
            payloads = [_payload(row) for row in game_rows]
            team_ids = tuple(
                sorted(
                    {
                        team_id
                        for payload in payloads
                        if normalize_identity(payload.get("position")) == "team"
                        if (
                            team_id := teams.get(
                                normalize_identity(payload.get("teamid") or payload.get("teamname"))
                            )
                        )
                        is not None
                    },
                    key=str,
                )
            )
            candidates.append(
                _Candidate(
                    game_id=canonical[0],
                    source_game_id=source_game_id,
                    competition_id=canonical[1],
                    event_date=canonical[2],
                    team_ids=team_ids,
                    source_series_id=_first_display(payloads, ("seriesid", "series_id")),
                    best_of=_first_int(payloads, "bestof"),
                    game_number=_first_int(payloads, "game"),
                    rows=tuple(game_rows),
                )
            )
        return candidates

    @staticmethod
    def _mark_games(
        connection: Connection,
        candidates: Sequence[_Candidate],
        series_id: UUID | None,
        status: str,
    ) -> None:
        if not candidates:
            return
        games = cast(Table, Game.__table__)
        connection.execute(
            update(games)
            .where(games.c.id.in_([candidate.game_id for candidate in candidates]))
            .values(series_id=series_id, series_resolution_status=status)
        )

    @staticmethod
    def _upsert_series(
        connection: Connection,
        *,
        key: str,
        candidates: Sequence[_Candidate],
        processed_at: datetime,
    ) -> UUID:
        first = candidates[0]
        team_one, team_two = first.team_ids
        best_of_values = {candidate.best_of for candidate in candidates if candidate.best_of}
        best_of = next(iter(best_of_values)) if len(best_of_values) == 1 else None
        team_results = connection.execute(
            select(GameTeamStat.game_id, GameTeamStat.team_id, GameTeamStat.result).where(
                GameTeamStat.game_id.in_([candidate.game_id for candidate in candidates])
            )
        ).all()
        results_by_game: dict[UUID, list[tuple[UUID, bool | None]]] = defaultdict(list)
        for game_id, team_id, result in team_results:
            results_by_game[game_id].append((team_id, result))
        score_one = 0
        score_two = 0
        known_games = 0
        for candidate in candidates:
            results = results_by_game[candidate.game_id]
            winners = [team_id for team_id, result in results if result is True]
            if len(winners) != 1:
                continue
            known_games += 1
            if winners[0] == team_one:
                score_one += 1
            elif winners[0] == team_two:
                score_two += 1
        score_available = known_games == len(candidates)
        complete, result_status, winner = _series_result(
            best_of=best_of,
            game_count=len(candidates),
            score_one=score_one,
            score_two=score_two,
            score_available=score_available,
            team_one=team_one,
            team_two=team_two,
        )
        source_series_id = first.source_series_id
        series_id = _canonical_id("series", key)
        series_table = cast(Table, Series.__table__)
        values: dict[str, object] = {
            "id": series_id,
            "game_title_id": connection.execute(
                select(Game.game_title_id).where(Game.id == first.game_id)
            ).scalar_one(),
            "competition_id": first.competition_id,
            "team_one_id": team_one,
            "team_two_id": team_two,
            "winner_team_id": winner,
            "series_key": key,
            "source_series_id": source_series_id,
            "identity_strategy": "oe" if source_series_id is not None else "fallback",
            "scheduled_date": first.event_date,
            "best_of": best_of,
            "allows_draw": best_of % 2 == 0 if best_of is not None else None,
            "score_one": score_one if score_available else None,
            "score_two": score_two if score_available else None,
            "result_status": result_status,
            "complete": complete,
            "quality_status": "complete" if complete else "incomplete",
            "availability": {
                "best_of": best_of is not None,
                "competition": first.competition_id is not None,
                "result": result_status != "unresolved",
                "score": score_available,
                "source_series_id": source_series_id is not None,
            },
            **_provenance(first.rows[0], processed_at),
        }
        statement = insert(series_table).values(values)
        connection.execute(
            statement.on_conflict_do_update(
                constraint="uq_series_game_title_series_key",
                set_={
                    field: statement.excluded[field]
                    for field in values
                    if field not in {"id", "game_title_id", "series_key"}
                },
            )
        )
        return series_id


def _series_key(candidate: _Candidate) -> str | None:
    if len(candidate.team_ids) != 2:
        return None
    if candidate.source_series_id is not None:
        return f"oe:{normalize_identity(candidate.source_series_id)}"
    if (
        candidate.competition_id is None
        or candidate.event_date is None
        or candidate.best_of is None
        or candidate.game_number is None
    ):
        return None
    teams = ":".join(str(team_id) for team_id in candidate.team_ids)
    return (
        f"fallback:{candidate.competition_id}:{candidate.event_date.isoformat()}:"
        f"{teams}:bo{candidate.best_of}"
    )


def _ambiguous(key: str, candidates: Sequence[_Candidate]) -> bool:
    team_pairs = {candidate.team_ids for candidate in candidates}
    competitions = {candidate.competition_id for candidate in candidates}
    best_of_values = {
        candidate.best_of for candidate in candidates if candidate.best_of is not None
    }
    if len(team_pairs) != 1 or len(competitions) != 1 or len(best_of_values) > 1:
        return True
    if key.startswith("oe:"):
        return False
    orders = [candidate.game_number for candidate in candidates]
    return None in orders or len(set(orders)) != len(orders)


def _series_result(
    *,
    best_of: int | None,
    game_count: int,
    score_one: int,
    score_two: int,
    score_available: bool,
    team_one: UUID,
    team_two: UUID,
) -> tuple[bool, str, UUID | None]:
    if best_of is None or not score_available:
        return False, "unresolved", None
    if best_of % 2 == 1:
        target = best_of // 2 + 1
        if score_one >= target:
            return True, "team_one", team_one
        if score_two >= target:
            return True, "team_two", team_two
        return False, "unresolved", None
    if game_count < best_of:
        return False, "unresolved", None
    if score_one == score_two:
        return True, "draw", None
    if score_one > score_two:
        return True, "team_one", team_one
    return True, "team_two", team_two


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


def _display(value: object) -> str | None:
    if value is None:
        return None
    displayed = " ".join(str(value).split())
    return displayed or None


def _first_display(payloads: Sequence[Mapping[str, object]], fields: Sequence[str]) -> str | None:
    for payload in payloads:
        for field in fields:
            value = _display(payload.get(field))
            if value is not None:
                return value
    return None


def _first_int(payloads: Sequence[Mapping[str, object]], field: str) -> int | None:
    for payload in payloads:
        displayed = _display(payload.get(field))
        if displayed is None:
            continue
        try:
            parsed = Decimal(displayed)
        except InvalidOperation:
            continue
        if parsed.is_finite() and parsed == parsed.to_integral_value() and parsed >= 1:
            return int(parsed)
    return None


def _canonical_id(kind: str, identity: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"metiquo:lol:{kind}:{identity}")
