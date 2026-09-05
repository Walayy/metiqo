"""Observations de roster historiques et projection strictement as-of."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, RowMapping, Select, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.canonical.dimensions import LOL_DATASET, ORACLES_ELIXIR_PROVIDER
from metiquo.canonical.games import CanonicalGameBuilder
from metiquo.db.core_models import Game, GamePlayerStat, RosterObservation
from metiquo.db.raw_models import CanonicalRow
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime

TRANSFORMATION_VERSION = "canonical-rosters-v1"
SUBSTITUTION_CONFIDENCE = Decimal("0.6500")
OBSERVED_CONFIDENCE = Decimal("1.0000")


@dataclass(frozen=True, slots=True)
class CanonicalRosterStatistics:
    """Nombre d'observations produites et de substitutions constatées."""

    observations: int
    substitutions: int


@dataclass(frozen=True, slots=True)
class ProjectedRosterMember:
    """Dernière observation connue avant cutoff, sans persistance future."""

    role: str
    player_id: UUID
    observed_at: datetime
    confidence: Decimal
    evidence_observation_id: UUID


class CanonicalRosterBuilder:
    """Matérialiser uniquement les joueurs réellement vus dans une game."""

    def __init__(self, *, engine: Engine, clock: Clock | None = None) -> None:
        self._engine = engine
        self._clock = clock or SystemClock()

    def build(
        self,
        *,
        provider: str = ORACLES_ELIXIR_PROVIDER,
        dataset: str = LOL_DATASET,
    ) -> CanonicalRosterStatistics:
        CanonicalGameBuilder(engine=self._engine, clock=self._clock).build(
            provider=provider,
            dataset=dataset,
        )
        processed_at = self._clock.now().value
        with self._engine.begin() as connection:
            rows = connection.execute(self._observed_players(provider, dataset)).mappings().all()
            previous: dict[tuple[UUID, str], UUID] = {}
            values: list[dict[str, object]] = []
            substitutions = 0
            for row in rows:
                observed_at = _observed_at(row)
                team_id = row["team_id"]
                player_id = row["player_id"]
                role = row["position"]
                if (
                    observed_at is None
                    or not isinstance(team_id, UUID)
                    or not isinstance(player_id, UUID)
                ):
                    continue
                key = (team_id, str(role))
                prior = previous.get(key)
                if prior is None:
                    continuity_status = "first_seen"
                    confidence = OBSERVED_CONFIDENCE
                elif prior == player_id:
                    continuity_status = "confirmed"
                    confidence = OBSERVED_CONFIDENCE
                else:
                    continuity_status = "substitution_observed"
                    confidence = SUBSTITUTION_CONFIDENCE
                    substitutions += 1
                previous[key] = player_id
                values.append(
                    {
                        "id": _canonical_id(
                            "roster-observation", f"{row['game_id']}:{team_id}:{role}"
                        ),
                        "game_id": row["game_id"],
                        "team_id": team_id,
                        "player_id": player_id,
                        "observed_at": observed_at,
                        "role": role,
                        "continuity_status": continuity_status,
                        "observation_confidence": confidence,
                        **_provenance(row, processed_at),
                    }
                )
            _upsert_observations(connection, values)
        return CanonicalRosterStatistics(len(values), substitutions)

    @staticmethod
    def _observed_players(provider: str, dataset: str) -> Select[tuple[Any, ...]]:
        return (
            select(
                GamePlayerStat.game_id,
                GamePlayerStat.team_id,
                GamePlayerStat.player_id,
                GamePlayerStat.position,
                GamePlayerStat.source_raw_row_id,
                GamePlayerStat.source_snapshot_id,
                GamePlayerStat.source_run_id,
                GamePlayerStat.source_natural_key,
                GamePlayerStat.source_row_hash,
                GamePlayerStat.source_row_revision,
                Game.start_at,
                Game.event_date,
                Game.source_game_id,
            )
            .join(Game, Game.id == GamePlayerStat.game_id)
            .join(CanonicalRow, CanonicalRow.id == Game.source_raw_row_id)
            .where(
                CanonicalRow.provider == provider,
                CanonicalRow.dataset == dataset,
                GamePlayerStat.team_id.is_not(None),
            )
            .order_by(
                Game.start_at.asc().nulls_last(),
                Game.event_date.asc().nulls_last(),
                Game.source_game_id.asc(),
                GamePlayerStat.team_id.asc(),
                GamePlayerStat.position.asc(),
            )
        )


class RosterProjectionService:
    """Lire le dernier roster observé strictement avant un cutoff."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def as_of(self, *, team_id: UUID, cutoff: datetime) -> tuple[ProjectedRosterMember, ...]:
        normalized_cutoff = normalize_utc_datetime(cutoff)
        with self._engine.connect() as connection:
            observations = (
                connection.execute(
                    select(
                        RosterObservation.id,
                        RosterObservation.role,
                        RosterObservation.player_id,
                        RosterObservation.observed_at,
                        RosterObservation.observation_confidence,
                    )
                    .where(
                        RosterObservation.team_id == team_id,
                        RosterObservation.observed_at < normalized_cutoff,
                    )
                    .order_by(RosterObservation.observed_at.asc(), RosterObservation.id.asc())
                )
                .mappings()
                .all()
            )
        latest: dict[str, ProjectedRosterMember] = {}
        for row in observations:
            latest[str(row["role"])] = ProjectedRosterMember(
                role=str(row["role"]),
                player_id=cast(UUID, row["player_id"]),
                observed_at=cast(datetime, row["observed_at"]),
                confidence=cast(Decimal, row["observation_confidence"]),
                evidence_observation_id=cast(UUID, row["id"]),
            )
        return tuple(latest[role] for role in sorted(latest))


def _upsert_observations(connection: Connection, values: Sequence[Mapping[str, object]]) -> None:
    if not values:
        return
    table = cast(Table, RosterObservation.__table__)
    statement = insert(table).values(list(values))
    connection.execute(
        statement.on_conflict_do_update(
            constraint="uq_roster_observations_game_team_role",
            set_={
                column: statement.excluded[column]
                for column in tuple(table.c.keys())
                if column not in {"id", "game_id", "team_id", "role"}
            },
        )
    )


def _observed_at(row: RowMapping) -> datetime | None:
    start_at = row["start_at"]
    if isinstance(start_at, datetime):
        return normalize_utc_datetime(start_at)
    event_date = row["event_date"]
    if isinstance(event_date, date):
        return datetime.combine(event_date, time.min, tzinfo=UTC)
    return None


def _provenance(row: RowMapping, processed_at: datetime) -> dict[str, object]:
    return {
        "source_raw_row_id": row["source_raw_row_id"],
        "source_snapshot_id": row["source_snapshot_id"],
        "source_run_id": row["source_run_id"],
        "source_natural_key": row["source_natural_key"],
        "source_row_hash": row["source_row_hash"],
        "source_row_revision": row["source_row_revision"],
        "transformation_version": TRANSFORMATION_VERSION,
        "processed_at": processed_at,
    }


def _canonical_id(kind: str, identity: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"metiquo:lol:{kind}:{identity}")
