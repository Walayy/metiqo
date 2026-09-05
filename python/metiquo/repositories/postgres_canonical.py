"""Lectures PostgreSQL des équipes, games, séries et événements historiques."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, RowMapping, Table, exists, func, or_, select

from metiquo.contracts import Event, Market, OddsSnapshot
from metiquo.contracts.enums import EventStatus, MarketStatus, ProviderStatus, SelectionType
from metiquo.contracts.enums import GameTitle as ContractGameTitle
from metiquo.db.core_models import Competition, Game, GameTeamStat, Series, Team
from metiquo.db.odds_models import (
    EventMappingAttempt,
    EventMappingCandidateScore,
    MappingReviewRecord,
    OddsProviderRecord,
    OddsSnapshotRecord,
    ProviderOddsSelection,
)
from metiquo.foundation.time import Clock, SystemClock


@dataclass(frozen=True, slots=True)
class CanonicalTeamRecord:
    team_id: UUID
    source_team_id: str
    display_name: str
    observed_at: datetime
    source_snapshot_id: UUID


@dataclass(frozen=True, slots=True)
class CanonicalGameRecord:
    game_id: UUID
    source_game_id: str
    series_id: UUID | None
    competition: str
    team_a_id: UUID | None
    team_a: str | None
    team_b_id: UUID | None
    team_b: str | None
    starts_at: datetime | None
    event_date: date | None
    quality_status: str
    observed_at: datetime
    source_snapshot_id: UUID


@dataclass(frozen=True, slots=True)
class CanonicalSeriesRecord:
    series_id: UUID
    source_series_id: str | None
    series_key: str
    competition: str
    team_a_id: UUID
    team_a: str
    team_b_id: UUID
    team_b: str
    starts_at: datetime | None
    scheduled_date: date | None
    best_of: int | None
    score_a: int | None
    score_b: int | None
    result_status: str
    observed_at: datetime
    source_snapshot_id: UUID


@dataclass(frozen=True, slots=True)
class PostgresCanonicalRepository:
    """Adapter les tables core sans exposer l'ORM dans les contrats publics."""

    engine: Engine
    clock: Clock = field(default_factory=SystemClock)

    def list_teams(self) -> tuple[CanonicalTeamRecord, ...]:
        teams = cast(Table, Team.__table__)
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(teams).order_by(teams.c.normalized_name, teams.c.id)
            ).mappings()
            return tuple(
                CanonicalTeamRecord(
                    team_id=cast(UUID, row.id),
                    source_team_id=str(row.source_team_id),
                    display_name=_display_name(row),
                    observed_at=cast(datetime, row.processed_at),
                    source_snapshot_id=cast(UUID, row.source_snapshot_id),
                )
                for row in rows
            )

    def get_team(self, team_id: UUID) -> CanonicalTeamRecord | None:
        return next((team for team in self.list_teams() if team.team_id == team_id), None)

    def list_games(self) -> tuple[CanonicalGameRecord, ...]:
        games = cast(Table, Game.__table__)
        competitions = cast(Table, Competition.__table__)
        stats = cast(Table, GameTeamStat.__table__)
        teams = cast(Table, Team.__table__)
        with self.engine.connect() as connection:
            game_rows = (
                connection.execute(
                    select(
                        games,
                        competitions.c.display_name.label("competition_display_name"),
                        competitions.c.normalized_name.label("competition_normalized_name"),
                        competitions.c.source_competition_id.label("competition_source_id"),
                    )
                    .outerjoin(competitions, competitions.c.id == games.c.competition_id)
                    .order_by(
                        games.c.start_at.desc().nulls_last(), games.c.event_date.desc(), games.c.id
                    )
                )
                .mappings()
                .all()
            )
            team_rows = connection.execute(
                select(
                    stats.c.game_id,
                    stats.c.side,
                    teams.c.id.label("team_id"),
                    teams.c.display_name,
                    teams.c.normalized_name,
                    teams.c.source_team_id,
                )
                .join(teams, teams.c.id == stats.c.team_id)
                .order_by(stats.c.game_id, stats.c.side)
            ).mappings()
        participants: dict[UUID, dict[str, tuple[UUID, str]]] = {}
        for row in team_rows:
            game_id = cast(UUID, row["game_id"])
            participants.setdefault(game_id, {})[str(row["side"])] = (
                cast(UUID, row["team_id"]),
                _display_name(row),
            )
        return tuple(self._game_record(row, participants) for row in game_rows)

    def get_game(self, game_id: UUID) -> CanonicalGameRecord | None:
        return next((game for game in self.list_games() if game.game_id == game_id), None)

    def list_series(self) -> tuple[CanonicalSeriesRecord, ...]:
        series = cast(Table, Series.__table__)
        competitions = cast(Table, Competition.__table__)
        games = cast(Table, Game.__table__)
        team_a = cast(Table, Team.__table__).alias("series_team_a")
        team_b = cast(Table, Team.__table__).alias("series_team_b")
        with self.engine.connect() as connection:
            starts = {
                series_id: (start_at, int(game_count))
                for series_id, start_at, game_count in connection.execute(
                    select(games.c.series_id, func.min(games.c.start_at), func.count(games.c.id))
                    .where(games.c.series_id.is_not(None))
                    .group_by(games.c.series_id)
                )
                if isinstance(series_id, UUID)
            }
            rows = (
                connection.execute(
                    select(
                        series,
                        competitions.c.display_name.label("competition_display_name"),
                        competitions.c.normalized_name.label("competition_normalized_name"),
                        competitions.c.source_competition_id.label("competition_source_id"),
                        team_a.c.display_name.label("team_a_display_name"),
                        team_a.c.normalized_name.label("team_a_normalized_name"),
                        team_a.c.source_team_id.label("team_a_source_id"),
                        team_b.c.display_name.label("team_b_display_name"),
                        team_b.c.normalized_name.label("team_b_normalized_name"),
                        team_b.c.source_team_id.label("team_b_source_id"),
                    )
                    .outerjoin(competitions, competitions.c.id == series.c.competition_id)
                    .join(team_a, team_a.c.id == series.c.team_one_id)
                    .join(team_b, team_b.c.id == series.c.team_two_id)
                    .order_by(series.c.scheduled_date.desc(), series.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(self._series_record(row, starts) for row in rows)

    def get_series(self, series_id: UUID) -> CanonicalSeriesRecord | None:
        return next(
            (series for series in self.list_series() if series.series_id == series_id), None
        )

    def list(self) -> tuple[Event, ...]:
        series = self.list_series()
        games = self.list_games()
        values = [self._series_event(item) for item in series]
        values.extend(
            event
            for item in games
            if item.series_id is None
            if (event := self._game_event(item)) is not None
        )
        return tuple(sorted(values, key=lambda item: (item.starts_at, item.event_id), reverse=True))

    def get(self, event_id: UUID) -> Event | None:
        return next((event for event in self.list() if event.event_id == event_id), None)

    @staticmethod
    def list_markets(event_id: UUID) -> tuple[Market, ...]:
        del event_id
        return ()

    def odds_history(self, event_id: UUID) -> tuple[OddsSnapshot, ...]:
        snapshots = cast(Table, OddsSnapshotRecord.__table__)
        providers = cast(Table, OddsProviderRecord.__table__)
        selections = cast(Table, ProviderOddsSelection.__table__)
        attempts = cast(Table, EventMappingAttempt.__table__)
        reviews = cast(Table, MappingReviewRecord.__table__)
        candidate_scores = cast(Table, EventMappingCandidateScore.__table__)
        approved_inversion = (
            select(candidate_scores.c.selections_inverted)
            .join(reviews, reviews.c.attempt_id == candidate_scores.c.attempt_id)
            .join(attempts, attempts.c.id == reviews.c.attempt_id)
            .where(
                attempts.c.provider_event_id == snapshots.c.event_id,
                reviews.c.selected_event_id == event_id,
                reviews.c.status == "approved",
                candidate_scores.c.canonical_event_id == event_id,
            )
            .order_by(reviews.c.reviewed_at.desc(), reviews.c.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        mapped_inversion = (
            select(attempts.c.selections_inverted)
            .where(
                attempts.c.provider_event_id == snapshots.c.event_id,
                attempts.c.selected_event_id == event_id,
                attempts.c.result_status == "auto_matched",
            )
            .order_by(attempts.c.evaluated_at.desc(), attempts.c.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(
                        snapshots,
                        providers.c.code.label("provider_code"),
                        selections.c.selection_type,
                        func.coalesce(mapped_inversion, approved_inversion, False).label(
                            "selections_inverted"
                        ),
                    )
                    .join(providers, providers.c.id == snapshots.c.provider_id)
                    .join(selections, selections.c.id == snapshots.c.selection_id)
                    .where(
                        or_(
                            snapshots.c.event_id == event_id,
                            exists(
                                select(attempts.c.id).where(
                                    attempts.c.provider_event_id == snapshots.c.event_id,
                                    attempts.c.selected_event_id == event_id,
                                    attempts.c.result_status == "auto_matched",
                                )
                            ),
                            exists(
                                select(reviews.c.id)
                                .join(attempts, attempts.c.id == reviews.c.attempt_id)
                                .where(
                                    attempts.c.provider_event_id == snapshots.c.event_id,
                                    reviews.c.selected_event_id == event_id,
                                    reviews.c.status == "approved",
                                )
                            ),
                        ),
                        snapshots.c.captured_at.is_not(None),
                    )
                    .order_by(snapshots.c.captured_at, snapshots.c.id)
                )
                .mappings()
                .all()
            )
        now = self.clock.now().value
        return tuple(self._odds_snapshot(row, now, event_id) for row in rows)

    @staticmethod
    def _odds_snapshot(row: RowMapping, now: datetime, canonical_event_id: UUID) -> OddsSnapshot:
        captured_at = cast(datetime, row["captured_at"])
        decimal_odds = cast(Decimal, row["decimal_odds"])
        selection = SelectionType(str(row["selection_type"]))
        if bool(row["selections_inverted"]):
            if selection is SelectionType.TEAM_A:
                selection = SelectionType.TEAM_B
            elif selection is SelectionType.TEAM_B:
                selection = SelectionType.TEAM_A
        return OddsSnapshot(
            odds_snapshot_id=cast(UUID, row["id"]),
            event_id=canonical_event_id,
            market_id=cast(UUID, row["market_id"]),
            selection=selection,
            provider=str(row["provider_code"]),
            provider_status=ProviderStatus(str(row["provider_status"])),
            market_status=MarketStatus(str(row["market_status"])),
            decimal_odds=decimal_odds,
            captured_at=captured_at,
            age_seconds=max(0, int((now - captured_at).total_seconds())),
            raw_implied_probability=Decimal(1) / decimal_odds,
            no_vig_probability=None,
            informational_only=bool(row["informational_only"]),
            provenance_reference=str(row["provenance_reference"]),
        )

    @staticmethod
    def _game_record(
        row: RowMapping,
        participants: dict[UUID, dict[str, tuple[UUID, str]]],
    ) -> CanonicalGameRecord:
        game_id = cast(UUID, row["id"])
        sides = participants.get(game_id, {})
        blue = sides.get("Blue")
        red = sides.get("Red")
        return CanonicalGameRecord(
            game_id=game_id,
            source_game_id=str(row["source_game_id"]),
            series_id=cast(UUID | None, row["series_id"]),
            competition=_competition_name(row),
            team_a_id=blue[0] if blue else None,
            team_a=blue[1] if blue else None,
            team_b_id=red[0] if red else None,
            team_b=red[1] if red else None,
            starts_at=cast(datetime | None, row["start_at"]),
            event_date=cast(date | None, row["event_date"]),
            quality_status=str(row["quality_status"]),
            observed_at=cast(datetime, row["processed_at"]),
            source_snapshot_id=cast(UUID, row["source_snapshot_id"]),
        )

    @staticmethod
    def _series_record(
        row: RowMapping,
        starts: dict[UUID, tuple[datetime | None, int]],
    ) -> CanonicalSeriesRecord:
        series_id = cast(UUID, row["id"])
        start_at = starts.get(series_id, (None, 0))[0]
        return CanonicalSeriesRecord(
            series_id=series_id,
            source_series_id=(
                str(row["source_series_id"]) if row["source_series_id"] is not None else None
            ),
            series_key=str(row["series_key"]),
            competition=_competition_name(row),
            team_a_id=cast(UUID, row["team_one_id"]),
            team_a=_prefixed_display_name(row, "team_a"),
            team_b_id=cast(UUID, row["team_two_id"]),
            team_b=_prefixed_display_name(row, "team_b"),
            starts_at=start_at,
            scheduled_date=cast(date | None, row["scheduled_date"]),
            best_of=cast(int | None, row["best_of"]),
            score_a=cast(int | None, row["score_one"]),
            score_b=cast(int | None, row["score_two"]),
            result_status=str(row["result_status"]),
            observed_at=cast(datetime, row["processed_at"]),
            source_snapshot_id=cast(UUID, row["source_snapshot_id"]),
        )

    @staticmethod
    def _series_event(record: CanonicalSeriesRecord) -> Event:
        start_at = _event_time(record.starts_at, record.scheduled_date)
        best_of = record.best_of or 1
        return Event(
            event_id=record.series_id,
            game_title=ContractGameTitle.LEAGUE_OF_LEGENDS,
            competition=record.competition,
            team_a_id=record.team_a_id,
            team_a=record.team_a,
            team_b_id=record.team_b_id,
            team_b=record.team_b,
            starts_at=start_at,
            best_of=max(1, min(best_of, 9)),
            status=EventStatus.FINISHED,
            observed_at=record.observed_at,
        )

    @staticmethod
    def _game_event(record: CanonicalGameRecord) -> Event | None:
        if (
            record.team_a_id is None
            or record.team_a is None
            or record.team_b_id is None
            or record.team_b is None
        ):
            return None
        return Event(
            event_id=record.game_id,
            game_title=ContractGameTitle.LEAGUE_OF_LEGENDS,
            competition=record.competition,
            team_a_id=record.team_a_id,
            team_a=record.team_a,
            team_b_id=record.team_b_id,
            team_b=record.team_b,
            starts_at=_event_time(record.starts_at, record.event_date),
            best_of=1,
            status=EventStatus.FINISHED,
            observed_at=record.observed_at,
        )


def _event_time(value: datetime | None, fallback: date | None) -> datetime:
    if value is not None:
        return value
    if fallback is not None:
        return datetime.combine(fallback, time.min, tzinfo=UTC)
    raise RuntimeError("un événement historique exige une date source")


def _display_name(row: object) -> str:
    values = cast(RowMapping, row)
    return str(values["display_name"] or values["normalized_name"] or values["source_team_id"])


def _prefixed_display_name(row: RowMapping, prefix: str) -> str:
    return str(
        row[f"{prefix}_display_name"]
        or row[f"{prefix}_normalized_name"]
        or row[f"{prefix}_source_id"]
    )


def _competition_name(row: RowMapping) -> str:
    return str(
        row["competition_display_name"]
        or row["competition_normalized_name"]
        or row["competition_source_id"]
        or "Non renseignée"
    )
