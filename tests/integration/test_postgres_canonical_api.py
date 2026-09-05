"""Contrat mock/réel des repositories et API d'événements historiques."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient, Response
from sqlalchemy import create_engine

from metiquo.api.app import create_app
from metiquo.api.readiness import ReadinessCheck
from metiquo.canonical.series import CanonicalSeriesBuilder
from metiquo.config import Settings
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.repositories.postgres_canonical import PostgresCanonicalRepository
from tests.integration.test_canonical_series import _seed_series

_ROOT = Path(__file__).resolve().parents[2]
_NOW = datetime(2026, 9, 6, 13, 0, tzinfo=UTC)


class _ReadyProbe:
    def check(self) -> ReadinessCheck:
        return ReadinessCheck(available=True)


def _alembic_config(url: str) -> Config:
    config = Config(_ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


def _settings(database_url: str, mode: str) -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": mode,
            "database_url": database_url,
            "object_store_root": str(_ROOT / ".unused-canonical-api-store"),
            "odds_provider": "disabled" if mode == "real" else "mock",
            "mock_seed": "canonical-api-contract",
        }
    )


def _request(app: FastAPI, path: str) -> Response:
    async def send() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(send())


@pytest.mark.integration
def test_real_canonical_repositories_and_event_api_match_mock_contract(
    postgresql_url: str,
) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    identities = _seed_series(engine, "league_of_legends_match_data")
    CanonicalSeriesBuilder(engine=engine, clock=FixedClock(UtcInstant(_NOW))).build()
    repository = PostgresCanonicalRepository(engine)

    suffix = identities["blue_team"].removeprefix("team-blue-")
    teams = tuple(team for team in repository.list_teams() if suffix in team.source_team_id)
    games = tuple(
        game for game in repository.list_games() if game.source_game_id in identities["all_games"]
    )
    series = tuple(
        item
        for item in repository.list_series()
        if suffix.casefold() in item.team_a.casefold()
        or suffix.casefold() in item.team_b.casefold()
    )
    events = tuple(
        event for event in repository.list() if suffix.casefold() in event.team_a.casefold()
    )

    assert len(teams) == 2
    assert len(games) == 6
    assert len(series) == 2
    assert len(events) == 4
    assert {event.best_of for event in events} == {1, 2, 3}
    assert all(event.status.value == "finished" for event in events)
    assert all(repository.get_team(team.team_id) == team for team in teams)
    assert all(repository.get_game(game.game_id) == game for game in games)
    assert all(repository.get_series(item.series_id) == item for item in series)
    assert all(repository.get(event.event_id) == event for event in events)
    assert repository.list_markets(events[0].event_id) == ()
    assert repository.odds_history(events[0].event_id) == ()

    clock = FixedClock(UtcInstant(datetime(2026, 9, 6, 7, 0, tzinfo=UTC)))
    real_app = create_app(
        settings=_settings(postgresql_url, "real"),
        readiness_probe=_ReadyProbe(),
        clock=clock,
    )
    mock_app = create_app(
        settings=_settings(postgresql_url, "mock"),
        readiness_probe=_ReadyProbe(),
        clock=clock,
    )
    response = _request(real_app, f"/api/v1/events?team={suffix}&offset=0&limit=2")
    payload = response.json()

    assert response.status_code == 200
    assert payload["page"] == {"offset": 0, "limit": 2, "total": 4}
    assert payload["meta"]["dataMode"] == "real"
    assert payload["meta"]["freshness"] == "fresh"
    assert payload["meta"]["computedAt"] == payload["meta"]["asOf"]
    assert len(payload["data"]) == 2
    competition = _request(real_app, f"/api/v1/events?competition={suffix}&status=finished")
    dated = _request(real_app, f"/api/v1/events?team={suffix}&startsFrom=2026-08-03T00:00:00Z")
    invalid_period = _request(
        real_app,
        "/api/v1/events?startsFrom=2026-08-04T00:00:00Z&startsTo=2026-08-03T00:00:00Z",
    )
    assert competition.json()["page"]["total"] == 4
    assert dated.json()["page"]["total"] == 3
    assert invalid_period.status_code == 400
    mock_event = _request(mock_app, "/api/v1/events?limit=1").json()["data"][0]
    assert set(payload["data"][0]) == set(mock_event)

    event_id = payload["data"][0]["eventId"]
    detail = _request(real_app, f"/api/v1/events/{event_id}")
    markets = _request(real_app, f"/api/v1/events/{event_id}/markets")
    odds = _request(real_app, f"/api/v1/events/{event_id}/odds-history")
    opportunities = _request(real_app, "/api/v1/opportunities")
    assert detail.status_code == 200
    assert set(detail.json()["data"]) == set(mock_event)
    assert markets.json()["page"]["total"] == 0
    assert odds.json()["page"]["total"] == 0
    assert opportunities.json()["page"]["total"] == 0
    assert _request(real_app, f"/api/v1/events/{uuid4()}").status_code == 404
    engine.dispose()
