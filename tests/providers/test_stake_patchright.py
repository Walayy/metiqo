"""Tests du moteur Patchright réel ; pages de test et réponses contrôlées."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from patchright.async_api import BrowserContext, BrowserType, Route

from metiquo.config import OddsProvider
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.providers.stake_browser import ScrapeLimits, StakeBrowserScraper
from metiquo.providers.stake_discovery import read_discovery, write_discovery
from metiquo.providers.stake_parser import STAKE_LIST_URL
from metiquo.worker.scheduler import SchedulePolicy
from tests.providers.test_stake_scraping import REPLAY_TIME, recorded_doms, replay_html
from tests.test_config import build_settings

EVENT = recorded_doms()[0]["dom"]["url"]


@pytest.mark.parametrize("fault", ["expired", "future", "external-url", "truncated"])
def test_invalid_discovery_cache_cannot_select_untrusted_or_stale_urls(
    tmp_path: Path, fault: str
) -> None:
    path = tmp_path / "discovery.json"
    clock = FixedClock(UtcInstant(REPLAY_TIME))
    write_discovery(path, clock, (EVENT,))
    assert read_discovery(path, clock) == (EVENT,)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if fault in {"expired", "future"}:
        delta = -300 if fault == "expired" else 1
        payload["observed_at"] = (REPLAY_TIME + timedelta(seconds=delta)).isoformat()
    elif fault == "external-url":
        payload["urls"] = ["https://example.org/private"]
    path.write_text("{" if fault == "truncated" else json.dumps(payload), encoding="utf-8")
    assert read_discovery(path, clock) == ()


@pytest.mark.parametrize("mode", ["mock", "real"])
def test_auto_provider_only_schedules_scraping_in_real_mode(mode: str) -> None:
    settings = build_settings(app_data_mode=mode, odds_provider="auto")
    assert settings.odds_provider is (
        OddsProvider.MOCK if mode == "mock" else OddsProvider.STAKE_PUBLIC
    )
    assert SchedulePolicy.from_settings(settings).stake_enabled is (mode == "real")
    assert settings.stake_browser_engine == "patchright" and not settings.stake_browser_headless


@pytest.mark.integration
@pytest.mark.parametrize(
    "case", ["complete", "challenge-clears", "challenge-stays", "hard-refusal"]
)
def test_patchright_collects_or_reports_real_browser_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    original = BrowserType.launch_persistent_context
    contexts: list[BrowserContext] = []
    requests: list[str] = []

    async def handler(route: Route) -> None:
        url = route.request.url
        requests.append(url)
        if "challenge" in case and requests.count(url) == 1:
            script = (
                "<script>setTimeout(()=>location.reload(),100)</script>"
                if case.endswith("clears")
                else ""
            )
            await route.fulfill(
                status=403,
                headers={"cf-mitigated": "challenge"},
                content_type="text/html",
                body="<title>Un instant…</title>" + script,
            )
        elif case == "hard-refusal":
            await route.fulfill(status=403, body="Forbidden")
        else:
            await route.fulfill(status=200, content_type="text/html", body=replay_html())

    async def launch(browser_type: BrowserType, *args: Any, **kwargs: Any) -> BrowserContext:
        context = await original(browser_type, *args, **kwargs)
        contexts.append(context)
        await context.route("**/*", handler)
        return context

    monkeypatch.setattr(BrowserType, "launch_persistent_context", launch)
    scraper = StakeBrowserScraper(
        ScrapeLimits(challenge_timeout_seconds=2),
        engine="patchright",
        headless=True,
        profile_dir=tmp_path / "profile",
        clock=FixedClock(UtcInstant(REPLAY_TIME)),
    )
    result = asyncio.run(scraper.collect([EVENT]))
    if case in {"complete", "challenge-clears"}:
        assert not result.blocked and not result.failures
        assert len(result.captures) == 1 and len(result.captures[0].markets) == 55
        assert sum(len(m.outcomes) for m in result.captures[0].markets) == 154
    else:
        assert result.blocked and not result.captures
        expected = "HTTP_403" if case == "hard-refusal" else "ACCESS_CHALLENGE"
        assert result.failures == (EVENT.rsplit("/", 1)[1] + ":" + expected,)
        assert requests == [EVENT]
    assert contexts[0].browser is not None and not contexts[0].browser.is_connected()


@pytest.mark.integration
def test_cached_discovery_still_reads_changed_prices_from_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = BrowserType.launch_persistent_context
    requests: list[str] = []
    competition = EVENT.rsplit("/", 1)[0]

    async def handler(route: Route) -> None:
        url = route.request.url
        requests.append(url)
        if url == EVENT:
            states = recorded_doms()
            states[0]["dom"]["markets"][0]["outcomes"][0]["oddsText"] = (
                "2,05" if requests.count(EVENT) == 1 else "2,10"
            )
            body = replay_html(states)
        else:
            target = competition if url == STAKE_LIST_URL else EVENT
            body = f'<div id="main-content"><a href="{target.removeprefix("https://stake.bet")}">LoL</a></div>'
        await route.fulfill(status=200, content_type="text/html", body=body)

    async def launch(browser_type: BrowserType, *args: Any, **kwargs: Any) -> BrowserContext:
        context = await original(browser_type, *args, **kwargs)
        await context.route("**/*", handler)
        return context

    monkeypatch.setattr(BrowserType, "launch_persistent_context", launch)
    scraper = StakeBrowserScraper(
        engine="patchright",
        headless=True,
        profile_dir=tmp_path / "profile",
        discovery_cache=tmp_path / "discovery.json",
        clock=FixedClock(UtcInstant(REPLAY_TIME)),
    )
    first = asyncio.run(scraper.collect())
    second = asyncio.run(scraper.collect())
    assert not first.failures and not second.failures
    assert first.captures[0].markets[0].outcomes[0].odds_text == "2,05"
    assert second.captures[0].markets[0].outcomes[0].odds_text == "2,10"
    assert requests.count(STAKE_LIST_URL) == requests.count(competition) == 1
    assert requests.count(EVENT) == 2
