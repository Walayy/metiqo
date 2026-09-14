"""Import et API sur PostgreSQL à partir de relevés Stake réellement consultés."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select

from metiquo.api.app import create_app
from metiquo.api.openapi import ContractReadinessProbe
from metiquo.config import Settings
from metiquo.contracts import OddsCaptureResult
from metiquo.db.odds_models import OddsProviderHealth, OddsSnapshotRecord, ProviderOddsEvent
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.services.odds_capture import (
    OddsCaptureService,
    OddsCaptureSource,
    OddsCaptureValidationError,
)
from metiquo.services.odds_import import import_odds_file
from tests.integration.test_migrations import alembic_config
from tests.integration.test_odds_capture_history import _REFERENCE_TIME, _ChangingProvider

FIXTURE = Path(__file__).parents[1] / "fixtures/odds/stake-observed-20260908.json"
OBSERVED_AT = datetime(2026, 9, 8, 15, 39, 40, tzinfo=UTC)


def _settings(url: str, root: Path) -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "real",
            "odds_provider": "disabled",
            "database_url": url,
            "object_store_root": root,
        }
    )


def _get(app: FastAPI, path: str) -> tuple[int, dict[str, Any]]:
    async def request() -> tuple[int, dict[str, Any]]:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            response = await client.get(path)
            return response.status_code, response.json()

    return asyncio.run(request())


@pytest.mark.integration
def test_observed_stake_import_replay_api_pagination_and_freshness(
    postgresql_url: str,
    tmp_path: Path,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = _settings(postgresql_url, tmp_path)
    clock = FixedClock(UtcInstant(OBSERVED_AT + timedelta(seconds=15)))
    first = import_odds_file(engine, settings, FIXTURE, "stake-observed", "json", clock=clock)
    replay = import_odds_file(engine, settings, FIXTURE, "stake-observed", "json", clock=clock)
    assert first["events"] == 2
    assert first["insertedSnapshots"] == 14
    assert replay["insertedSnapshots"] == 0
    assert replay["duplicateSnapshots"] == 14
    raw = tmp_path / str(first["rawPayloadReference"])
    assert raw.read_bytes() == FIXTURE.read_bytes()
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(OddsSnapshotRecord)) == 14
        assert connection.scalar(select(func.count()).select_from(ProviderOddsEvent)) == 2
        assert set(connection.scalars(select(OddsProviderHealth.last_success_at))) == {OBSERVED_AT}
    app = create_app(settings=settings, clock=clock, readiness_probe=ContractReadinessProbe())
    status, response = _get(app, "/api/v1/odds/quotes?limit=100")
    assert status == 200
    data = response["data"]
    assert isinstance(data, list) and len(data) == 14
    assert {q["decimalOdds"] for q in data if q["period"] == "SERIES"} == {
        "2.05000000",
        "1.78000000",
    }
    assert all(q["event"]["bestOf"] is None and q["informationalOnly"] for q in data)
    assert all(q["freshness"] == "fresh" and q["ageSeconds"] == 15 for q in data)
    assert all(q["event"]["startsAt"] > "2026-09-08" for q in data)
    status, response = _get(app, "/api/v1/odds/quotes?offset=100&limit=2")
    assert status == 200 and response["data"] == []
    assert response["page"] == {"offset": 100, "limit": 2, "total": 14}
    _, response = _get(app, "/api/v1/odds/quotes?startsFrom=2026-09-12T00:00:00Z")
    assert len(response["data"]) == 2
    _, response = _get(app, "/api/v1/odds/quotes?provider=missing")
    assert response["data"] == []
    assert _get(app, "/api/v1/odds/quotes?startsFrom=2026-09-12")[0] == 400
    assert _get(app, "/api/v1/odds/quotes?limit=101")[0] == 422
    stale_app = create_app(
        settings=settings,
        clock=FixedClock(UtcInstant(OBSERVED_AT + timedelta(hours=1))),
        readiness_probe=ContractReadinessProbe(),
    )
    _, response = _get(stale_app, "/api/v1/odds/quotes?limit=100")
    assert all(q["freshness"] == "stale" for q in response["data"])
    app.state.real_admin_engine.dispose()
    stale_app.state.real_admin_engine.dispose()
    engine.dispose()


@pytest.mark.integration
def test_invalid_document_does_not_publish_or_archive_partial_odds(
    postgresql_url: str,
    tmp_path: Path,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows[-1]["decimal_odds"] = "NaN"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValueError, match="Document de cotes refusé"):
        import_odds_file(
            engine, _settings(postgresql_url, tmp_path / "objects"), path, "stake-observed", "json"
        )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(OddsSnapshotRecord)) == 0
    assert not (tmp_path / "objects").exists()
    engine.dispose()


@pytest.mark.integration
def test_capture_received_after_request_start_is_not_a_future_capture(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)

    class AdvancingClock:
        value = _REFERENCE_TIME

        def now(self) -> UtcInstant:
            return UtcInstant(self.value)

    clock = AdvancingClock()

    class DelayedProvider(_ChangingProvider):
        def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult:
            self.state = 1
            clock.value = _REFERENCE_TIME + timedelta(minutes=1)
            return super().capture_snapshot(provider_event_id)

    provider = DelayedProvider("delayed-provider")
    report = OddsCaptureService(engine, clock).capture_event(
        provider,
        provider.event(),
        OddsCaptureSource("licensed_feed", "Delayed test", "fixture:delayed"),
    )
    assert report.inserted_snapshots == 1
    with engine.connect() as connection:
        assert connection.scalar(select(OddsSnapshotRecord.recorded_at)) == clock.value
    engine.dispose()


@pytest.mark.integration
def test_reused_snapshot_id_with_changed_content_is_rejected(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    provider = _ChangingProvider("immutable-provider")
    service = OddsCaptureService(engine, FixedClock(UtcInstant(_REFERENCE_TIME)))
    source = OddsCaptureSource("licensed_feed", "Immutable test", "fixture:original")
    service.capture_event(provider, provider.event(), source)
    with pytest.raises(OddsCaptureValidationError, match="immuable"):
        service.capture_event(
            provider,
            provider.event(),
            OddsCaptureSource("licensed_feed", "Immutable test", "fixture:different-content"),
        )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(OddsSnapshotRecord)) == 1
        assert (
            connection.scalar(select(OddsSnapshotRecord.raw_payload_reference))
            == "fixture:original"
        )
    engine.dispose()


@pytest.mark.integration
def test_genuinely_future_capture_is_still_rejected(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    provider = _ChangingProvider("future-provider", state=1)
    service = OddsCaptureService(engine, FixedClock(UtcInstant(_REFERENCE_TIME)))
    with pytest.raises(OddsCaptureValidationError, match="future"):
        service.capture_event(
            provider,
            provider.event(),
            OddsCaptureSource("licensed_feed", "Future test", "fixture:future"),
        )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(OddsSnapshotRecord)) == 0
        assert connection.scalar(select(OddsProviderHealth.status)) == "unavailable"
    engine.dispose()


@pytest.mark.integration
def test_multi_event_import_rolls_back_when_later_capture_fails(
    postgresql_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    original = OddsCaptureService.capture_event
    count = 0

    def fail_second(*args: Any, **kwargs: Any) -> Any:
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("failure on second event")
        return original(*args, **kwargs)

    monkeypatch.setattr(OddsCaptureService, "capture_event", fail_second)
    with pytest.raises(RuntimeError, match="second event"):
        import_odds_file(
            engine, _settings(postgresql_url, tmp_path), FIXTURE, "stake-observed", "json"
        )
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(OddsSnapshotRecord)) == 0
        assert connection.scalar(select(func.count()).select_from(ProviderOddsEvent)) == 0
    engine.dispose()
