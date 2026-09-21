"""Rendered-page scraper for SofaScore LoL schedules and live event pages.

Only the rendered DOM and the HTML-embedded ``__NEXT_DATA__`` are read.
The site may load its own resources normally, but the collector neither calls
SofaScore JSON endpoints nor reads intercepted API response bodies.
"""

from __future__ import annotations

import atexit
import json
import logging
import re
import time as clock
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from random import SystemRandom
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from metiquo_core.config import Settings
from metiquo_core.matches import source_game, unique_bans
from patchright.sync_api import (
    BrowserContext,
    Page,
    Playwright,
    Response,
    sync_playwright,
)
from patchright.sync_api import (
    TimeoutError as BrowserTimeout,
)

from metiquo_worker.portraits import PortraitReference, record_portrait
from metiquo_worker.sofascore_policy import SofaScoreBlocked as SofaScoreBlocked
from metiquo_worker.sofascore_policy import SofaScorePolicy

SOURCE = "sofascore"
ROOT_URL = "https://www.sofascore.com/fr/esports/lol"
PARIS = ZoneInfo("Europe/Paris")
MATCH_HREF = re.compile(r"/esports/match/[^?#]+(?:#id:(\d+))?")
RANDOM = SystemRandom()
logger = logging.getLogger(__name__)


_POLICY: SofaScorePolicy | None = None
_BLOCK_ERROR: SofaScoreBlocked | None = None
_PORTRAITS: dict[str, dict[str, object]] = {}
_PORTRAIT_ROOT: Path | None = None
_VISITED_PAGES: set[str] = set()
_GAME_DOM = (
    Path(__file__)
    .with_name("sofascore_dom.js")
    .read_text(encoding="utf-8")
    .strip()
    .removesuffix(";")
)


@lru_cache(maxsize=1)
def _portrait_reference() -> PortraitReference:
    return PortraitReference()


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
    attempted_at: dict[str, float] | None = None
    day_fetched_at: dict[str, float] | None = None
    fresh: list[SofaEvent] | None = None
    priority_live_ids: list[str] | None = None


_STATE = _ScrapeState()


@dataclass
class _BrowserState:
    playwright: Playwright | None = None
    context: BrowserContext | None = None
    page: Page | None = None
    headless: bool | None = None
    profile: Path | None = None


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


def _refresh_sort_key(
    link: SofaLink, current: date, live_ids: frozenset[str]
) -> tuple[bool, bool, date, str]:
    """Put known live events ahead of the rest of the refresh queue."""
    return (
        link.source_id not in live_ids,
        link.day != current,
        link.day,
        link.source_id,
    )


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


def _raise_if_blocked() -> None:
    if _BLOCK_ERROR is not None:
        raise _BLOCK_ERROR


def _page_key(url: str) -> str:
    parsed = urlsplit(url)
    event_id = re.search(r"(?:^|,)id:(\d+)(?:,|$)", parsed.fragment)
    if "/esports/match/" in parsed.path and event_id:
        return "event:" + event_id.group(1)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), parsed.query, ""))


def _navigate(page: Page, url: str, settings: Settings) -> bool:
    _raise_if_blocked()
    key = _page_key(url)
    if key in _VISITED_PAGES:
        return False
    # Also deduplicate failed attempts: no retry of a page within this pass.
    _VISITED_PAGES.add(key)
    now = clock.monotonic()
    if _STATE.blocked_until > now:
        raise SofaScoreBlocked("SofaScore cooldown active", reason="cooldown")
    if _POLICY is not None:
        _POLICY.before_request()
    else:
        wait = _STATE.last_navigation_at + _bounded_delay(settings) - now
        if wait > 0:
            clock.sleep(wait)
    try:
        response = page.goto(url, wait_until="domcontentloaded")
    except Exception:
        _raise_if_blocked()
        raise
    finally:
        _STATE.last_navigation_at = clock.monotonic()
    _raise_if_blocked()
    status = getattr(response, "status", None)
    reason = f"http-{status}" if status in {403, 429} else _blocked_page_reason(page)
    if reason is not None:
        _cooldown(settings)
        if _POLICY is not None:
            raise _BLOCK_ERROR or _POLICY.block(
                status,
                reason,
                response.headers.get("retry-after") if response else None,
                request_url=response.url if response else url,
                resource_type="document",
            )
        raise SofaScoreBlocked(
            f"SofaScore blocked ({reason}, http_status={status or 'unknown'})",
            status=status if isinstance(status, int) else None,
            reason=reason,
        )
    return True


def _finish_page(*, persist_discovery: bool = False) -> None:
    # Stop the site's background polling while waiting, keeping its profile/cache.
    idle_browser()
    _STATE.last_navigation_at = clock.monotonic()
    if _POLICY is not None:
        # Match observations are checkpointed by sync only after publication.
        # A crash before publication must not leave an unpublished event "fresh".
        _POLICY.page_completed(checkpoint() if persist_discovery else None)
    _raise_if_blocked()


def _listing_interval(day: date, today: date, settings: Settings) -> int:
    if day < today:
        return settings.sofascore_past_listing_interval_seconds
    if day > today:
        return settings.sofascore_future_listing_interval_seconds
    return settings.sofascore_listing_interval_seconds


def _cache_event(event: SofaEvent, previous: SofaEvent | None) -> SofaEvent:
    """Retain completed live maps only in cache, never as a fresh observation."""
    if previous is None or event.status != "live":
        return event
    old = previous.payload.get("rendered")
    current = event.payload.get("rendered")
    if not isinstance(old, dict) or not isinstance(current, dict):
        return event
    old_maps, new_maps = old.get("maps", []), current.get("maps", [])
    if not isinstance(old_maps, list) or not isinstance(new_maps, list):
        return event
    maps = {
        item["number"]: item
        for item in old_maps
        if isinstance(item, dict) and item.get("status") == "finished" and "number" in item
    }
    maps.update(
        {item["number"]: item for item in new_maps if isinstance(item, dict) and "number" in item}
    )
    return replace(
        event, payload={**event.payload, "rendered": {**current, "maps": list(maps.values())}}
    )


def _should_refresh_event(
    link: SofaLink,
    now: float,
    settings: Settings,
    known_stable_ids: frozenset[str] = frozenset(),
) -> bool:
    attempted = (_STATE.attempted_at or {}).get(link.source_id)
    if attempted is not None and now - attempted < settings.sofascore_scheduled_refresh_seconds:
        return False
    events = _STATE.events or {}
    fetched_at = (_STATE.event_fetched_at or {}).get(link.source_id, 0.0)
    event = events.get(link.source_id)
    if event is None:
        return link.source_id not in known_stable_ids
    if event.status == "live":
        return now - fetched_at >= settings.sofascore_live_refresh_seconds
    if event.status in {"scheduled", "postponed"}:
        seconds_to_start = (event.starts_at - datetime.now(PARIS)).total_seconds()
        interval = (
            settings.sofascore_scheduled_refresh_seconds
            if seconds_to_start <= 30 * 60
            else settings.sofascore_upcoming_refresh_seconds
        )
        return now - fetched_at >= interval
    # Missing DOM labels cannot be repaired through API enrichment. Keep the
    # normal historical refresh interval once a map has been captured.
    rendered = event.payload.get("rendered")
    maps = rendered.get("maps") if isinstance(rendered, dict) else None
    if event.status == "finished" and not maps:
        return now - fetched_at >= settings.sofascore_incomplete_refresh_seconds
    # Historical corrections and late statistics remain discoverable throughout
    # J-7/J+7; "finished" is not a permanent cache entry.
    return now - fetched_at >= settings.sofascore_finished_refresh_seconds


def _timestamp(value: object, fallback_day: date) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("SofaScore did not publish a start timestamp")
    return datetime.fromtimestamp(value, UTC).astimezone(PARIS)


def _safe_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def _status(event: dict[str, object]) -> str | None:
    status = event.get("status")
    kind = status.get("type") if isinstance(status, dict) else None
    if kind in {"inprogress", "in_progress", "live"}:
        return "live"
    if kind in {"finished", "ended"}:
        return "finished"
    if kind in {"notstarted", "not_started", "scheduled"}:
        return "scheduled"
    if kind in {"canceled", "cancelled"}:
        return "cancelled"
    if kind in {"postponed", "interrupted", "suspended"}:
        return "postponed"
    return None


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
        if urlsplit(absolute).hostname != "www.sofascore.com":
            continue
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


def _rendered_team_image(page: Page, source_id: str, name: str) -> str:
    """Read a team crest URL already rendered on the public event page."""
    selectors = (
        f'img[src*="/api/v1/team/{source_id}/image"]',
        f'img[alt="{name.replace(chr(34), "")}"]',
    )
    for selector in selectors:
        try:
            image = page.locator(selector)
            if image.count():
                value = image.first.get_attribute("src")
                if isinstance(value, str) and value.startswith("https://img.sofascore.com/"):
                    return value
        except Exception:
            continue
    return ""


def _direct_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _rendered_count(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    compact = re.fullmatch(r"(\d+(?:[.,]\d+)?)K", value, re.I)
    if compact is not None:
        return round(float(compact.group(1).replace(",", ".")) * 1_000)
    return None


def _first_label(values: list[str], labels: tuple[str, ...], start: int = 0) -> int:
    indexes = [values.index(label, start) for label in labels if label in values[start:]]
    if not indexes:
        raise ValueError("rendered section label is absent")
    return min(indexes)


def _rendered_map(
    capture: object,
    *,
    number: int,
    status: str,
    source_id: str,
) -> dict[str, object] | None:
    """Turn one rendered SofaScore game panel into source-neutral map data.

    SofaScore does not expose accessible labels for every pictogram.  The four
    objective columns in its public LoL game panel are, in DOM order, dragons,
    barons, inhibitors and towers.  Fields which the page renders as ``-`` are
    kept as ``None``; they must never become made-up zeroes.
    """
    if not isinstance(capture, dict):
        return None
    values = capture.get("direct")
    images = capture.get("championImages")
    score_classes = capture.get("scoreClasses")
    names = capture.get("championNames")
    names = names if isinstance(names, list) else []
    if not isinstance(values, list) or not isinstance(images, list):
        return None
    direct = [_direct_text(value) for value in values]
    try:
        objectives_at = _first_label(direct, ("Objectives", "Objectifs"))
        lineups_at = _first_label(
            direct,
            ("Lineups", "Compositions"),
            objectives_at + 1,
        )
    except ValueError:
        return None

    before_objectives = [value for value in direct[:objectives_at] if value]
    score: list[int] | None = None
    for index in range(len(before_objectives) - 3, -1, -1):
        candidate = before_objectives[index : index + 3]
        if (
            len(candidate) == 3
            and candidate[1] == "-"
            and all(item.isdigit() for item in (candidate[0], candidate[2]))
        ):
            score = [int(candidate[0]), int(candidate[2])]
            break
    objective_values = [value for value in direct[objectives_at + 1 : lineups_at] if value]
    if (
        score is None
        or len(objective_values) < 8
        or not all(value.isdigit() for value in objective_values[:8])
    ):
        return None

    try:
        lineup_end = _first_label(
            direct,
            ("Ban Phase", "Phase de ban"),
            lineups_at + 1,
        )
    except ValueError:
        lineup_end = len(direct)
    lineup = [value for value in direct[lineups_at + 1 : lineup_end] if value]
    if len(lineup) < 50 or len(images) < 10 or len(lineup) % 5:
        return None
    row_width = len(lineup) // 5
    if row_width not in {10, 11}:
        return None

    roles = ("TOP", "JGL", "MID", "BOT", "SUP")
    home_players: list[dict[str, object]] = []
    away_players: list[dict[str, object]] = []
    for index, role in enumerate(roles):
        row = lineup[index * row_width : index * row_width + row_width]
        if len(row) != row_width:
            return None
        home_name, away_name = row[0], row[1]
        home_kda = row[3].split("/")
        away_kda = row[4].split("/")
        if (
            not home_name
            or not away_name
            or len(home_kda) != 3
            or len(away_kda) != 3
            or not all(
                value.isdigit() for value in [*home_kda, *away_kda, row[2], row[5], row[6], row[-1]]
            )
        ):
            return None

        def player(
            position: str,
            player_role: str,
            name: str,
            level: str,
            kda: list[str],
            cs: str,
            gold: str,
            image: object,
            champion: object,
        ) -> dict[str, object]:
            slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
            return {
                "id": (
                    f"sofascore:{source_id}:map:{number}:{position}:{player_role.casefold()}:{slug}"
                ),
                "name": name,
                "role": player_role,
                "champion": champion if isinstance(champion, str) and champion else None,
                "championImage": image if isinstance(image, str) else "",
                "level": int(level),
                "kills": int(kda[0]),
                "deaths": int(kda[1]),
                "assists": int(kda[2]),
                "cs": int(cs),
                "gold": _rendered_count(gold),
            }

        home_players.append(
            player(
                "home",
                role,
                home_name,
                row[2],
                home_kda,
                row[5],
                row[7],
                images[index * 2],
                names[index * 2] if len(names) > index * 2 else None,
            )
        )
        away_players.append(
            player(
                "away",
                role,
                away_name,
                row[-1],
                away_kda,
                row[6],
                row[-2],
                images[index * 2 + 1],
                names[index * 2 + 1] if len(names) > index * 2 + 1 else None,
            )
        )

    objectives = [int(value) for value in objective_values[:8]]
    home_objectives = objectives[:4]
    away_objectives = objectives[4:8]
    winner: str | None = None
    if status == "finished" and isinstance(score_classes, list) and len(score_classes) >= 2:
        home_class = _direct_text(score_classes[0])
        away_class = _direct_text(score_classes[1])
        if "primary" in home_class and "primary" not in away_class:
            winner = "home"
        elif "primary" in away_class and "primary" not in home_class:
            winner = "away"
    if status == "finished" and winner is None:
        # This score counts kills, not destroyed nexuses.
        return None

    def side(
        position: str, stats: list[int], players: list[dict[str, object]]
    ) -> dict[str, object]:
        return {
            "position": position,
            "side": None,
            "kills": score[0 if position == "home" else 1],
            "dragons": stats[0],
            "barons": stats[1],
            "inhibitors": stats[2],
            "towers": stats[3],
            "heralds": None,
            "grubs": None,
            "players": players,
        }

    return {
        "number": number,
        "status": status,
        "durationSeconds": None,
        "winner": winner,
        "bans": unique_bans(capture.get("bans")),
        "portraitEvidence": capture.get("portraitEvidence", {}),
        "sides": [
            side("home", home_objectives, home_players),
            side("away", away_objectives, away_players),
        ],
    }


def _resolve_portrait_labels(capture: dict[str, object]) -> None:
    reference = _portrait_reference()
    images, names = capture.get("championImages"), capture.get("championNames")
    images = images if isinstance(images, list) else []
    names = names if isinstance(names, list) else []
    evidence: dict[str, object] = {}

    def name_for(image: object, label: object) -> str | None:
        explicit = reference.label(label)
        if explicit:
            return explicit
        if not isinstance(image, str):
            return None
        observed = _PORTRAITS.get(image)
        if observed is None:
            return None
        evidence[image] = observed
        name = observed.get("name")
        return name if isinstance(name, str) else None

    capture["championNames"] = [
        name_for(image, names[index] if index < len(names) else None)
        for index, image in enumerate(images)
    ]
    raw_bans = capture.get("bans")
    capture["bans"] = (
        [
            {
                "teamId": ban.get("teamId"),
                "champion": name_for(ban.get("image"), ban.get("label")),
                "championImage": ban.get("image", ""),
            }
            for ban in raw_bans
            if isinstance(ban, dict)
        ]
        if isinstance(raw_bans, list)
        else []
    )
    capture["portraitEvidence"] = evidence


def _visible_maps(
    page: Page,
    *,
    event_status: str,
    source_id: str,
) -> list[dict[str, object]]:
    """Wait for the selected panel and its portraits, then read rendered data."""
    maps: list[dict[str, object]] = []
    previous = (_STATE.events or {}).get(source_id)
    rendered = previous.payload.get("rendered") if previous is not None else None
    previous_maps = rendered.get("maps", []) if isinstance(rendered, dict) else []
    completed = (
        {
            item.get("number")
            for item in previous_maps
            if isinstance(item, dict) and item.get("status") == "finished"
        }
        if isinstance(previous_maps, list) and event_status == "live"
        else set()
    )
    tab_indices = [index for index in range(5) if page.get_by_test_id(f"tab-{index}").count()]
    for position, index in enumerate(tab_indices):
        _raise_if_blocked()
        # Publication retains earlier completed maps; do not recollect them just
        # because another map in the same live series has changed.
        if index + 1 in completed:
            continue
        tab = page.get_by_test_id(f"tab-{index}")
        stage = "activate-tab"
        try:
            # An actual click lets the site's own JavaScript load the panel.
            if tab.first.get_attribute("aria-selected") != "true":
                tab.first.click(timeout=DETAIL_TAB_TIMEOUT_MS)
            _raise_if_blocked()
            stage = "read-panel"
            try:
                handle = page.wait_for_function(
                    "(args) => { const value = (" + _GAME_DOM + ")(args.index); "
                    "return value && value.ready && (args.live || value.bans.length === 10) "
                    "? value : false; }",
                    arg={"index": index, "live": event_status == "live"},
                )
                try:
                    capture = handle.json_value()
                finally:
                    handle.dispose()
            except BrowserTimeout:
                # Missing source fields remain unknown; a slow or incomplete
                # panel must not be replaced with another tab's stale contents.
                capture = page.evaluate(_GAME_DOM, index)
            if _BLOCK_ERROR is not None:
                raise _BLOCK_ERROR
            if not isinstance(capture, dict) or capture.get("number") != index + 1:
                continue
            _resolve_portrait_labels(capture)
        except SofaScoreBlocked:
            raise
        except Exception as error:
            _raise_if_blocked()
            logger.warning(
                "SofaScore map %s/%s unavailable at %s: %s",
                source_id,
                index + 1,
                stage,
                type(error).__name__,
            )
            continue
        finally:
            # An unsuccessful click must not remove the pause before the next tab.
            if _BLOCK_ERROR is None and position < len(tab_indices) - 1:
                page.wait_for_timeout(RANDOM.uniform(4000, 8000))
        map_status = (
            "live" if event_status == "live" and position == len(tab_indices) - 1 else "finished"
        )
        parsed = _rendered_map(capture, number=index + 1, status=map_status, source_id=source_id)
        if parsed is not None:
            maps.append(parsed)
    return maps


def _dismiss_consent(page: Page) -> None:
    """Close the rendered CMP without opting into optional data processing."""
    try:
        manage = page.locator(".fc-consent-root .fc-cta-manage-options:visible")
        if manage.count():
            manage.first.click(timeout=DETAIL_TAB_TIMEOUT_MS)
            confirm = page.locator(".fc-consent-root .fc-confirm-choices:visible")
            if confirm.count():
                confirm.first.click(timeout=DETAIL_TAB_TIMEOUT_MS)
                page.wait_for_timeout(200)
    except Exception:
        _raise_if_blocked()
        # The dialog is asynchronous and not present on every navigation.
        pass


def _event_from_page(page: Page, link: SofaLink) -> SofaEvent | None:
    html = page.content()
    raw = _event_from_next(html)
    if not raw:
        return None
    if source_game({"event": raw}) != "lol":
        logger.info("Ignoring SofaScore recommendation outside LoL: %s", link.source_id)
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
    if not isinstance(competition_image, str) or not competition_image:
        unique = tournament_data.get("uniqueTournament")
        ids = [tournament_data.get("id")]
        if isinstance(unique, dict):
            ids.append(unique.get("id"))
        for identifier in ids:
            if not isinstance(identifier, (int, str)) or not str(identifier).isdigit():
                continue
            logo = page.locator(
                f'img[src*="/tournament/{identifier}/image"], '
                f'img[src*="/unique-tournament/{identifier}/image"]'
            )
            if logo.count():
                observed = logo.first.get_attribute("src")
                if isinstance(observed, str) and urlsplit(observed).hostname == "img.sofascore.com":
                    competition_image = observed
                    break
    if not isinstance(competition_id, (str, int)) or not str(competition_id):
        competition_id = competition_slug if isinstance(competition_slug, str) else competition
    if not isinstance(competition_slug, str) or not competition_slug:
        competition_slug = re.sub(r"[^a-z0-9]+", "-", competition.casefold()).strip("-")
    if not isinstance(home_id, (str, int)) or not str(home_id):
        home_id = home_name
    if not isinstance(away_id, (str, int)) or not str(away_id):
        away_id = away_name
    if not isinstance(home_image, str) or not home_image:
        home_image = _rendered_team_image(page, str(home_id), home_name)
    if not isinstance(away_image, str) or not away_image:
        away_image = _rendered_team_image(page, str(away_id), away_name)
    home_score = raw.get("homeScore")
    away_score = raw.get("awayScore")
    home_current = _safe_int(home_score.get("current")) if isinstance(home_score, dict) else None
    away_current = _safe_int(away_score.get("current")) if isinstance(away_score, dict) else None
    best_of = _safe_int(raw.get("bestOf"))
    if best_of not in {1, 3, 5}:
        return None
    assert best_of is not None
    status = _status(raw)
    if status is None:
        return None
    source_id = str(raw.get("id") or link.source_id)
    rendered = _visible_signals(page) if status in {"live", "finished"} else {}
    if status in {"live", "finished"}:
        maps = _visible_maps(
            page,
            event_status=status,
            source_id=source_id,
        )
        if maps:
            rendered["maps"] = maps
            map_numbers = [number for item in maps if isinstance(number := item.get("number"), int)]
            highest_map = max(map_numbers, default=0)
            if highest_map > best_of:
                logger.warning("SofaScore event %s has maps beyond its published format", source_id)
                rendered["maps"] = []
    payload: dict[str, object] = {
        "event": raw,
        "sourceUrl": link.url,
        "rendered": rendered,
    }
    return SofaEvent(
        source_id=source_id,
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
        _dismiss_consent(page)
        if _status(_event_from_next(page.content())) not in {"live", "finished"}:
            return
        # The HTML script can arrive before React has rendered the controls.
        # Wait for a real detail tab before deciding that no maps are available.
        page.wait_for_selector(
            '[data-testid="tab-games"], [data-testid="tab-matches"]', state="visible"
        )
        # SofaScore currently calls this tab "Matches" in English and
        # "Matchs" in the French locale.  The test id is not stable across
        # event templates, so keep a DOM/text fallback as well.  This is still
        # a normal rendered-page interaction, with no separate API lookup.
        for test_id, labels in (
            ("tab-games", ("Games", "Jeux")),
            ("tab-matches", ("Matches", "Matchs")),
        ):
            tab_root = page.get_by_test_id(test_id)
            if tab_root.count():
                if tab_root.first.get_attribute("aria-selected") != "true":
                    tab_root.first.click(timeout=DETAIL_TAB_TIMEOUT_MS)
                _raise_if_blocked()
                page.wait_for_selector('[data-testid="tab-0"]', state="visible")
                return
            for label in labels:
                tab = tab_root.get_by_role("link", name=label, exact=True)
                if not tab.count():
                    tab = tab_root.get_by_text(label, exact=True)
                if tab.count():
                    tab.first.click(timeout=DETAIL_TAB_TIMEOUT_MS)
                    page.wait_for_selector('[data-testid="tab-0"]', state="visible")
                    return
        for label in ("Games", "Jeux", "Matches", "Matchs"):
            for role in ("link", "button"):
                tab = page.get_by_role(role, name=label, exact=True)
                if tab.count():
                    tab.first.click(timeout=DETAIL_TAB_TIMEOUT_MS)
                    page.wait_for_selector('[data-testid="tab-0"]', state="visible")
                    return
    except Exception:
        _raise_if_blocked()
        # Some event pages do not render the tab (or are not yet hydrated).
        pass


SCHEDULE_DAYS_BEFORE = 7
SCHEDULE_DAYS_AFTER = 7
DETAIL_TAB_TIMEOUT_MS = 10_000


def _close_browser() -> None:
    context = _BROWSER.context
    playwright = _BROWSER.playwright
    _BROWSER.page = None
    _BROWSER.context = None
    _BROWSER.playwright = None
    _BROWSER.headless = None
    _BROWSER.profile = None
    if context is not None:
        try:
            context.close()
        except Exception:
            pass
    if playwright is not None:
        try:
            playwright.stop()
        except Exception:
            pass


atexit.register(_close_browser)


def _browser_page(settings: Settings) -> Page:
    global _PORTRAIT_ROOT
    _PORTRAIT_ROOT = settings.artifact_dir
    _raise_if_blocked()
    if _POLICY is not None:
        _POLICY.check()
    profile = settings.sofascore_browser_profile_dir.resolve()
    if _BROWSER.headless != settings.browser_headless or _BROWSER.profile != profile:
        _close_browser()
    if _BROWSER.context is None:
        profile.mkdir(parents=True, exist_ok=True)
        playwright = sync_playwright().start()
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=settings.browser_headless,
                locale="fr-FR",
                timezone_id="Europe/Paris",
            )
        except Exception:
            playwright.stop()
            raise
        _BROWSER.playwright = playwright
        _BROWSER.context = context
        _BROWSER.headless = settings.browser_headless
        _BROWSER.profile = profile
        # Listening is passive. Routing all requests would disable HTTP caching.
        context.on("response", _observe_response)
    context = _BROWSER.context
    context.set_offline(False)
    page = _BROWSER.page
    if page is None or page.is_closed():
        page = context.pages[0] if context.pages else context.new_page()
        _BROWSER.page = page
    page.set_default_timeout(settings.sofascore_timeout_seconds * 1000)
    # A persistent profile also keeps cookies and browser cache across restarts.
    return page


def _stop_source_network() -> None:
    """Cut off the context at the first refusal, without installing a route."""
    context = _BROWSER.context
    if context is not None:
        try:
            context.set_offline(True)
            for page in context.pages:
                page.close()
            _BROWSER.page = None
        except Exception:
            _close_browser()


def _observe_response(response: Response) -> None:
    """Observe refusals and rendered portrait bytes, never JSON API bodies."""
    global _BLOCK_ERROR
    if _BLOCK_ERROR is not None:
        return
    parsed = urlsplit(response.url)
    if (
        parsed.hostname == "img.sofascore.com"
        and re.fullmatch(r"/api/v1/character/\d+/image", parsed.path)
        and response.status == 200
        and _PORTRAIT_ROOT is not None
        and response.headers.get("content-type", "").startswith("image/")
    ):
        try:
            raw = response.body()
            if len(raw) <= 1_000_000:
                if len(_PORTRAITS) >= 512:
                    _PORTRAITS.pop(next(iter(_PORTRAITS)))
                _PORTRAITS[response.url] = record_portrait(
                    raw, _portrait_reference(), _PORTRAIT_ROOT
                )
        except Exception as error:
            logger.warning("Unreadable rendered portrait: %s", type(error).__name__)
        return
    if parsed.hostname not in {"www.sofascore.com", "api.sofascore.com", "img.sofascore.com"}:
        return
    if response.status in {403, 429}:
        retry_after = response.headers.get("retry-after")
        resource_type = response.request.resource_type
        _BLOCK_ERROR = SofaScoreBlocked(
            f"SofaScore blocked (browser-response, http_status={response.status})",
            status=response.status,
            reason="browser-response",
        )
        _stop_source_network()
        if _POLICY is not None:
            _BLOCK_ERROR = _POLICY.block(
                response.status,
                "browser-response",
                retry_after,
                request_url=response.url,
                resource_type=resource_type,
            )
        logger.warning(
            "SofaScore refused %s %s%s (HTTP %s)",
            resource_type,
            parsed.hostname,
            parsed.path,
            response.status,
        )
        return


def idle_browser() -> None:
    if _BROWSER.page is not None:
        try:
            _BROWSER.page.goto("about:blank")
        except Exception:
            _close_browser()


def checkpoint() -> dict[str, object]:
    """Convert monotonic cache clocks to portable UTC timestamps."""
    offset = clock.time() - clock.monotonic()
    value = asdict(_STATE)
    value.pop("fresh", None)
    value.pop("blocked_until", None)  # Owned by the shared policy, not the cache.
    for field in ("last_navigation_at", "listing_complete_at"):
        value[field] = value[field] + offset if value[field] else 0
    for field in ("event_fetched_at", "attempted_at", "day_fetched_at"):
        value[field] = {key: at + offset for key, at in (value[field] or {}).items()}
    value["listing_days"] = [day.isoformat() for day in (_STATE.listing_days or ())]
    value["links"] = {
        key: {**asdict(link), "day": link.day.isoformat()}
        for key, link in (_STATE.links or {}).items()
    }
    value["events"] = {
        key: {**asdict(event), "starts_at": event.starts_at.isoformat()}
        for key, event in (_STATE.events or {}).items()
    }
    return value


def restore_checkpoint(value: object) -> None:
    global _STATE
    if not isinstance(value, dict) or not value:
        _STATE = _ScrapeState()
        return
    try:
        data = dict(value)
        offset = clock.time() - clock.monotonic()
        for field in ("last_navigation_at", "listing_complete_at"):
            data[field] = data.get(field, 0) - offset if data.get(field) else 0
        for field in ("event_fetched_at", "attempted_at", "day_fetched_at"):
            data[field] = {key: at - offset for key, at in data.get(field, {}).items()}
        data["listing_days"] = tuple(date.fromisoformat(day) for day in data["listing_days"])
        data["links"] = {
            key: SofaLink(**{**item, "day": date.fromisoformat(item["day"])})
            for key, item in data["links"].items()
        }
        data["events"] = {
            key: SofaEvent(**{**item, "starts_at": datetime.fromisoformat(item["starts_at"])})
            for key, item in data["events"].items()
        }
        _STATE = _ScrapeState(**data)
    except (KeyError, TypeError, ValueError):
        logger.warning("Invalid SofaScore checkpoint; rebuilding discovery from source")
        _STATE = _ScrapeState()


def scrape(
    settings: Settings,
    today: date | None = None,
    known_stable_ids: set[str] | frozenset[str] | None = None,
) -> list[SofaEvent]:
    """Scrape the UI window (J-7 through J+7) through rendered pages.

    Every due listing and event in the window is visited once per pass.
    Freshness clocks avoid unnecessary rereads; sequential pacing and source
    refusal handling remain in force independently of the number of matches.
    """
    if not settings.sofascore_enabled:
        raise ValueError("SofaScore collection is disabled")
    _raise_if_blocked()
    _VISITED_PAGES.clear()
    _STATE.fresh = []
    stable_ids = frozenset(known_stable_ids or ())
    current = today or datetime.now(PARIS).date()
    # Visit the entire J-7/J+7 window, starting with the current day.
    days = [
        date.fromordinal(current.toordinal() + offset)
        for offset in range(0, SCHEDULE_DAYS_AFTER + 1)
    ] + [
        date.fromordinal(current.toordinal() + offset) for offset in range(-SCHEDULE_DAYS_BEFORE, 0)
    ]
    day_key = tuple(days)
    now = clock.monotonic()
    if _STATE.blocked_until > now:
        raise SofaScoreBlocked("SofaScore cooldown active", reason="cooldown")
    if _STATE.listing_days != day_key:
        _STATE.listing_days = day_key
        _STATE.listing_cursor = 0
        _STATE.listing_complete_at = 0.0
        _STATE.links = {
            key: link for key, link in (_STATE.links or {}).items() if link.day in day_key
        }
        _STATE.attempted_at = {
            key: at for key, at in (_STATE.attempted_at or {}).items() if key in _STATE.links
        }
        _STATE.day_fetched_at = {
            day: at
            for day, at in (_STATE.day_fetched_at or {}).items()
            if date.fromisoformat(day) in day_key
        }
        _STATE.events = {
            key: event
            for key, event in (_STATE.events or {}).items()
            if event.starts_at.astimezone(PARIS).date() in day_key
        }
        _STATE.event_fetched_at = {
            key: value
            for key, value in (_STATE.event_fetched_at or {}).items()
            if key in _STATE.events
        }
    cached_links = _STATE.links or {}
    day_times = _STATE.day_fetched_at or {}
    # Current-day discovery has its own clock; it no longer waits for the
    # complete 15-day rotation before noticing a newly listed live fixture.
    due_days = [
        day
        for day in days
        if day.isoformat() not in day_times
        or now - day_times[day.isoformat()] >= _listing_interval(day, current, settings)
    ]
    due_days.sort(
        key=lambda day: (
            day != current,
            day_times.get(day.isoformat(), 0),
            abs((day - current).days),
        )
    )
    refresh_listing = bool(due_days)
    if not refresh_listing and not any(
        _should_refresh_event(link, now, settings, stable_ids) for link in cached_links.values()
    ):
        return []
    page = _browser_page(settings)
    if refresh_listing:
        links = dict(_STATE.links or {})
        try:
            for day in due_days:
                try:
                    if not _navigate(page, _day_url(day), settings):
                        continue
                    try:
                        page.wait_for_selector(
                            'a[href*="/esports/match/"]',
                            state="attached",
                            timeout=min(settings.sofascore_timeout_seconds * 1000, 5000),
                        )
                    except BrowserTimeout:
                        _raise_if_blocked()
                    page.wait_for_timeout(800)
                    _raise_if_blocked()
                    for link in _links(page.content(), day, page.url):
                        links.setdefault(link.source_id, link)
                    _STATE.links = links
                    _STATE.listing_cursor += 1
                    day_times[day.isoformat()] = clock.monotonic()
                    _STATE.day_fetched_at = day_times
                finally:
                    _finish_page(persist_discovery=True)
        except SofaScoreBlocked:
            raise
        if _STATE.listing_cursor >= len(days):
            _STATE.listing_complete_at = clock.monotonic()
        unique = links
    else:
        unique = cached_links
    if not any(
        _should_refresh_event(link, clock.monotonic(), settings, stable_ids)
        for link in unique.values()
    ):
        return []
    events = dict(_STATE.events or {})
    fetched_at = dict(_STATE.event_fetched_at or {})
    refreshable = [
        link
        for link in unique.values()
        if _should_refresh_event(link, clock.monotonic(), settings, stable_ids)
    ]
    # Live pages must be visited before the long tail of scheduled fixtures.
    # Otherwise a live series discovered late in the day can wait behind all
    # other current-day links, even though its refresh interval has elapsed.
    live_ids = frozenset(
        source_id for source_id, event in (_STATE.events or {}).items() if event.status == "live"
    ) | frozenset(_STATE.priority_live_ids or [])
    refreshable.sort(
        key=lambda link: (
            link.source_id not in live_ids,
            fetched_at.get(link.source_id, 0.0),
            _refresh_sort_key(link, current, live_ids),
        )
    )
    fresh = _STATE.fresh
    visited_ids: set[str] = set()
    for link in refreshable:
        if link.source_id in visited_ids:
            continue
        visited_ids.add(link.source_id)
        try:
            if not _navigate(page, link.url, settings):
                continue
            page.wait_for_selector(
                "script#__NEXT_DATA__",
                state="attached",
                timeout=settings.sofascore_timeout_seconds * 1000,
            )
            _reveal_match_details(page)
            _raise_if_blocked()
            event = _event_from_page(page, link)
            _raise_if_blocked()
            if event is not None:
                visited_ids.add(event.source_id)
                _VISITED_PAGES.add("event:" + event.source_id)
                events[event.source_id] = _cache_event(event, events.get(event.source_id))
                fetched_at[event.source_id] = clock.monotonic()
                fresh.append(event)
                _STATE.events = events
                _STATE.event_fetched_at = fetched_at
                (_STATE.attempted_at or {}).pop(link.source_id, None)
                if _POLICY is not None:
                    _POLICY.check()
            else:
                logger.warning("SofaScore event %s could not be parsed", link.source_id)
                _STATE.attempted_at = {
                    **(_STATE.attempted_at or {}),
                    link.source_id: clock.monotonic(),
                }
        except SofaScoreBlocked:
            raise
        except Exception as error:
            _raise_if_blocked()
            # One unstable public event must not discard the rest of the day.
            logger.warning("SofaScore event %s failed: %s", link.source_id, type(error).__name__)
            _STATE.attempted_at = {**(_STATE.attempted_at or {}), link.source_id: clock.monotonic()}
            continue
        finally:
            _finish_page()
    _STATE.events = events
    _STATE.event_fetched_at = fetched_at
    if refreshable and not fresh:
        raise RuntimeError("No requested SofaScore event could be refreshed")
    return fresh
