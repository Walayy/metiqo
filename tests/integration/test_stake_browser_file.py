"""L'import configuré du fichier publie les observations sans démarrer de navigateur."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine

from metiquo.api.app import create_app
from metiquo.api.openapi import ContractReadinessProbe
from metiquo.providers.stake_browser import StakeBrowserScraper
from metiquo.services.stake_scraping import scrape_stake
from tests.integration.test_migrations import alembic_config
from tests.integration.test_observed_odds import _get
from tests.integration.test_stake_scraping import RecordedScraper, ReplayClock, settings_for
from tests.providers.test_stake_browser_file import browser_export


@pytest.mark.integration
def test_browser_file_to_database_and_http_with_no_playwright_or_network(
    postgresql_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Le mode fichier ne doit jamais créer de navigateur")

    monkeypatch.setattr(StakeBrowserScraper, "__init__", forbidden)
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    path = tmp_path / "browser.json"
    path.write_text(json.dumps(browser_export()), encoding="utf-8")
    settings = settings_for(postgresql_url, tmp_path / "objects").model_copy(
        update={"stake_browser_capture_file": path}
    )
    clock = ReplayClock()
    app = create_app(settings=settings, clock=clock, readiness_probe=ContractReadinessProbe())
    try:
        result = scrape_stake(engine, settings, clock=clock)
        assert result["state"] == "operational" and result["insertedSnapshots"] == 12
        data = _get(app, "/api/v1/odds/stake/events")[1]["data"]
        assert len(data[0]["capture"]["markets"]) == 55 and data[0]["freshness"] == "fresh"
        clock.value += timedelta(minutes=3)
        replay = scrape_stake(engine, settings, clock=clock)
        assert replay["state"] == "partial" and replay["insertedSnapshots"] == 0
        assert replay["detail"] == "BROWSER_EXPORT_STALE"
        assert _get(app, "/api/v1/odds/stake/events")[1]["data"][0]["freshness"] == "stale"
    finally:
        app.state.real_admin_engine.dispose()
        engine.dispose()


@pytest.mark.integration
def test_file_mode_recovers_without_waiting_for_old_network_backoff(
    postgresql_url: str, tmp_path: Path
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings, clock = settings_for(postgresql_url, tmp_path / "objects"), ReplayClock()
    refused = RecordedScraper()
    refused.blocked = True
    path = tmp_path / "browser.json"
    path.write_text(json.dumps(browser_export()), encoding="utf-8")
    file_settings = settings.model_copy(update={"stake_browser_capture_file": path})
    try:
        assert scrape_stake(engine, settings, clock=clock, scraper=refused)["state"] == "blocked"
        immediate = scrape_stake(engine, file_settings, clock=clock)
        assert immediate["state"] == "cooldown"
        assert immediate["nextAttemptAt"] == (clock.value + timedelta(seconds=60)).isoformat()
        clock.value += timedelta(seconds=61)
        assert scrape_stake(engine, file_settings, clock=clock)["state"] == "operational"
    finally:
        engine.dispose()
