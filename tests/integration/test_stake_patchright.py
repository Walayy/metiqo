"""Mode réel → handler du worker → Patchright → PostgreSQL → lecture HTTP."""

from pathlib import Path
from typing import Any

import pytest
from alembic import command
from patchright.async_api import BrowserContext, BrowserType, Route
from sqlalchemy import create_engine

from metiquo.api.app import create_app
from metiquo.api.openapi import ContractReadinessProbe
from metiquo.config import Settings
from metiquo.foundation.identifiers import CorrelationId, JobId, TraceId
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.providers.stake_parser import STAKE_LIST_URL
from metiquo.worker.contracts import CancellationToken, JobContext
from metiquo.worker.handlers import default_handlers
from tests.integration.test_migrations import alembic_config
from tests.integration.test_observed_odds import _get
from tests.providers.test_stake_scraping import REPLAY_TIME, recorded_doms, replay_html


@pytest.mark.integration
def test_auto_real_worker_publishes_patchright_capture(
    postgresql_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = recorded_doms()[0]["dom"]["url"]
    competition = event.rsplit("/", 1)[0]
    original = BrowserType.launch_persistent_context

    async def handler(route: Route) -> None:
        if route.request.url == event:
            body = replay_html()
        else:
            target = competition if route.request.url == STAKE_LIST_URL else event
            body = f'<div id="main-content"><a href="{target.removeprefix("https://stake.bet")}">LoL</a></div>'
        await route.fulfill(status=200, content_type="text/html", body=body)

    async def launch(browser_type: BrowserType, *args: Any, **kwargs: Any) -> BrowserContext:
        assert kwargs["headless"] is False
        context = await original(browser_type, *args, **kwargs)
        await context.route("**/*", handler)
        return context

    monkeypatch.setattr(BrowserType, "launch_persistent_context", launch)
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "real",
            "odds_provider": "auto",
            "database_url": postgresql_url,
            "object_store_root": tmp_path,
            "stake_scrape_navigation_interval_seconds": 1,
        }
    )
    clock = FixedClock(UtcInstant(REPLAY_TIME))
    app = create_app(settings=settings, clock=clock, readiness_probe=ContractReadinessProbe())
    try:
        context = JobContext(
            job_id=JobId.new(),
            trace_id=TraceId.new(),
            correlation_id=CorrelationId.new(),
            started_at=clock.now(),
            clock=clock,
            cancellation=CancellationToken(),
        )
        report = default_handlers(engine, settings)["odds.stake_scrape"].handle(context)
        assert report is not None and report["state"] == "operational"
        assert report["insertedSnapshots"] == 12
        status, data = _get(app, "/api/v1/odds/stake/events")
        assert status == 200 and data["meta"]["dataMode"] == "real"
        assert data["data"][0]["freshness"] == "fresh"
        assert len(data["data"][0]["capture"]["markets"]) == 55
    finally:
        app.state.real_admin_engine.dispose()
        engine.dispose()
