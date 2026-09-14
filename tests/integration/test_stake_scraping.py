"""Chaîne complète DOM relevé → stockage → HTTP, avec PostgreSQL jetable."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import DBAPIError

from metiquo.api.app import create_app
from metiquo.api.openapi import ContractReadinessProbe
from metiquo.config import Settings
from metiquo.db.odds_models import OddsSnapshotRecord, StakePageCapture, StakeScrapeRun
from metiquo.foundation.time import UtcInstant
from metiquo.operations.backup import BackupService
from metiquo.operations.restore import RestoreRequest, RestoreService
from metiquo.providers.stake_browser import ScrapeResult
from metiquo.providers.stake_parser import StakeScrapeError
from metiquo.services.stake_scraping import scrape_stake
from tests.integration.test_migrations import alembic_config
from tests.integration.test_observed_odds import _get
from tests.operations.support import postgres_tools
from tests.providers.test_stake_scraping import REPLAY_TIME, recorded_capture


class ReplayClock:
    def __init__(self, value: datetime = REPLAY_TIME) -> None:
        self.value = value

    def now(self) -> UtcInstant:
        return UtcInstant(self.value)


class RecordedScraper:
    calls = 0
    blocked = False

    async def collect(self, urls: Sequence[str] = ()) -> ScrapeResult:
        del urls
        self.calls += 1
        if self.blocked:
            raise StakeScrapeError("HTTP_403", "Accès refusé", blocked=True)
        return ScrapeResult((recorded_capture(),), (), 1)


def settings_for(url: str, root: Path) -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "real",
            "odds_provider": "stake_public",
            "database_url": url,
            "object_store_root": root,
        }
    )


@pytest.mark.integration
def test_refusal_mid_collection_preserves_capture_and_applies_backoff(
    postgresql_url: str, tmp_path: Path
) -> None:
    class InterruptedScraper:
        async def collect(self, urls: Sequence[str] = ()) -> ScrapeResult:
            return ScrapeResult((recorded_capture(),), ("other-match:HTTP_429",), 2, blocked=True)

    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings, clock = settings_for(postgresql_url, tmp_path), ReplayClock()
    try:
        report = scrape_stake(engine, settings, clock=clock, scraper=InterruptedScraper())
        assert report["state"] == "blocked" and report["events"] == 1
        assert report["insertedSnapshots"] == 12
        assert datetime.fromisoformat(str(report["nextAttemptAt"])) == (
            REPLAY_TIME + timedelta(seconds=600)
        )
        app = create_app(settings=settings, clock=clock, readiness_probe=ContractReadinessProbe())
        try:
            state = _get(app, "/api/v1/odds/stake/status")[1]["data"]
            assert state["state"] == "blocked" and state["eventCount"] == 1
            events = _get(app, "/api/v1/odds/stake/events")[1]["data"]
            assert len(events) == 1 and events[0]["freshness"] == "degraded"
            assert len(events[0]["capture"]["markets"]) == 55
        finally:
            app.state.real_admin_engine.dispose()
    finally:
        engine.dispose()


@pytest.mark.integration
def test_publish_all_markets_api_replay_freshness_and_access_failure(
    postgresql_url: str, tmp_path: Path
) -> None:
    config = alembic_config(postgresql_url)
    command.upgrade(config, "head")
    engine = create_engine(postgresql_url)
    settings, clock, scraper = (
        settings_for(postgresql_url, tmp_path),
        ReplayClock(),
        RecordedScraper(),
    )
    first = scrape_stake(engine, settings, clock=clock, scraper=scraper)
    assert (
        first["state"],
        first["events"],
        first["markets"],
        first["outcomes"],
        first["insertedSnapshots"],
    ) == ("operational", 1, 55, 154, 12)
    cooldown = scrape_stake(engine, settings, clock=clock, scraper=scraper)
    assert cooldown["state"] == "cooldown" and scraper.calls == 1
    app = create_app(settings=settings, clock=clock, readiness_probe=ContractReadinessProbe())
    status, payload = _get(app, "/api/v1/odds/stake/events")
    assert status == 200 and payload["meta"]["dataMode"] == "real"
    assert payload["data"][0]["freshness"] == "fresh"
    assert len(payload["data"][0]["capture"]["markets"]) == 55
    assert _get(app, "/api/v1/odds/stake/status")[1]["data"]["state"] == "operational"
    assert _get(app, "/api/v1/odds/stake/events?limit=21")[0] == 422
    assert _get(app, "/api/v1/odds/stake/events?startsFrom=2026-09-12")[0] == 400
    assert _get(app, "/api/v1/odds/stake/events?startsFrom=2026-09-12T00:00:00Z")[1]["data"] == []
    quotes = _get(app, "/api/v1/odds/quotes?provider=stake-public")[1]["data"]
    assert len(quotes) == 12 and all(q["informationalOnly"] for q in quotes)
    assert all(q["providerType"] == "public_scrape" for q in quotes)
    with engine.connect() as connection:
        row = connection.execute(select(StakePageCapture.__table__)).one()
    raw = tmp_path / row.raw_payload_reference
    assert raw.is_file() and b"2.05" in raw.read_bytes()

    clock.value += timedelta(seconds=121)
    replay = scrape_stake(engine, settings, clock=clock, scraper=scraper)
    assert replay["insertedSnapshots"] == 0
    assert _get(app, "/api/v1/odds/stake/events")[1]["data"][0]["freshness"] == "stale"
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(StakePageCapture)) == 1
        assert connection.scalar(select(func.count()).select_from(OddsSnapshotRecord)) == 12

    clock.value += timedelta(seconds=121)
    scraper.blocked = True
    refused = scrape_stake(engine, settings, clock=clock, scraper=scraper)
    assert refused["state"] == "blocked"
    _, status_payload = _get(app, "/api/v1/odds/stake/status")
    assert status_payload["data"]["state"] == "blocked"
    assert status_payload["data"]["lastSuccessAt"] == REPLAY_TIME.isoformat().replace("+00:00", "Z")
    old_count = scraper.calls
    scrape_stake(engine, settings, clock=clock, scraper=scraper)
    assert scraper.calls == old_count
    clock.value += timedelta(seconds=601)
    refused_again = scrape_stake(engine, settings, clock=clock, scraper=scraper)
    assert datetime.fromisoformat(str(refused_again["nextAttemptAt"])) == clock.value + timedelta(
        seconds=1200
    )
    assert _get(app, "/api/v1/odds/stake/events")[1]["page"]["total"] == 1
    for table in ("stake_scrape_runs", "stake_page_captures"):
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(text(f"DELETE FROM odds.{table}"))
    app.state.real_admin_engine.dispose()
    engine.dispose()
    # Une base ayant réellement reçu ce nouveau type reste rétrogradable entièrement.
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.mark.integration
def test_mock_configuration_cannot_start_scraping_or_read_real_market_pages(
    postgresql_url: str, tmp_path: Path
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "mock",
            "odds_provider": "mock",
            "database_url": postgresql_url,
            "object_store_root": tmp_path,
        }
    )
    scraper = RecordedScraper()
    with pytest.raises(ValueError, match="APP_DATA_MODE=real"):
        scrape_stake(engine, settings, scraper=scraper)
    assert scraper.calls == 0
    app = create_app(settings=settings, readiness_probe=ContractReadinessProbe())
    assert _get(app, "/api/v1/odds/stake/events")[1]["data"] == []
    assert _get(app, "/api/v1/odds/stake/status")[1]["data"]["state"] == "disabled"
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(StakeScrapeRun)) == 0
    engine.dispose()


@pytest.mark.integration
def test_backup_restore_preserves_all_scraped_markets_and_their_source(
    postgresql_url: str, tmp_path: Path
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = settings_for(postgresql_url, tmp_path / "source")
    scrape_stake(engine, settings, clock=ReplayClock(), scraper=RecordedScraper())
    tools = postgres_tools(engine)
    backup = BackupService(engine, settings, tools=tools).run()
    target_name = "metiquo_restore_" + uuid4().hex
    target_root = tmp_path / "restored"
    target = create_engine(engine.url.set(database=target_name))
    admin = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        report = RestoreService(engine, settings, tools=tools).run(
            RestoreRequest(
                backup.backup_id,
                backup.index_sha256,
                target_name,
                target_root,
            )
        )
        assert report.objects_verified >= 1
        with target.connect() as connection:
            row = connection.execute(select(StakePageCapture.__table__)).one()
            assert len(row.payload["markets"]) == 55
        assert (target_root / row.raw_payload_reference).read_bytes() == (
            settings.object_store_root / row.raw_payload_reference
        ).read_bytes()
    finally:
        target.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{target_name}" WITH (FORCE)')
        admin.dispose()
        engine.dispose()
