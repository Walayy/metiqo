"""Scénarios adverses synthétiques, exécutés dans le vrai Chromium complet."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from playwright.async_api import Browser, BrowserContext, Route, async_playwright

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.providers.stake_browser import ScrapeLimits, StakeBrowserScraper
from metiquo.providers.stake_parser import STAKE_LIST_URL
from metiquo.providers.stake_public import winner_provider
from tests.providers.test_stake_scraping import FIXTURE, REPLAY_TIME, recorded_doms, replay_html

EVENT = recorded_doms()[0]["dom"]["url"]
COMPETITION = EVENT.rsplit("/", 1)[0]


def install_replay(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[Route], Awaitable[None]]
) -> list[BrowserContext]:
    """Intercepter uniquement le réseau de test, sans remplacer le navigateur ni collect()."""
    original = Browser.new_context
    contexts: list[BrowserContext] = []

    async def create(browser: Browser, **kwargs: Any) -> BrowserContext:
        context = await original(browser, **kwargs)
        contexts.append(context)
        await context.route("**/*", handler)
        return context

    monkeypatch.setattr(Browser, "new_context", create)
    return contexts


@pytest.mark.integration
@pytest.mark.parametrize("failure", [403, 429, 451, 401])
def test_collect_preserves_completed_events_and_stops_after_refusal(
    monkeypatch: pytest.MonkeyPatch, failure: int
) -> None:
    requested: list[str] = []
    bad, skipped = COMPETITION + "/2-test-refused", COMPETITION + "/3-test-skipped"

    async def handler(route: Route) -> None:
        requested.append(route.request.url)
        await route.fulfill(
            status=failure if route.request.url == bad else 200,
            content_type="text/html",
            body="Refused" if route.request.url == bad else replay_html(),
        )

    contexts = install_replay(monkeypatch, handler)
    scraper = StakeBrowserScraper(
        ScrapeLimits(concurrency=1), clock=FixedClock(UtcInstant(REPLAY_TIME))
    )
    result = asyncio.run(scraper.collect([EVENT, bad, skipped, EVENT]))
    assert result.blocked and result.discovered_events == 3
    assert len(result.captures) == 1 and len(result.captures[0].markets) == 55
    assert result.failures == (f"2-test-refused:HTTP_{failure}", "3-test-skipped:NOT_ATTEMPTED")
    assert requested == [EVENT, bad]
    assert contexts[0].browser is not None and not contexts[0].browser.is_connected()


@pytest.mark.integration
@pytest.mark.parametrize("failure", [500, "timeout", "network"])
def test_one_broken_page_does_not_discard_other_matches(
    monkeypatch: pytest.MonkeyPatch, failure: int | str
) -> None:
    bad = COMPETITION + "/2-test-failure"

    async def handler(route: Route) -> None:
        if route.request.url == bad:
            if failure == "network":
                await route.abort("failed")
            else:
                await route.fulfill(status=500 if failure == 500 else 200, body="No event DOM")
        else:
            await route.fulfill(status=200, content_type="text/html", body=replay_html())

    install_replay(monkeypatch, handler)
    scraper = StakeBrowserScraper(
        ScrapeLimits(page_timeout_seconds=5), clock=FixedClock(UtcInstant(REPLAY_TIME))
    )
    result = asyncio.run(scraper.collect([bad, EVENT]))
    assert not result.blocked and len(result.captures) == 1
    code = {500: "HTTP_500", "timeout": "PAGE_TIMEOUT", "network": "PAGE_UNAVAILABLE"}[failure]
    assert result.failures == (f"2-test-failure:{code}",)


@pytest.mark.integration
def test_discovery_continues_after_unavailable_competition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = COMPETITION.rsplit("/", 1)[0] + "/synthetic-failing-competition"
    requested: list[str] = []

    def links(*urls: str) -> str:
        return (
            '<div id="main-content">'
            + "".join(f'<a href="{url.removeprefix("https://stake.bet")}">lien</a>' for url in urls)
            + "</div>"
        )

    async def handler(route: Route) -> None:
        url = route.request.url
        requested.append(url)
        body = (
            links(bad, COMPETITION)
            if url == STAKE_LIST_URL
            else links(EVENT)
            if url == COMPETITION
            else replay_html()
        )
        await route.fulfill(status=503 if url == bad else 200, content_type="text/html", body=body)

    install_replay(monkeypatch, handler)
    result = asyncio.run(StakeBrowserScraper(clock=FixedClock(UtcInstant(REPLAY_TIME))).collect())
    assert len(result.captures) == 1
    assert result.failures == ("synthetic-failing-competition:HTTP_503",)
    assert requested == [STAKE_LIST_URL, bad, COMPETITION, EVENT]


@pytest.mark.integration
@pytest.mark.parametrize("other_markets", [0, 300])
def test_expand_reveals_late_score_control_and_accepts_exact_action_limit(
    other_markets: int,
) -> None:
    async def run() -> None:
        async with async_playwright() as runtime:
            browser = await runtime.chromium.launch(channel="chromium")
            try:
                page = await browser.new_page()
                await page.set_content("""
                  <div id="main-content"><div class="secondary-accordion level-2">
                    <div class="header" onclick="this.parentNode.classList.add('is-open');
                      this.querySelector('button').style.display='inline'">
                      <span data-ds-text>Résultat final</span>
                      <button style="display:none" onclick="event.stopPropagation();
                        document.querySelector('#scores').textContent='0:3 5,30 3:0 6,30'"
                      >Tout</button>
                    </div><div id="scores">Suspendu</div>
                  </div></div>
                """)
                await page.evaluate(
                    """count => document.querySelector('#main-content').insertAdjacentHTML(
                      'afterbegin', Array.from({length: count}, (_, i) =>
                        '<div class="secondary-accordion level-2 is-open"><div class="header">' +
                        '<span data-ds-text>Total ' + i + '</span></div></div>').join(''))""",
                    other_markets,
                )
                scraper = StakeBrowserScraper(ScrapeLimits(max_expansions=2))
                assert await asyncio.wait_for(scraper._expand(page), timeout=8) == ()
                assert await page.locator("#scores").text_content() == "0:3 5,30 3:0 6,30"
            finally:
                await browser.close()

    asyncio.run(run())


@pytest.mark.integration
@pytest.mark.parametrize("map_number", [1, 10])
def test_french_team_total_labels_must_belong_to_the_requested_map(
    monkeypatch: pytest.MonkeyPatch, map_number: int
) -> None:
    states = recorded_doms()
    label = f"Nombre total d'éliminations 18.5 de Nongshim, sur la carte {map_number}"
    states[1]["dom"]["markets"][1]["label"] = label

    async def handler(route: Route) -> None:
        await route.fulfill(content_type="text/html", body=replay_html(states))

    install_replay(monkeypatch, handler)
    result = asyncio.run(
        StakeBrowserScraper(
            ScrapeLimits(page_timeout_seconds=5), clock=FixedClock(UtcInstant(REPLAY_TIME))
        ).collect([EVENT])
    )
    if map_number == 1:
        assert not result.failures and len(result.captures) == 1
        assert any(m.label == label for m in result.captures[0].markets)
        assert result.captures[0].visited_tabs == result.captures[0].expected_tabs
    else:
        assert not result.captures and result.failures[0].endswith(":PAGE_TIMEOUT")


@pytest.mark.integration
def test_collect_loads_visual_resources_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []
    image = "https://stake.bet/synthetic-test-image.png"

    async def handler(route: Route) -> None:
        requested.append(route.request.url)
        if route.request.url == image:
            await route.fulfill(status=200, content_type="image/png", body=b"")
        else:
            await route.fulfill(
                status=200,
                content_type="text/html",
                body=replay_html().replace("<body>", f'<body><img src="{image}">'),
            )

    install_replay(monkeypatch, handler)
    result = asyncio.run(
        StakeBrowserScraper(clock=FixedClock(UtcInstant(REPLAY_TIME))).collect([EVENT])
    )
    assert len(result.captures) == 1 and not result.failures
    assert image in requested


@pytest.mark.integration
def test_global_timeout_closes_browser_without_losing_finished_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = COMPETITION + "/2-test-never-ready"

    async def handler(route: Route) -> None:
        await route.fulfill(
            status=200,
            content_type="text/html",
            body="<title>Waiting</title>" if route.request.url == bad else replay_html(),
        )

    contexts = install_replay(monkeypatch, handler)
    scraper = StakeBrowserScraper(
        ScrapeLimits(timeout_seconds=10, concurrency=1),
        clock=FixedClock(UtcInstant(REPLAY_TIME)),
    )
    result = asyncio.run(scraper.collect([EVENT, bad]))
    assert len(result.captures) == 1 and result.discovered_events == 2
    assert result.failures == ("RUN_TIMEOUT",)
    assert contexts[0].browser is not None and not contexts[0].browser.is_connected()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("fixture", "markets", "outcomes", "snapshots"),
    [("stake-9z-dom-20260908.json", 11, 22, 12), ("stake-keyd-excerpt-20260908.json", 2, 4, 4)],
)
def test_other_real_page_structures_and_alias_survive_tab_navigation(
    monkeypatch: pytest.MonkeyPatch, fixture: str, markets: int, outcomes: int, snapshots: int
) -> None:
    # 9z : six onglets complets. Keyd : extrait principal/carte 1 clairement limité.
    states = json.loads(FIXTURE.with_name(fixture).read_text(encoding="utf-8"))

    async def handler(route: Route) -> None:
        await route.fulfill(status=200, content_type="text/html", body=replay_html(states))

    install_replay(monkeypatch, handler)
    clock = FixedClock(UtcInstant(REPLAY_TIME))
    result = asyncio.run(StakeBrowserScraper(clock=clock).collect([states[0]["dom"]["url"]]))
    assert not result.failures and len(result.captures) == 1
    capture = result.captures[0]
    assert len(capture.markets) == markets
    assert sum(len(m.outcomes) for m in capture.markets) == outcomes
    assert winner_provider(capture, clock).observation_count == snapshots
    if "keyd" in fixture:
        assert capture.event.participants == ("Keyd Stars Academy", "KaBuM! Ilha das Lendas")
