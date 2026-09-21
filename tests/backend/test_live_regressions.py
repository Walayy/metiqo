"""Regression cases found during the v1-ajout-live review."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from metiquo_api.main import _match_maps, create_app
from metiquo_core.config import Settings
from metiquo_core.matches import source_game, unique_bans
from metiquo_core.models import (
    Dataset,
    DatasetVersion,
    EsportMatch,
    IngestionRun,
    League,
    MatchSnapshot,
    MatchSourceLink,
    OracleRow,
    Team,
)
from metiquo_worker.matching import MatchIdentity, resolve_match, resolve_team
from metiquo_worker.oracle_match_sync import _build_map, _timestamp, sync_oracle_match_details
from metiquo_worker.sofascore_sync import _payload, _save_event
from metiquo_worker.sources import sofascore
from sqlalchemy import select
from sqlalchemy.orm import Session


def identities():
    league = League(id="league", data={"id": "league", "name": "Cup", "slug": "cup"})
    home = Team(id="home", league_id=league.id, data={"name": "Alpha", "id": "home"})
    away = Team(id="away", league_id=league.id, data={"name": "Beta", "id": "away"})
    return league, home, away


def event():
    return sofascore.SofaEvent(
        source_id="42",
        url="https://www.sofascore.com/esports/match/alpha-beta#id:42",
        home_name="Alpha",
        away_name="Beta",
        competition="Cup",
        competition_source_id="1",
        competition_slug="cup",
        home_source_id="10",
        away_source_id="20",
        home_image="",
        away_image="",
        competition_image="",
        starts_at=datetime.now(UTC),
        status="live",
        best_of=3,
        home_score=1,
        away_score=0,
        payload={},
    )


def test_team_ties_and_reverse_academy_matching_are_rejected():
    academy = Team(id="academy", league_id="league", data={"name": "Alpha Academy"})
    assert resolve_team("Alpha", [academy]) is None
    _, home, _ = identities()
    duplicate = Team(id="other-alpha", league_id="league", data={"name": "Alpha"})
    assert resolve_team("Alpha", [home, duplicate]) is None


def test_duplicate_ban_from_provider_does_not_break_the_entire_match_feed():
    bans = [
        {"teamId": team, "champion": f"champion-{i}", "championImage": ""}
        for team in ["home", "away"]
        for i in range(5)
    ]
    assert len(unique_bans([*bans, bans[-1]])) == 10
    assert unique_bans([*bans, {"teamId": "away", "champion": "extra"}]) == []


def test_other_competition_match_is_not_reused():
    league, home, away = identities()
    at = datetime.now(UTC)
    match = EsportMatch(
        id=uuid4(), home_id=home.id, away_id=away.id, league_id="other", starts_at=at, format="BO3"
    )
    result = resolve_match(
        MatchIdentity("Alpha", "Beta", at, "Cup", "sofascore", "42"),
        [home, away],
        [league],
        [match],
    )
    assert result is not None and result.existing_match is None


def test_oracle_date_does_not_invent_a_timezone():
    assert _timestamp({"date": "2026-09-20 12:00:00"}) is None
    assert _timestamp({"date": "2026-09-20 12:00:00"}, "Europe/Paris") == datetime(
        2026, 9, 20, 10, tzinfo=UTC
    )
    assert _timestamp({"date": "2026-09-20T12:00:00+02:00"}) == datetime(
        2026, 9, 20, 10, tzinfo=UTC
    )


def oracle_rows():
    rows = []
    for name, side, base, winner in [("Alpha", "Blue", 1, "1"), ("Beta", "Red", 6, "0")]:
        common = {
            "teamname": name,
            "side": side,
            "game": "1",
            "gamelength": "1800",
            "result": winner,
            "date": "2026-09-20T12:00:00Z",
            "league": "Cup",
        }
        rows.append(
            OracleRow(
                game_id="game",
                participant_id="100" if base == 1 else "200",
                payload={**common, "position": "team"},
            )
        )
        for index, role in enumerate(["top", "jng", "mid", "bot", "sup"]):
            rows.append(
                OracleRow(
                    game_id="game",
                    participant_id=str(base + index),
                    payload={
                        **common,
                        "position": role,
                        "playername": f"p{base + index}",
                        "kills": "1",
                        "deaths": "1",
                        "assists": "2",
                        "total cs": "100",
                    },
                )
            )
    return rows


def test_optional_oracle_objectives_stay_unknown_and_bad_game_is_isolated():
    league, home, away = identities()
    match = EsportMatch(
        id=uuid4(), home_id=home.id, away_id=away.id, league_id=league.id, format="BO1"
    )
    rows = oracle_rows()
    projected = _build_map("game", rows, match, {home.id: home, away.id: away})
    assert projected is not None
    assert projected[0]["sides"][0]["grubs"] is None
    rows[1].payload.pop("kills")
    assert _build_map("game", rows, match, {home.id: home, away.id: away}) is None


def test_sofascore_score_does_not_replace_missing_side_with_zero():
    _, home, away = identities()
    assert _payload(replace(event(), away_score=None), home, away)["currentScore"] is None
    assert _payload(event(), home, away)["seriesScore"] == {"home": 1, "away": 0}


def test_sofascore_cooldown_does_not_return_cached_observations(monkeypatch):
    monkeypatch.setattr(
        sofascore,
        "_STATE",
        sofascore._ScrapeState(blocked_until=float("inf"), events={"42": event()}),
    )
    settings = Settings(database_url="postgresql://unused", sofascore_enabled=True)
    with pytest.raises(sofascore.SofaScoreBlocked):
        sofascore.scrape(settings)


def test_finished_event_without_maps_is_retried(monkeypatch):
    finished = replace(event(), status="finished")
    monkeypatch.setattr(
        sofascore,
        "_STATE",
        sofascore._ScrapeState(events={"42": finished}, event_fetched_at={"42": 1}),
    )
    settings = Settings(database_url="postgresql://unused")
    link = sofascore.SofaLink(finished.url, "42", finished.starts_at.date(), "Alpha - Beta")
    assert not sofascore._should_refresh_event(link, 120, settings)
    assert sofascore._should_refresh_event(link, 302, settings)


def test_cached_schedule_is_not_returned_as_a_new_observation(monkeypatch):
    now = datetime.now(sofascore.PARIS)
    current = now.date()
    days = tuple(current + timedelta(days=i) for i in [*range(8), *range(-7, 0)])
    cached = replace(event(), status="scheduled", starts_at=now + timedelta(hours=10))
    link = sofascore.SofaLink(cached.url, "42", current, "Alpha - Beta")
    monkeypatch.setattr(
        sofascore,
        "_STATE",
        sofascore._ScrapeState(
            listing_days=days,
            listing_cursor=15,
            listing_complete_at=sofascore.clock.monotonic(),
            day_fetched_at={day.isoformat(): sofascore.clock.monotonic() for day in days},
            links={"42": link},
            events={"42": cached},
            event_fetched_at={"42": sofascore.clock.monotonic()},
        ),
    )
    monkeypatch.setattr(sofascore, "_browser_page", lambda _: object())
    assert (
        sofascore.scrape(Settings(database_url="postgresql://unused", sofascore_enabled=True)) == []
    )


def test_game_category_is_read_from_the_event_not_the_listing_link(monkeypatch):
    raw = {"tournament": {"category": {"slug": "dota2"}}}
    assert source_game({"event": raw}) == "dota2"
    monkeypatch.setattr(sofascore, "_event_from_next", lambda _: raw)

    class Page:
        def content(self):
            return "source"

    assert (
        sofascore._event_from_page(
            Page(), sofascore.SofaLink("lol-listing", "42", datetime.now(UTC).date(), "PGL")
        )
        is None
    )


@pytest.mark.integration
def test_repeated_source_state_remains_the_latest_observation(database):
    engine, _ = database
    league, home, away = identities()
    at = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.add(league)
        session.flush()
        session.add_all([home, away])
        session.flush()
        for index, status in enumerate(["scheduled", "live", "scheduled", "scheduled"]):
            value = replace(event(), status=status, starts_at=at)
            _save_event(
                session,
                value,
                league,
                home,
                away,
                [home, away],
                [league],
                [],
                at + timedelta(seconds=index),
            )
            session.flush()
        history = session.scalars(select(MatchSnapshot).order_by(MatchSnapshot.observed_at)).all()
        assert [row.status for row in history] == ["scheduled", "live", "scheduled"]
        link = session.scalar(select(MatchSourceLink))
        assert link.last_seen_at == at + timedelta(seconds=3)


def snapshot(match, number, *, status="finished", score=None, observed_at=None):
    return MatchSnapshot(
        id=uuid4(),
        match_id=match.id,
        source="sofascore",
        status="finished",
        observed_at=observed_at or datetime.now(UTC),
        payload={
            "format": "BO3",
            "currentScore": score or {"home": 2, "away": 0},
            "maps": [
                {
                    "number": number,
                    "status": status,
                    "winnerId": "home" if status == "finished" else None,
                    "durationSeconds": None,
                    "bans": [],
                    "sides": [
                        {
                            "teamId": team,
                            "side": color,
                            "towers": None,
                            "dragons": None,
                            "barons": None,
                            "players": [],
                        }
                        for team, color in [("home", "blue"), ("away", "red")]
                    ],
                }
            ],
        },
    )


def test_partial_snapshots_preserve_each_completed_map_without_inventing_sides():
    match = EsportMatch(id=uuid4(), home_id="home", away_id="away", format="BO3")
    first, second = snapshot(match, 1), snapshot(match, 2)
    maps = _match_maps([first, second], match, "finished", second)
    assert [item["number"] for item in maps] == [1, 2]
    assert all(side["side"] is None for item in maps for side in item["sides"])


@pytest.mark.integration
def test_finished_api_match_keeps_sourced_score_with_partial_map_details(database):
    engine, settings = database
    league, home, away = identities()
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.add(league)
        session.flush()
        session.add_all([home, away])
        session.flush()
        match = EsportMatch(
            id=uuid4(),
            source="sofascore",
            source_id="42",
            league_id=league.id,
            home_id=home.id,
            away_id=away.id,
            starts_at=now,
            registered_at=now,
            format="BO3",
        )
        session.add(match)
        session.flush()
        observed = snapshot(match, 2)
        observed.source_id = "42"
        observed.source_url = event().url
        observed.sha256 = "a" * 64
        session.add(observed)
    with TestClient(create_app(settings)) as client:
        item = client.get("/api/v1/matches").json()["items"][0]
        assert item["status"] == "finished"
        assert item["seriesScore"] == {"home": 2, "away": 0}
        assert item["maps"][0]["number"] == 2


@pytest.mark.integration
@pytest.mark.parametrize("format_name, expected", [("BO1", 1), ("BO3", 0), ("BO5", 0)])
def test_oracle_projection_never_closes_a_partial_series(database, format_name, expected):
    engine, _ = database
    league, home, away = identities()
    at = datetime(2026, 9, 20, 12, tzinfo=UTC)
    run_id, version_id, match_id = uuid4(), uuid4(), uuid4()
    with Session(engine) as session, session.begin():
        session.add_all([league, IngestionRun(id=run_id, source="oracles-elixir", scope="2026")])
        session.flush()
        session.add_all(
            [
                home,
                away,
                Dataset(
                    id="oracle:2026",
                    source="oracles-elixir",
                    source_file_id="csv",
                    filename="test.csv",
                    file_year=2026,
                    checked_at=at,
                ),
            ]
        )
        session.flush()
        session.add(
            DatasetVersion(
                id=version_id,
                dataset_id="oracle:2026",
                run_id=run_id,
                sha256="a" * 64,
                artifact_path="unused.csv",
                byte_count=1,
                row_count=12,
                columns=[],
                retrieved_at=at,
            )
        )
        session.add(
            EsportMatch(
                id=match_id,
                source="sofascore",
                source_id="42",
                league_id=league.id,
                home_id=home.id,
                away_id=away.id,
                starts_at=at,
                registered_at=at,
                format=format_name,
            )
        )
        session.flush()
        session.get(Dataset, "oracle:2026").active_version_id = version_id
        for number, row in enumerate(oracle_rows(), 1):
            row.version_id, row.row_number = version_id, number
            session.add(row)
    result = sync_oracle_match_details(engine, observed_at=at + timedelta(days=1))
    assert result["published"] == expected
    assert sync_oracle_match_details(engine)["published"] == 0
    with Session(engine) as session:
        assert session.get(EsportMatch, match_id).format == format_name
        link = session.scalar(select(MatchSourceLink))
        if expected:
            assert link.last_seen_at == at
        else:
            assert link is None


@pytest.mark.integration
def test_legacy_other_game_is_excluded_without_deleting_evidence(database):
    engine, settings = database
    league, home, away = identities()
    at = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.add(league)
        session.flush()
        session.add_all([home, away])
        session.flush()
        match = EsportMatch(
            id=uuid4(),
            source="sofascore",
            source_id="42",
            league_id=league.id,
            home_id=home.id,
            away_id=away.id,
            starts_at=at,
            registered_at=at,
            format="BO3",
        )
        session.add(match)
        session.flush()
        row = snapshot(match, 1)
        row.source_id, row.source_url, row.sha256 = "42", event().url, "a" * 64
        row.payload["event"] = {"tournament": {"category": {"slug": "dota2"}}}
        session.add(row)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/matches").json()["items"] == []
    with Session(engine) as session:
        assert session.scalar(select(MatchSnapshot)) is not None


@pytest.mark.integration
def test_migration_repairs_inferred_format_from_explicit_source(database):
    engine, _ = database
    command.downgrade(Config("alembic.ini"), "0007")
    league, home, away = identities()
    now, match_id = datetime.now(UTC), uuid4()
    with Session(engine) as session, session.begin():
        session.add(league)
        session.flush()
        session.add_all([home, away])
        session.flush()
        match = EsportMatch(
            id=match_id,
            source="sofascore",
            source_id="42",
            league_id=league.id,
            home_id=home.id,
            away_id=away.id,
            starts_at=now,
            registered_at=now,
            format="BO1",
        )
        session.add(match)
        session.flush()
        row = snapshot(match, 1)
        row.source_id, row.source_url, row.sha256 = "42", event().url, "a" * 64
        row.payload["event"] = {"bestOf": 5}
        session.add(row)
    command.upgrade(Config("alembic.ini"), "head")
    with Session(engine) as session:
        assert session.get(EsportMatch, match_id).format == "BO5"
        assert session.scalar(select(MatchSnapshot)).sha256 == "a" * 64
