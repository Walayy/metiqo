"""DOM public réellement relevé ; horloge de rejeu explicitement figée pour les tests."""

import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Route, async_playwright

from metiquo.config import Settings
from metiquo.contracts.enums import GameTitle
from metiquo.contracts.stake_scraping import StakeEventCapture
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.providers.stake_browser import StakeBrowserScraper
from metiquo.providers.stake_parser import (
    StakeScrapeError,
    decimal_price,
    parse_event,
    parse_markets,
    public_url,
)
from metiquo.providers.stake_public import winner_provider
from metiquo.worker.scheduler import SchedulePolicy, planned_jobs

FIXTURE = Path(__file__).parents[1] / "fixtures/odds/stake-dom-20260908.json"
REPLAY_TIME = datetime(2026, 9, 8, 16, 45, tzinfo=UTC)


def recorded_doms() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return result


def additional_matches() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = json.loads(
        FIXTURE.with_name("stake-additional-matches-20260908.json").read_text(encoding="utf-8")
    )["records"]
    return result


@pytest.mark.parametrize(
    "record", additional_matches(), ids=lambda r: r["dom"]["url"].rsplit("/", 1)[1]
)
def test_additional_real_match_headers_and_winner_prices(record: dict[str, Any]) -> None:
    dom = record["dom"]
    if record["expectedStartUtc"] is None:
        with pytest.raises(StakeScrapeError) as error:
            parse_event(dom, REPLAY_TIME)
        assert error.value.code == "START_TIME_MISSING"
        return
    event = parse_event(dom, REPLAY_TIME)
    assert event.starts_at.isoformat() == record["expectedStartUtc"]
    assert event.best_of is None
    markets = parse_markets(dom, "tab-main", REPLAY_TIME)
    capture = StakeEventCapture(
        event=event,
        source_url=dom["url"],
        observed_at=REPLAY_TIME,
        expected_tabs=tuple(dom["tabs"]),
        visited_tabs=("tab-main",),
        markets=markets,
        warnings=("TEST_FIXTURE_MAIN_WINNER_ONLY",),
    )
    provider = winner_provider(capture, FixedClock(UtcInstant(REPLAY_TIME)))
    snapshots = provider.capture_snapshot(event.provider_event_id).snapshots
    assert len(snapshots) == 2
    assert sorted(s.decimal_odds for s in snapshots) == sorted(
        Decimal(o["oddsText"].replace(",", ".")) for o in dom["markets"][0]["outcomes"]
    )
    assert set(event.participants) == {o["label"] for o in dom["markets"][0]["outcomes"]}


def test_keyd_short_name_is_anchored_by_exact_opponent_even_if_outcomes_reversed() -> None:
    dom = copy.deepcopy(additional_matches()[1]["dom"])
    dom["markets"][0]["outcomes"].reverse()
    assert parse_event(dom, REPLAY_TIME).participants == (
        "Keyd Stars Academy",
        "KaBuM! Ilha das Lendas",
    )


def test_two_unrelated_market_names_are_rejected_instead_of_fuzzy_matching() -> None:
    dom = copy.deepcopy(additional_matches()[1]["dom"])
    dom["participants"] = ["Different Academy", "Different Opponent"]
    with pytest.raises(StakeScrapeError) as error:
        parse_event(dom, REPLAY_TIME)
    assert error.value.code == "EVENT_IDENTITY_CONFLICT"


@pytest.mark.parametrize("same_timestamp", [False, True])
def test_latest_missing_prices_never_fall_back_to_earlier_open_tab(same_timestamp: bool) -> None:
    capture = recorded_capture()
    at = REPLAY_TIME if same_timestamp else REPLAY_TIME + timedelta(seconds=1)
    markets = tuple(
        market.model_copy(
            update={
                "captured_at": at,
                "outcomes": tuple(
                    o.model_copy(
                        update={"decimal_odds": None, "odds_text": "", "status": "suspended"}
                    )
                    for o in market.outcomes
                ),
            }
        )
        if market.tab == "tab-map-1" and market.label == "Map 1 Gagnant - Two options"
        else market
        for market in capture.markets
    )
    updated = capture.model_copy(update={"markets": markets, "observed_at": at})
    provider = winner_provider(updated, FixedClock(UtcInstant(at)))
    assert provider.observation_count == 10


def recorded_capture() -> StakeEventCapture:
    states = recorded_doms()
    return StakeEventCapture(
        event=parse_event(states[0]["dom"], REPLAY_TIME),
        source_url=states[0]["dom"]["url"],
        observed_at=REPLAY_TIME,
        expected_tabs=tuple(s["tab"] for s in states),
        visited_tabs=tuple(s["tab"] for s in states),
        markets=tuple(m for s in states for m in parse_markets(s["dom"], s["tab"], REPLAY_TIME)),
        warnings=(),
    )


def test_all_recorded_tabs_preserve_prices_labels_and_unknown_format() -> None:
    capture = recorded_capture()
    assert capture.event.starts_at == datetime(2026, 9, 11, 15, tzinfo=UTC)
    assert capture.event.best_of is None
    assert len(capture.markets) == 55
    assert sum(len(m.outcomes) for m in capture.markets) == 154
    score = next(m for m in capture.markets if m.label == "Résultat final")
    assert [(o.label, o.decimal_odds) for o in score.outcomes][:2] == [
        ("0:3", Decimal("5.30")),
        ("1:3", Decimal("4.00")),
    ]
    provider = winner_provider(capture, FixedClock(UtcInstant(REPLAY_TIME)))
    assert provider.observation_count == 12
    assert (
        len(
            provider.list_events(
                REPLAY_TIME, datetime(2026, 10, 1, tzinfo=UTC), GameTitle.LEAGUE_OF_LEGENDS
            )
        )
        == 1
    )
    snapshots = provider.capture_snapshot("822193").snapshots
    assert all(s.informational_only for s in snapshots)
    assert {s.decimal_odds for s in snapshots} == {
        Decimal("2.05"),
        Decimal("1.78"),
        Decimal("1.95"),
        Decimal("1.82"),
    }


@pytest.mark.parametrize("value", ["NaN", "inf", "-2", "0", "1", "2/1", "+150", "1,5.2"])
def test_invalid_or_non_decimal_odds_are_never_invented(value: str) -> None:
    with pytest.raises(StakeScrapeError):
        decimal_price(value)


def test_missing_price_remains_null_and_suspended_is_not_open() -> None:
    dom = copy.deepcopy(recorded_doms()[0]["dom"])
    dom["markets"][0]["outcomes"] = [
        {
            "label": "suspended",
            "displayedLabel": "",
            "oddsText": "",
            "disabled": True,
            "text": "Suspendu",
        }
    ]
    outcome = parse_markets(dom, "tab-main", REPLAY_TIME)[0].outcomes[0]
    assert outcome.decimal_odds is None and outcome.status == "suspended"


@pytest.mark.parametrize(
    "date", ["17:00", "02:30 25/10/2026", "02:30 29/03/2026", "15:00 01/09/2026"]
)
def test_ambiguous_missing_and_past_dates_are_refused(date: str) -> None:
    dom = {**recorded_doms()[0]["dom"], "displayedStart": date}
    with pytest.raises(StakeScrapeError):
        parse_event(dom, REPLAY_TIME)


@pytest.mark.parametrize(
    "url",
    [
        "https://stake.bet.evil.test/fr/sports/league-of-legends/all",
        "http://stake.bet/fr/sports/league-of-legends/all",
        "https://stake.bet/api/graphql",
        "https://user@stake.bet/fr/sports/league-of-legends/all",
        "https://stake.bet/fr/sports/league-of-legends/all?token=x",
        "http://127.0.0.1/",
    ],
)
def test_urls_cannot_leave_the_public_pages(url: str) -> None:
    with pytest.raises(ValueError):
        public_url(url)


def test_scraping_schedules_only_in_real_mode_without_api_credentials() -> None:
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "real",
            "odds_provider": "stake_public",
            "database_url": "postgresql+psycopg://test@localhost/test",
        }
    )
    jobs = planned_jobs(SchedulePolicy.from_settings(settings), REPLAY_TIME, {})
    assert sum(job.job_type == "odds.stake_scrape" for job in jobs) == 1
    with pytest.raises(ValueError, match="provider de cotes réel"):
        Settings.model_validate(
            {
                "app_env": "test",
                "app_data_mode": "mock",
                "odds_provider": "stake_public",
                "database_url": "postgresql+psycopg://test@localhost/test",
            }
        )


def replay_html(doms: list[dict[str, Any]] | None = None) -> str:
    """Reproduction minimale de la structure observée, jamais présentée comme une page live."""
    states = json.dumps(doms or recorded_doms(), ensure_ascii=False).replace("</", "<\\/")
    return (
        FIXTURE.with_name("stake-page-replay.html")
        .read_text(encoding="utf-8")
        .replace("__RECORDED_STATES__", states)
    )


@pytest.mark.integration
def test_browser_replays_hydration_tabs_more_and_exact_scores_without_selecting_odds() -> None:
    async def run() -> None:
        async with async_playwright() as runtime:
            browser = await runtime.chromium.launch(channel="chromium")
            context = await browser.new_context(locale="fr-FR", timezone_id="Europe/Paris")
            clicked: list[bool] = []
            await context.expose_function("noteSelection", lambda: clicked.append(True))

            async def replay(route: Route) -> None:
                await route.fulfill(status=200, content_type="text/html", body=replay_html())

            await context.route("**/*", replay)
            scraper = StakeBrowserScraper(clock=FixedClock(UtcInstant(REPLAY_TIME)))
            scraper._navigation_lock = asyncio.Lock()
            try:
                capture = await scraper._event(context, recorded_doms()[0]["dom"]["url"])
                assert len(capture.markets) == 55
                assert sum(len(m.outcomes) for m in capture.markets) == 154
                assert capture.event.starts_at.hour == 15
                assert capture.visited_tabs == capture.expected_tabs
                assert not clicked
            finally:
                await browser.close()

    asyncio.run(run())


@pytest.mark.integration
def test_browser_stops_at_access_refusal() -> None:
    async def run() -> None:
        async with async_playwright() as runtime:
            browser = await runtime.chromium.launch(channel="chromium")
            context = await browser.new_context()
            requests: list[str] = []

            async def refused(route: Route) -> None:
                requests.append(route.request.url)
                await route.fulfill(status=403, body="<title>Just a moment...</title>")

            await context.route("**/*", refused)
            scraper = StakeBrowserScraper()
            scraper._navigation_lock = asyncio.Lock()
            try:
                with pytest.raises(StakeScrapeError) as error:
                    await scraper._event(context, recorded_doms()[0]["dom"]["url"])
                assert error.value.blocked and error.value.code == "HTTP_403"
                assert len(requests) == 1
            finally:
                await browser.close()

    asyncio.run(run())


@pytest.mark.integration
def test_browser_discovers_competitions_then_unique_event_links() -> None:
    from metiquo.providers.stake_parser import STAKE_LIST_URL

    async def run() -> None:
        event = recorded_doms()[0]["dom"]["url"]
        competition = event.rsplit("/", 1)[0]
        async with async_playwright() as runtime:
            browser = await runtime.chromium.launch(channel="chromium")
            context = await browser.new_context()
            requested: list[str] = []

            async def replay(route: Route) -> None:
                requested.append(route.request.url)
                link = competition if route.request.url == STAKE_LIST_URL else event
                relative = link.removeprefix("https://stake.bet")
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=(
                        '<div id="main-content">'
                        f'<a href="{relative}">premier lien</a><a href="{relative}">doublon</a>'
                        '<a href="https://example.org/">extérieur</a></div>'
                    ),
                )

            await context.route("**/*", replay)
            scraper = StakeBrowserScraper()
            scraper._navigation_lock = asyncio.Lock()
            try:
                assert await scraper._discover(context) == (event,)
                assert requested == [STAKE_LIST_URL, competition]
            finally:
                await browser.close()

    asyncio.run(run())
