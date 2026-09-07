"""Canonical historical events projected once before filtering and pagination."""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    DateTime,
    RowMapping,
    Table,
    and_,
    false,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy import cast as sql_cast
from sqlalchemy.sql import ColumnElement, FromClause, Select, Subquery

from metiquo.contracts import Event
from metiquo.contracts.enums import EventStatus, GameTitle
from metiquo.db.core_models import Competition, Game, GameTeamStat, Series, Team


def display(table: FromClause, source: str) -> ColumnElement[str]:
    return func.coalesce(
        func.nullif(table.c.display_name, ""),
        func.nullif(table.c.normalized_name, ""),
        table.c[source],
    )


def event_projection() -> Subquery:
    series, games = cast(Table, Series.__table__), cast(Table, Game.__table__)
    competitions, stats = cast(Table, Competition.__table__), cast(Table, GameTeamStat.__table__)
    a, b = (
        cast(Table, Team.__table__).alias("event_a"),
        cast(Table, Team.__table__).alias("event_b"),
    )
    starts = (
        select(games.c.series_id, func.min(games.c.start_at).label("start_at"))
        .where(games.c.series_id.is_not(None))
        .group_by(games.c.series_id)
        .subquery("series_starts")
    )
    competition = func.coalesce(
        display(competitions, "source_competition_id"), "Non renseignée"
    ).label("competition")
    series_query = select(
        series.c.id.label("event_id"),
        competition,
        a.c.id.label("team_a_id"),
        display(a, "source_team_id").label("team_a"),
        b.c.id.label("team_b_id"),
        display(b, "source_team_id").label("team_b"),
        func.coalesce(
            starts.c.start_at, func.timezone("UTC", sql_cast(series.c.scheduled_date, DateTime()))
        ).label("starts_at"),
        func.greatest(1, func.least(func.coalesce(series.c.best_of, 1), 9)).label("best_of"),
        series.c.processed_at.label("observed_at"),
    ).select_from(
        series.outerjoin(competitions, competitions.c.id == series.c.competition_id)
        .join(a, a.c.id == series.c.team_one_id)
        .join(b, b.c.id == series.c.team_two_id)
        .outerjoin(starts, starts.c.series_id == series.c.id)
    )
    blue, red = stats.alias("event_blue"), stats.alias("event_red")
    game_query = (
        select(
            games.c.id.label("event_id"),
            competition,
            a.c.id.label("team_a_id"),
            display(a, "source_team_id").label("team_a"),
            b.c.id.label("team_b_id"),
            display(b, "source_team_id").label("team_b"),
            func.coalesce(
                games.c.start_at, func.timezone("UTC", sql_cast(games.c.event_date, DateTime()))
            ).label("starts_at"),
            literal(1).label("best_of"),
            games.c.processed_at.label("observed_at"),
        )
        .select_from(
            games.outerjoin(competitions, competitions.c.id == games.c.competition_id)
            .join(blue, and_(blue.c.game_id == games.c.id, blue.c.side == "Blue"))
            .join(red, and_(red.c.game_id == games.c.id, red.c.side == "Red"))
            .join(a, a.c.id == blue.c.team_id)
            .join(b, b.c.id == red.c.team_id)
        )
        .where(games.c.series_id.is_(None))
    )
    return union_all(series_query, game_query).subquery("canonical_events")


def event_from_row(row: RowMapping, prefix: str = "") -> Event:
    return Event(
        event_id=cast(UUID, row[prefix + "event_id"]),
        game_title=GameTitle.LEAGUE_OF_LEGENDS,
        competition=str(row[prefix + "competition"]),
        team_a_id=cast(UUID, row[prefix + "team_a_id"]),
        team_a=str(row[prefix + "team_a"]),
        team_b_id=cast(UUID, row[prefix + "team_b_id"]),
        team_b=str(row[prefix + "team_b"]),
        starts_at=cast(datetime, row[prefix + "starts_at"]),
        best_of=int(row[prefix + "best_of"]),
        status=EventStatus.FINISHED,
        observed_at=cast(datetime, row[prefix + "observed_at"]),
    )


def filter_events(
    statement: Select[tuple[Any, ...]],
    events: FromClause,
    *,
    competition: str | None = None,
    team: str | None = None,
    status: EventStatus | None = None,
    starts_from: datetime | None = None,
    starts_to: datetime | None = None,
    prefix: str = "",
) -> Select[tuple[Any, ...]]:
    if competition is not None:
        statement = statement.where(
            events.c[prefix + "competition"].icontains(competition, autoescape=True)
        )
    if team is not None:
        statement = statement.where(
            or_(
                events.c[prefix + "team_a"].icontains(team, autoescape=True),
                events.c[prefix + "team_b"].icontains(team, autoescape=True),
            )
        )
    if status is not None and status is not EventStatus.FINISHED:
        statement = statement.where(false())
    if starts_from is not None:
        statement = statement.where(events.c[prefix + "starts_at"] >= starts_from)
    if starts_to is not None:
        statement = statement.where(events.c[prefix + "starts_at"] <= starts_to)
    return statement
