"""API réelle de santé fournisseur et d'historique des cotes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

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
from metiquo.contracts import OddsCaptureResult, OddsSnapshot
from metiquo.contracts.enums import (
    EventStatus,
    GameTitle,
    MarketPeriod,
    MarketStatus,
    MarketType,
    ProviderStatus,
    SelectionType,
)
from metiquo.contracts.odds_provider import (
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
    ProviderSelection,
)
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.providers import provider_market_uuid
from metiquo.repositories.postgres_canonical import PostgresCanonicalRepository
from metiquo.services.odds_capture import OddsCaptureService, OddsCaptureSource
from tests.integration.test_canonical_series import _seed_series

_ROOT = Path(__file__).resolve().parents[2]
_NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


class _ReadyProbe:
    def check(self) -> ReadinessCheck:
        return ReadinessCheck(available=True)


@dataclass(slots=True)
class _HistoryProvider:
    provider_code: str
    event: ProviderEvent
    snapshot_event_id: UUID
    captured_at: datetime
    failing: bool = False

    def list_events(
        self,
        starts_from: datetime,
        starts_to: datetime,
        game_title: GameTitle,
    ) -> tuple[ProviderEvent, ...]:
        del starts_from, starts_to, game_title
        return (self.event,)

    def get_event_markets(self, provider_event_id: str) -> tuple[ProviderMarket, ...]:
        if self.failing:
            raise RuntimeError("fixture provider unavailable")
        if provider_event_id != self.event.provider_event_id:
            return ()
        return (
            ProviderMarket(
                provider_event_id=provider_event_id,
                provider_market_id="match-winner",
                raw_label="Match winner",
                market_type=MarketType.MATCH_WINNER,
                period=MarketPeriod.SERIES,
                selections=(
                    ProviderSelection(
                        provider_selection_id="team-a",
                        selection=SelectionType.TEAM_A,
                        label=self.event.participants[0],
                        decimal_odds=Decimal("2.00"),
                    ),
                ),
                status=MarketStatus.OPEN,
                captured_at=self.captured_at,
                settlement_rules_version="rules-v1",
            ),
        )

    def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult:
        market_id = provider_market_uuid(
            self.provider_code,
            provider_event_id,
            "match-winner",
        )
        return OddsCaptureResult(
            provider_event_id=provider_event_id,
            captured_at=self.captured_at,
            snapshots=(
                OddsSnapshot(
                    odds_snapshot_id=uuid4(),
                    event_id=self.snapshot_event_id,
                    market_id=market_id,
                    selection=SelectionType.TEAM_A,
                    provider=self.provider_code,
                    provider_status=ProviderStatus.OPERATIONAL,
                    market_status=MarketStatus.OPEN,
                    decimal_odds=Decimal("2.00"),
                    captured_at=self.captured_at,
                    age_seconds=30,
                    raw_implied_probability=Decimal("0.5"),
                    no_vig_probability=None,
                    provenance_reference="licensed-fixture:odd-009",
                ),
            ),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_code=self.provider_code,
            status=ProviderStatus.UNAVAILABLE if self.failing else ProviderStatus.OPERATIONAL,
            checked_at=_NOW,
            last_success_at=self.captured_at,
        )


def _settings(database_url: str) -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "real",
            "database_url": database_url,
            "object_store_root": str(_ROOT / ".unused-odds-api-store"),
            "odds_provider": "disabled",
            "odds_max_age_seconds": 90,
        }
    )


def _request(app: FastAPI, path: str) -> Response:
    async def send() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(send())


@pytest.mark.integration
def test_real_odds_history_and_provider_health_survive_capture_failure(
    postgresql_url: str,
) -> None:
    config = Config(_ROOT / "alembic.ini")
    config.attributes["database_url"] = postgresql_url
    command.upgrade(config, "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    identities = _seed_series(engine, "league_of_legends_match_data")
    CanonicalSeriesBuilder(engine=engine, clock=FixedClock(UtcInstant(_NOW))).build()
    canonical = PostgresCanonicalRepository(engine, FixedClock(UtcInstant(_NOW)))
    suffix = identities["blue_team"].removeprefix("team-blue-")
    event = next(item for item in canonical.list() if suffix.casefold() in item.team_a.casefold())
    provider_event = ProviderEvent(
        provider_event_id="licensed-event-009",
        game_title=event.game_title,
        competition=event.competition,
        participants=(event.team_a, event.team_b),
        starts_at=event.starts_at,
        best_of=event.best_of,
        status=EventStatus.FINISHED,
        collected_at=_NOW - timedelta(seconds=30),
        source_reference="licensed-fixture:event-009",
    )
    provider = _HistoryProvider(
        f"licensed-{uuid4().hex[:8]}",
        provider_event,
        event.event_id,
        _NOW - timedelta(seconds=30),
    )
    service = OddsCaptureService(engine, FixedClock(UtcInstant(_NOW)))
    source = OddsCaptureSource(
        "licensed_feed",
        "Licensed fixture",
        "licensed-fixture:payload-009",
    )

    report = service.capture_event(provider, provider_event, source)
    app = create_app(
        settings=_settings(postgresql_url),
        readiness_probe=_ReadyProbe(),
        clock=FixedClock(UtcInstant(_NOW)),
    )
    fresh_history = _request(app, f"/api/v1/events/{event.event_id}/odds-history")
    provider.failing = True
    with pytest.raises(RuntimeError, match="fixture provider unavailable"):
        service.capture_event(provider, provider_event, source)

    history = _request(app, f"/api/v1/events/{event.event_id}/odds-history")
    sources = _request(app, "/api/v1/admin/data-sources?limit=100")

    assert report.inserted_snapshots == 1
    assert fresh_history.json()["meta"]["freshness"] == "fresh"
    assert history.status_code == 200
    assert history.json()["page"]["total"] == 1
    assert history.json()["meta"]["freshness"] == "degraded"
    assert history.json()["meta"]["asOf"] == "2026-09-07T11:59:30Z"
    assert history.json()["data"][0]["ageSeconds"] == 30
    assert history.json()["data"][0]["decimalOdds"] == "2.00000000"
    provider_health = next(
        item for item in sources.json()["data"] if item["providerCode"] == provider.provider_code
    )
    assert provider_health == {
        "providerCode": provider.provider_code,
        "status": "degraded",
        "checkedAt": "2026-09-07T12:00:00Z",
        "lastSuccessAt": "2026-09-07T11:59:30Z",
        "lastCaptureAt": "2026-09-07T11:59:30Z",
        "ageSeconds": 30,
        "failureCount": 1,
        "freshness": "degraded",
        "detail": "Capture échouée (RuntimeError) ; historique valide conservé",
    }
    engine.dispose()
