"""Rendered-page scraper for SofaScore LoL schedules and live event pages.

This module deliberately has no SofaScore API client and no endpoint construction.
It navigates public pages with the already approved Patchright browser and reads the
rendered HTML/DOM, including the public SSR event object when present.
"""

from __future__ import annotations

import atexit
import json
import re
import time as clock
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from random import SystemRandom
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from metiquo_core.config import Settings
from patchright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

SOURCE = "sofascore"
ROOT_URL = "https://www.sofascore.com/fr/esports/lol"
PARIS = ZoneInfo("Europe/Paris")
MATCH_HREF = re.compile(r"/esports/match/[^?#]+(?:#id:(\d+))?")
RANDOM = SystemRandom()


class SofaScoreBlocked(RuntimeError):
    """The public page asked the collector to stop for a cooldown period."""

    def __init__(self, message: str, *, status: int | None = None, reason: str = "unknown"):
        super().__init__(message)
        self.status = status
        self.reason = reason


@dataclass
class _ScrapeState:
    last_navigation_at: float = 0.0
    blocked_until: float = 0.0
    listing_days: tuple[date, ...] | None = None
    listing_cursor: int = 0
    listing_complete_at: float = 0.0
    links: dict[str, SofaLink] | None = None
    events: dict[str, SofaEvent] | None = None
    event_fetched_at: dict[str, float] | None = None


_STATE = _ScrapeState()


@dataclass
class _BrowserState:
    playwright: Playwright | None = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None
    headless: bool | None = None


_BROWSER = _BrowserState()


@dataclass(frozen=True)
class SofaLink:
    url: str
    source_id: str
    day: date
    label: str


@dataclass(frozen=True)
class SofaEvent:
    source_id: str
    url: str
    home_name: str
    away_name: str
    competition: str
    competition_source_id: str
    competition_slug: str
    home_source_id: str
    away_source_id: str
    home_image: str
    away_image: str
    competition_image: str
    starts_at: datetime
    status: str
    best_of: int
    home_score: int | None
    away_score: int | None
    payload: dict[str, object]


def _json_script(html: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or not script.string:
        return {}
    try:
        value = json.loads(script.string)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _event_from_next(html: str) -> dict[str, object]:
    data = _json_script(html)
    props = data.get("props")
    page_props = props.get("pageProps") if isinstance(props, dict) else None
    event = page_props.get("event") if isinstance(page_props, dict) else None
    return event if isinstance(event, dict) else {}


def _day_url(day: date) -> str:
    return f"{ROOT_URL}/{day.isoformat()}"


def _bounded_delay(settings: Settings) -> float:
    low = min(settings.sofascore_min_delay_seconds, settings.sofascore_max_delay_seconds)
    high = max(settings.sofascore_min_delay_seconds, settings.sofascore_max_delay_seconds)
    return RANDOM.uniform(low, high)


def _blocked_page_reason(page: Page) -> str | None:
    try:
        body = page.content()[:10_000]
    except Exception:
        return None
    if re.search(r'"(?:code|status)"\s*:\s*403|\bForbidden\b|Access denied', body, re.I):
        return "forbidden-body"
    if re.search(r"Just a moment|Checking your browser|cf-chl-|challenge-platform", body, re.I):
        return "browser-challenge"
    return None


def _cooldown(settings: Settings) -> None:
    _STATE.blocked_until = clock.monotonic() + settings.sofascore_block_cooldown_seconds


def _navigate(page: Page, url: str, settings: Settings) -> None:
    now = clock.monotonic()
    if _STATE.blocked_until > now:
        raise SofaScoreBlocked("SofaScore cooldown active", reason="cooldown")
    wait = _STATE.last_navigation_at + _bounded_delay(settings) - now
    if wait > 0:
        clock.sleep(wait)
    response = page.goto(url, wait_until="domcontentloaded")
    _STATE.last_navigation_at = clock.monotonic()
    status = getattr(response, "status", None)
    reason = f"http-{status}" if status in {403, 429} else _blocked_page_reason(page)
    if reason is not None:
        _cooldown(settings)
        raise SofaScoreBlocked(
            f"SofaScore blocked ({reason}, http_status={status or 'unknown'})",
            status=status if isinstance(status, int) else None,
            reason=reason,
        )


def _cached_events() -> list[SofaEvent]:
    return list((_STATE.events or {}).values())


def _should_refresh_event(link: SofaLink, now: float, settings: Settings) -> bool:
    events = _STATE.events or {}
    fetched_at = (_STATE.event_fetched_at or {}).get(link.source_id, 0.0)
    event = events.get(link.source_id)
    if event is None:
        return True
    if event.status == "live":
        return now - fetched_at >= settings.sofascore_live_refresh_seconds
    if event.status == "scheduled":
        seconds_to_start = (event.starts_at - datetime.now(PARIS)).total_seconds()
        return seconds_to_start <= 30 * 60 and (
            now - fetched_at >= settings.sofascore_scheduled_refresh_seconds
        )
    # Completed events are immutable for SofaScore purposes. Oracle’s Elixir
    # supplies their historical cards, so revisiting them every minute only
    # increases load and can never improve the live view.
    return False


def _timestamp(value: object, fallback_day: date) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC).astimezone(PARIS)
    return datetime.combine(fallback_day, time(0), PARIS)


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def _status(event: dict[str, object]) -> str:
    status = event.get("status")
    kind = status.get("type") if isinstance(status, dict) else None
    if kind in {"inprogress", "in_progress", "live"}:
        return "live"
    if kind in {"finished", "ended"}:
        return "finished"
    return "scheduled"


def _links(html: str, day: date, page_url: str) -> list[SofaLink]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, SofaLink] = {}
    for anchor in soup.select('a[href*="/esports/match/"]'):
        href = str(anchor.get("href", ""))
        match = MATCH_HREF.search(href)
        if match is None:
            continue
        source_id = match.group(1)
        if source_id is None:
            fragment = href.split("#id:", 1)[-1] if "#id:" in href else ""
            source_id = fragment.split(",", 1)[0]
        if not source_id.isdigit():
            continue
        absolute = href if href.startswith("http") else f"https://www.sofascore.com{href}"
        label_value = anchor.get("aria-label")
        label = label_value if isinstance(label_value, str) else anchor.get_text(" ", strip=True)
        result[source_id] = SofaLink(absolute, source_id, day, label)
    return list(result.values())


def _visible_signals(page: Page) -> dict[str, object]:
    """Keep only useful rendered signals; advertising and the whole page are not stored."""
    try:
        text = page.locator("body").inner_text(timeout=10_000)
    except Exception:
        return {}
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    keywords = re.compile(
        r"\b(ban|bans|kills?|cs|champions?|players?|objectives?|barons?|dragons?)\b", re.I
    )
    signals = [line[:240] for line in lines if keywords.search(line)]
    return {"signals": signals[:80]} if signals else {}


def _event_from_page(page: Page, link: SofaLink) -> SofaEvent | None:
    html = page.content()
    raw = _event_from_next(html)
    if not raw:
        return None
    home = raw.get("homeTeam")
    away = raw.get("awayTeam")
    tournament = raw.get("tournament")
    home_name = home.get("name") if isinstance(home, dict) else None
    away_name = away.get("name") if isinstance(away, dict) else None
    competition = tournament.get("name") if isinstance(tournament, dict) else None
    if not all(isinstance(value, str) and value for value in (home_name, away_name, competition)):
        return None
    assert isinstance(home_name, str)
    assert isinstance(away_name, str)
    assert isinstance(competition, str)
    tournament_data = tournament if isinstance(tournament, dict) else {}
    competition_id = tournament_data.get("id")
    competition_slug = tournament_data.get("slug")
    home_id = home.get("id") if isinstance(home, dict) else None
    away_id = away.get("id") if isinstance(away, dict) else None
    home_image = home.get("image") if isinstance(home, dict) else None
    away_image = away.get("image") if isinstance(away, dict) else None
    competition_image = tournament_data.get("image")
    if not isinstance(competition_id, (str, int)) or not str(competition_id):
        competition_id = competition_slug if isinstance(competition_slug, str) else competition
    if not isinstance(competition_slug, str) or not competition_slug:
        competition_slug = re.sub(r"[^a-z0-9]+", "-", competition.casefold()).strip("-")
    if not isinstance(home_id, (str, int)) or not str(home_id):
        home_id = home_name
    if not isinstance(away_id, (str, int)) or not str(away_id):
        away_id = away_name
    home_score = raw.get("homeScore")
    away_score = raw.get("awayScore")
    home_current = _safe_int(home_score.get("current")) if isinstance(home_score, dict) else None
    away_current = _safe_int(away_score.get("current")) if isinstance(away_score, dict) else None
    best_of = _safe_int(raw.get("bestOf")) or 1
    if best_of not in {1, 3, 5}:
        best_of = 1
    status = _status(raw)
    payload: dict[str, object] = {
        "event": raw,
        "sourceUrl": link.url,
        "rendered": _visible_signals(page) if status == "live" else {},
    }
    return SofaEvent(
        source_id=str(raw.get("id") or link.source_id),
        url=link.url,
        home_name=home_name,
        away_name=away_name,
        competition=competition,
        competition_source_id=str(competition_id),
        competition_slug=competition_slug,
        home_source_id=str(home_id),
        away_source_id=str(away_id),
        home_image=home_image if isinstance(home_image, str) else "",
        away_image=away_image if isinstance(away_image, str) else "",
        competition_image=competition_image if isinstance(competition_image, str) else "",
        starts_at=_timestamp(raw.get("startTimestamp"), link.day),
        status=status,
        best_of=best_of,
        home_score=home_current,
        away_score=away_current,
        payload=payload,
    )


def _reveal_match_details(page: Page) -> None:
    """Open the rendered match-statistics tab when the public page exposes it."""
    try:
        # SofaScore currently calls this tab "Matches" in English and
        # "Matchs" in the French locale.  The test id is not stable across
        # event templates, so keep a DOM/text fallback as well.  This is still
        # a normal rendered-page interaction; no data endpoint is consulted.
        for test_id, labels in (
            ("tab-games", ("Games", "Jeux")),
            ("tab-matches", ("Matches", "Matchs")),
        ):
            tab_root = page.get_by_test_id(test_id)
            for label in labels:
                tab = tab_root.get_by_role("link", name=label, exact=True)
                if not tab.count():
                    tab = tab_root.get_by_text(label, exact=True)
                if tab.count():
                    tab.first.click()
                    page.wait_for_timeout(1_000)
                    return
        for label in ("Games", "Jeux", "Matches", "Matchs"):
            for role in ("link", "button"):
                tab = page.get_by_role(role, name=label, exact=True)
                if tab.count():
                    tab.first.click()
                    page.wait_for_timeout(1_000)
                    return
    except Exception:
        # Some event pages do not render the tab (or are not yet hydrated).
        pass


SCHEDULE_DAYS_BEFORE = 7
SCHEDULE_DAYS_AFTER = 7


def _close_browser() -> None:
    browser = _BROWSER.browser
    playwright = _BROWSER.playwright
    _BROWSER.page = None
    _BROWSER.context = None
    _BROWSER.browser = None
    _BROWSER.playwright = None
    _BROWSER.headless = None
    if browser is not None:
        try:
            browser.close()
        except Exception:
            pass
    if playwright is not None:
        try:
            playwright.stop()
        except Exception:
            pass


atexit.register(_close_browser)


def _browser_page(settings: Settings) -> Page:
    if _BROWSER.page is not None and _BROWSER.headless == settings.browser_headless:
        return _BROWSER.page
    _close_browser()
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=settings.browser_headless)
    context = browser.new_context(locale="fr-FR", timezone_id="Europe/Paris")
    page = context.new_page()
    page.set_default_timeout(settings.sofascore_timeout_seconds * 1000)
    _BROWSER.playwright = playwright
    _BROWSER.browser = browser
    _BROWSER.context = context
    _BROWSER.page = page
    _BROWSER.headless = settings.browser_headless
    # Reuse one normal public browsing session across scheduler ticks. This
    # reduces browser launches and source load; it is not a fingerprint or
    # anti-bot bypass.
    _navigate(page, ROOT_URL, settings)
    page.wait_for_timeout(500)
    return page


def scrape(settings: Settings, today: date | None = None) -> list[SofaEvent]:
    """Scrape the UI window (J-7 through J+7) through rendered pages.

    The source is discovered incrementally.  A scheduler tick visits only a
    small number of day listings and event pages, while the in-memory cache
    retains the rest of the already discovered window.  This keeps the normal
    five-minute refresh useful without turning one run into a burst of dozens
    of navigations that can trigger a source cooldown.
    """
    if not settings.sofascore_enabled:
        raise ValueError("SofaScore collection is disabled")
    current = today or datetime.now(PARIS).date()
    # Current and upcoming days are the useful first pass.  Older days remain
    # in the same exact J-7/J+7 contract and are filled during later ticks.
    days = [
        date.fromordinal(current.toordinal() + offset)
        for offset in range(0, SCHEDULE_DAYS_AFTER + 1)
    ] + [
        date.fromordinal(current.toordinal() + offset) for offset in range(-SCHEDULE_DAYS_BEFORE, 0)
    ]
    day_key = tuple(days)
    now = clock.monotonic()
    if _STATE.blocked_until > now:
        cached = _cached_events()
        if cached:
            return cached
        raise SofaScoreBlocked(
            "SofaScore cooldown active without a cached schedule", reason="cooldown"
        )
    if _STATE.listing_days != day_key:
        _STATE.listing_days = day_key
        _STATE.listing_cursor = 0
        _STATE.listing_complete_at = 0.0
        _STATE.links = {}
    cached_links = _STATE.links or {}
    cycle_complete = _STATE.listing_cursor >= len(days)
    refresh_listing = (
        not cached_links
        or not cycle_complete
        or (now - _STATE.listing_complete_at >= settings.sofascore_listing_interval_seconds)
    )
    page = _browser_page(settings)
    if refresh_listing:
        if cycle_complete:
            _STATE.listing_cursor = 0
        batch = days[
            _STATE.listing_cursor : _STATE.listing_cursor + settings.sofascore_listing_days_per_run
        ]
        links = dict(_STATE.links or {})
        try:
            for day in batch:
                _navigate(page, _day_url(day), settings)
                try:
                    page.wait_for_selector(
                        'a[href*="/esports/match/"]',
                        state="attached",
                        timeout=settings.sofascore_timeout_seconds * 1000,
                    )
                except Exception:
                    pass
                page.wait_for_timeout(800)
                for link in _links(page.content(), day, page.url):
                    links[link.source_id] = link
                # Persist after each page so a later 403 cannot erase
                # the successful part of this incremental discovery.
                _STATE.links = links
                _STATE.listing_cursor += 1
        except SofaScoreBlocked:
            cached = _cached_events()
            if cached:
                return cached
            raise
        if _STATE.listing_cursor >= len(days):
            _STATE.listing_complete_at = clock.monotonic()
        unique = links
    else:
        unique = cached_links
    if not any(
        _should_refresh_event(link, clock.monotonic(), settings) for link in unique.values()
    ):
        return [
            (_STATE.events or {})[source_id]
            for source_id in unique
            if source_id in (_STATE.events or {})
        ]
    events = _STATE.events or {}
    fetched_at = _STATE.event_fetched_at or {}
    refreshable = [
        link for link in unique.values() if _should_refresh_event(link, clock.monotonic(), settings)
    ]
    refreshable.sort(key=lambda link: (link.day != current, link.day, link.source_id))
    for link in refreshable[
        : min(settings.sofascore_max_events, settings.sofascore_events_per_run)
    ]:
        try:
            _navigate(page, link.url, settings)
            page.wait_for_selector(
                "script#__NEXT_DATA__",
                state="attached",
                timeout=settings.sofascore_timeout_seconds * 1000,
            )
            page.wait_for_timeout(400)
            _reveal_match_details(page)
            event = _event_from_page(page, link)
            if event is not None:
                events[event.source_id] = event
                fetched_at[event.source_id] = clock.monotonic()
        except SofaScoreBlocked:
            if events:
                return list(events.values())
            raise
        except Exception:
            # One unstable public event must not discard the rest of the day.
            continue
    _STATE.events = events
    _STATE.event_fetched_at = fetched_at
    return [events[source_id] for source_id in unique if source_id in events]
