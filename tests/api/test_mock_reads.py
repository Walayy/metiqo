"""Contrats HTTP des lectures métier en mode mock."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient, Response

from metiquo.api.app import create_app
from metiquo.api.readiness import ReadinessCheck
from metiquo.config import Settings
from metiquo.foundation.time import FixedClock, UtcInstant

REFERENCE_TIME = datetime(2026, 9, 4, 12, tzinfo=UTC)


class ReadyProbe:
    def check(self) -> ReadinessCheck:
        return ReadinessCheck(available=True)


def build_app() -> FastAPI:
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "mock",
            "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "odds_provider": "mock",
            "mock_seed": "metiquo-api-test",
        }
    )
    return create_app(
        settings=settings,
        readiness_probe=ReadyProbe(),
        clock=FixedClock(UtcInstant(REFERENCE_TIME)),
    )


def get(app: FastAPI, path: str) -> Response:
    async def send_request() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(send_request())


def assert_mock_metadata(payload: dict[str, object]) -> None:
    assert payload["meta"] == {
        "dataMode": "mock",
        "freshness": "fresh",
        "asOf": "2026-09-04T12:00:00Z",
        "computedAt": "2026-09-04T12:00:00Z",
        "appVersion": "0.1.0",
    }


def test_opportunities_support_typed_filters_pagination_and_empty_results() -> None:
    app = build_app()

    response = get(
        app,
        "/api/v1/opportunities?grade=STRONG_VALUE&minConfidence=0.80&offset=0&limit=1",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == {"offset": 0, "limit": 1, "total": 1}
    assert len(payload["data"]) == 1
    assert payload["data"][0]["value"]["grade"] == "STRONG_VALUE"
    assert_mock_metadata(payload)

    empty = get(app, "/api/v1/opportunities?competition=aucune-ligue")
    assert empty.status_code == 200
    assert empty.json()["data"] == []
    assert empty.json()["page"]["total"] == 0

    invalid = get(app, "/api/v1/opportunities?limit=0")
    assert invalid.status_code == 422
    assert invalid.headers["content-type"] == "application/problem+json"


def test_opportunity_detail_and_explanation_share_versioned_metadata() -> None:
    app = build_app()
    listing = get(app, "/api/v1/opportunities?limit=1").json()
    signal_id = listing["data"][0]["signalId"]

    detail = get(app, f"/api/v1/opportunities/{signal_id}")
    explanation = get(app, f"/api/v1/opportunities/{signal_id}/explanation")

    assert detail.status_code == 200
    assert explanation.status_code == 200
    assert detail.json()["data"]["signalId"] == signal_id
    assert explanation.json()["data"]["signalId"] == signal_id
    assert explanation.json()["data"]["reasons"]
    assert_mock_metadata(detail.json())
    assert_mock_metadata(explanation.json())


def test_event_markets_and_append_only_odds_history_are_exposed() -> None:
    app = build_app()
    events = get(app, "/api/v1/events?team=Aurore&limit=100")
    assert events.status_code == 200
    assert events.json()["page"]["total"] == 12
    event_id = events.json()["data"][9]["eventId"]

    detail = get(app, f"/api/v1/events/{event_id}")
    markets = get(app, f"/api/v1/events/{event_id}/markets")
    history = get(app, f"/api/v1/events/{event_id}/odds-history")

    assert detail.status_code == 200
    assert markets.json()["page"]["total"] == 1
    assert history.json()["page"]["total"] == 2
    captured = [snapshot["capturedAt"] for snapshot in history.json()["data"]]
    assert captured == sorted(captured)


def test_models_backtests_paper_and_admin_reads_are_available() -> None:
    app = build_app()
    expected_totals = {
        "/api/v1/models": 12,
        "/api/v1/backtests": 12,
        "/api/v1/paper-bets": 2,
        "/api/v1/admin/data-sources": 1,
        "/api/v1/admin/ingestion-runs": 2,
        "/api/v1/admin/quality-issues": 8,
        "/api/v1/admin/jobs": 3,
        "/api/v1/admin/mappings/pending": 1,
    }
    for path, total in expected_totals.items():
        response = get(app, path)
        assert response.status_code == 200, path
        assert response.json()["page"]["total"] == total, path
        assert response.json()["meta"]["dataMode"] == "mock", path

    model = get(app, "/api/v1/models?limit=1").json()["data"][0]
    backtest = get(app, "/api/v1/backtests?limit=1").json()["data"][0]
    paper_bet = get(app, "/api/v1/paper-bets?limit=1").json()["data"][0]
    assert get(app, f"/api/v1/models/{model['modelVersionId']}").status_code == 200
    assert get(app, f"/api/v1/backtests/{backtest['backtestId']}").status_code == 200
    assert get(app, f"/api/v1/paper-bets/{paper_bet['paperBetId']}").status_code == 200


def test_unknown_resources_return_problem_details() -> None:
    app = build_app()

    for path in (
        f"/api/v1/opportunities/{uuid4()}",
        f"/api/v1/events/{uuid4()}",
        f"/api/v1/models/{uuid4()}",
        f"/api/v1/backtests/{uuid4()}",
        f"/api/v1/paper-bets/{uuid4()}",
    ):
        response = get(app, path)
        assert response.status_code == 404, path
        assert response.headers["content-type"] == "application/problem+json", path
        assert response.json()["code"] == "NOT_FOUND", path
