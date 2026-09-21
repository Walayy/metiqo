"""Rendered-page scraper for SofaScore LoL schedules and live event pages.

This module uses Patchright for the authoritative public-page record and a narrow,
best-effort ``curl-cffi`` lookup for typed lineup metadata that the rendered page
only exposes as champion portraits.  The enrichment is optional: a source block
never erases the page data already captured.
"""

from __future__ import annotations

import atexit
import json
import logging
import re
import time as clock
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from random import SystemRandom
from typing import Protocol, cast
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from metiquo_core.config import Settings
from patchright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

SOURCE = "sofascore"
ROOT_URL = "https://www.sofascore.com/fr/esports/lol"
PARIS = ZoneInfo("Europe/Paris")
MATCH_HREF = re.compile(r"/esports/match/[^?#]+(?:#id:(\d+))?")
RANDOM = SystemRandom()
logger = logging.getLogger(__name__)


class _SofaApiResponse(Protocol):
    status_code: int

    def json(self) -> object: ...


class _SofaApiSession(Protocol):
    def get(self, url: str, *, timeout: float) -> _SofaApiResponse: ...


_SOFA_API_SESSION: _SofaApiSession | None = None
_CHARACTER_NAMES: dict[str, str] = {}


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


def _should_refresh_event(
    link: SofaLink,
    now: float,
    settings: Settings,
    known_stable_ids: frozenset[str] = frozenset(),
) -> bool:
    events = _STATE.events or {}
    fetched_at = (_STATE.event_fetched_at or {}).get(link.source_id, 0.0)
    event = events.get(link.source_id)
    if event is None:
        return link.source_id not in known_stable_ids
    if event.status == "live":
        return now - fetched_at >= settings.sofascore_live_refresh_seconds
    if event.status == "scheduled":
        seconds_to_start = (event.starts_at - datetime.now(PARIS)).total_seconds()
        return seconds_to_start <= 30 * 60 and (
            now - fetched_at >= settings.sofascore_scheduled_refresh_seconds
        )
    # Completed events do not need repeated polling once their maps are fully
    # identified.  Older snapshots can, however, contain a portrait without
    # the champion name because the rendered page hides that label; revisit
    # those events at the scheduled cadence so the typed lineup enrichment can
    # backfill the missing name without changing any other historical field.
    if event.status == "finished" and _maps_need_detail_enrichment(event.payload):
        return now - fetched_at >= settings.sofascore_scheduled_refresh_seconds
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


def _character_source_id(image: object) -> str | None:
    if not isinstance(image, str):
        return None
    match = re.search(r"/character/(\d+)/image(?:$|[?/])", image)
    return match.group(1) if match is not None else None


def _player_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold()) if isinstance(value, str) else ""


def _sofascore_api_json(path: str, timeout_seconds: float) -> dict[str, object] | None:
    """Read one public SofaScore detail response with a Chrome TLS fingerprint.

    The rendered page remains authoritative for the match itself.  This narrow,
    best-effort lookup only restores labels which the rendered character icons do
    not expose.  If SofaScore blocks or changes the endpoint, the rendered map is
    still published with its portrait and an explicitly unknown name.
    """
    global _SOFA_API_SESSION
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        return None
    try:
        if _SOFA_API_SESSION is None:
            _SOFA_API_SESSION = cast(
                _SofaApiSession,
                curl_requests.Session(impersonate="chrome"),
            )
        response = _SOFA_API_SESSION.get(
            f"https://api.sofascore.com/api/v1/{path.lstrip('/')}",
            timeout=max(3.0, min(timeout_seconds, 15.0)),
        )
        if response.status_code in {403, 429}:
            logger.warning("SofaScore detail enrichment blocked (HTTP %s)", response.status_code)
            return None
        if response.status_code < 200 or response.status_code >= 300:
            return None
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except Exception as error:
        logger.debug("SofaScore detail enrichment failed: %s", error)
        return None


def _merge_lineup_champions(game_map: dict[str, object], lineup: dict[str, object]) -> None:
    """Fill champion names from the typed esports lineup response.

    The DOM deliberately exposes only ``/character/<id>/image``.  The lineup
    resource is the source that pairs that same character id with its official
    name; matching by player name prevents order changes from swapping picks.
    """
    sides = game_map.get("sides")
    if not isinstance(sides, list):
        return
    for side in sides:
        if not isinstance(side, dict):
            continue
        position = side.get("position")
        lineup_key = "homeTeamPlayers" if position == "home" else "awayTeamPlayers"
        lineup_players = lineup.get(lineup_key)
        if not isinstance(lineup_players, list):
            continue
        by_player = {
            _player_key(item.get("player", {}).get("name"))
            if isinstance(item, dict) and isinstance(item.get("player"), dict)
            else "": item
            for item in lineup_players
            if isinstance(item, dict)
        }
        players = side.get("players")
        if not isinstance(players, list):
            continue
        for player in players:
            if not isinstance(player, dict):
                continue
            source_player = by_player.get(_player_key(player.get("name")))
            if not isinstance(source_player, dict):
                continue
            character = source_player.get("character")
            if not isinstance(character, dict):
                continue
            name = character.get("name")
            source_id = character.get("id")
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            if isinstance(source_id, (int, str)) and str(source_id).isdigit():
                character_id = str(source_id)
                _CHARACTER_NAMES[character_id] = name
                if not isinstance(player.get("championImage"), str) or not player.get(
                    "championImage"
                ):
                    player["championImage"] = (
                        f"https://img.sofascore.com/api/v1/character/{character_id}/image"
                    )
            player["champion"] = name


def _apply_cached_champions(game_map: dict[str, object]) -> set[str]:
    """Apply names learned from earlier games and return still-unknown ids."""
    unknown: set[str] = set()
    sides = game_map.get("sides")
    if not isinstance(sides, list):
        return unknown
    for side in sides:
        if not isinstance(side, dict):
            continue
        players = side.get("players")
        if not isinstance(players, list):
            continue
        for player in players:
            if not isinstance(player, dict) or player.get("champion"):
                continue
            source_id = _character_source_id(player.get("championImage"))
            if source_id is None:
                continue
            name = _CHARACTER_NAMES.get(source_id)
            if name is None:
                unknown.add(source_id)
            else:
                player["champion"] = name
    return unknown


def _maps_need_champion_enrichment(payload: dict[str, object]) -> bool:
    """Return whether a payload has identifiable portraits but no names yet."""
    maps = payload.get("maps")
    if not isinstance(maps, list):
        rendered = payload.get("rendered")
        maps = rendered.get("maps") if isinstance(rendered, dict) else None
    if not isinstance(maps, list):
        return False
    for game_map in maps:
        if not isinstance(game_map, dict):
            continue
        sides = game_map.get("sides")
        if not isinstance(sides, list):
            continue
        for side in sides:
            if not isinstance(side, dict):
                continue
            players = side.get("players")
            if not isinstance(players, list):
                continue
            for player in players:
                if not isinstance(player, dict) or player.get("champion"):
                    continue
                if _character_source_id(player.get("championImage")) is not None:
                    return True
    return False


def _maps_need_bans(payload: dict[str, object]) -> bool:
    """Return whether a started rendered map has no bans captured yet."""
    maps = payload.get("maps")
    if not isinstance(maps, list):
        rendered = payload.get("rendered")
        maps = rendered.get("maps") if isinstance(rendered, dict) else None
    if not isinstance(maps, list):
        return False
    for game_map in maps:
        if not isinstance(game_map, dict) or game_map.get("status") not in {"live", "finished"}:
            continue
        sides = game_map.get("sides")
        if not isinstance(sides, list) or not sides:
            continue
        bans = game_map.get("bans")
        # A live draft is published progressively. Keep asking until the
        # expected five bans per team are present instead of freezing the
        # first partial response forever.
        if not isinstance(bans, list) or len(bans) < 10:
            return True
    return False


def _maps_need_detail_enrichment(payload: dict[str, object]) -> bool:
    return _maps_need_champion_enrichment(payload) or _maps_need_bans(payload)


def _merge_lineup_bans(game_map: dict[str, object], bans_payload: dict[str, object]) -> None:
    """Store the source ban phase with temporary home/away team references."""
    bans: list[dict[str, object]] = []
    for key, team_ref in (("homeTeamBans", "home"), ("awayTeamBans", "away")):
        values = bans_payload.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            character_id = item.get("id")
            if not isinstance(name, str) or not name.strip():
                continue
            ban: dict[str, object] = {
                "teamId": team_ref,
                "champion": name.strip(),
                "championImage": "",
            }
            if isinstance(character_id, (int, str)) and str(character_id).isdigit():
                character_source_id = str(character_id)
                ban["championImage"] = (
                    f"https://img.sofascore.com/api/v1/character/{character_source_id}/image"
                )
                _CHARACTER_NAMES[character_source_id] = name.strip()
            bans.append(ban)
    if bans:
        game_map["bans"] = bans


def _enrich_rendered_maps(
    source_id: str, maps: list[dict[str, object]], timeout_seconds: float
) -> list[dict[str, object]]:
    """Resolve icon-only portraits to names without making enrichment mandatory."""
    unknown = set().union(*(_apply_cached_champions(item) for item in maps)) if maps else set()
    needs_bans = any(_maps_need_bans({"maps": [item]}) for item in maps)
    if not unknown and not needs_bans:
        return maps
    games_payload = _sofascore_api_json(f"event/{source_id}/esports-games", timeout_seconds)
    games = games_payload.get("games") if isinstance(games_payload, dict) else None
    if not isinstance(games, list):
        return maps
    for game_map in maps:
        number = game_map.get("number")
        if not isinstance(number, int) or number < 1 or number > len(games):
            continue
        game = games[number - 1]
        if not isinstance(game, dict):
            continue
        game_id = game.get("id")
        if not isinstance(game_id, (int, str)) or not str(game_id).isdigit():
            continue
        if unknown:
            lineup = _sofascore_api_json(
                f"esports-game/{game_id}/lineups",
                timeout_seconds,
            )
            if lineup is not None:
                _merge_lineup_champions(game_map, lineup)
        if _maps_need_bans({"maps": [game_map]}):
            bans_payload = _sofascore_api_json(
                f"esports-game/{game_id}/bans",
                timeout_seconds,
            )
            if bans_payload is not None:
                _merge_lineup_bans(game_map, bans_payload)
    return maps


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
        ) -> dict[str, object]:
            slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
            return {
                "id": (
                    f"sofascore:{source_id}:map:{number}:{position}:{player_role.casefold()}:{slug}"
                ),
                "name": name,
                "role": player_role,
                # The rendered panel supplies the portrait immediately. The
                # best-effort lineup enrichment fills the official name later;
                # keep it nullable when SofaScore does not expose that detail.
                "champion": None,
                "championImage": image if isinstance(image, str) else "",
                "level": int(level),
                "kills": int(kda[0]),
                "deaths": int(kda[1]),
                "assists": int(kda[2]),
                "cs": int(cs),
                "gold": _rendered_count(gold),
            }

        home_players.append(
            player("home", role, home_name, row[2], home_kda, row[5], row[7], images[index * 2])
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
        # The score emphasis is normally present. A strictly unequal rendered
        # final score is the safe fallback when SofaScore changes only classes.
        if score[0] != score[1]:
            winner = "home" if score[0] > score[1] else "away"
        else:
            return None

    def side(
        position: str, color: str, stats: list[int], players: list[dict[str, object]]
    ) -> dict[str, object]:
        return {
            "position": position,
            "side": color,
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
        "bans": [],
        "sides": [
            side("home", "blue", home_objectives, home_players),
            side("away", "red", away_objectives, away_players),
        ],
    }


def _visible_maps(
    page: Page,
    *,
    event_status: str,
    source_id: str,
) -> list[dict[str, object]]:
    """Read every game tab currently rendered by the public match page."""
    maps: list[dict[str, object]] = []
    tab_indices = [index for index in range(5) if page.get_by_test_id(f"tab-{index}").count()]
    for position, index in enumerate(tab_indices):
        tab = page.get_by_test_id(f"tab-{index}")
        try:
            try:
                tab.first.click(timeout=DETAIL_TAB_TIMEOUT_MS)
            except Exception:
                tab.first.evaluate("(element) => element.click()")
            page.wait_for_timeout(150)
            capture = page.evaluate(
                """() => {
                    const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));
                    const panel = panels.find((item) => {
                        const text = item.textContent || '';
                        return text.includes('Lineups') || text.includes('Compositions');
                    });
                    if (!panel) return null;
                    const elements = Array.from(panel.querySelectorAll('*'));
                    const directItems = elements.map((element) => ({
                        text: Array.from(element.childNodes)
                            .filter((node) => node.nodeType === 3)
                            .map((node) => (node.textContent || '').trim())
                            .filter(Boolean)
                            .join(' '),
                        className: typeof element.className === 'string' ? element.className : '',
                    })).filter((item) => item.text);
                    const objectiveIndex = directItems.findIndex(
                        (item) => ['Objectives', 'Objectifs'].includes(item.text)
                    );
                    const scoreItems = directItems
                        .slice(0, objectiveIndex)
                        .filter((item) => /^\\d+$/.test(item.text));
                    return {
                        direct: directItems.map((item) => item.text),
                        scoreClasses: scoreItems.slice(-2).map((item) => item.className),
                        championImages: Array.from(
                            panel.querySelectorAll('img[src*="/api/v1/character/"]')
                        )
                            .slice(0, 10)
                            .map((image) => image.getAttribute('src') || ''),
                    };
                }"""
            )
        except Exception:
            continue
        map_status = (
            "live" if event_status == "live" and position == len(tab_indices) - 1 else "finished"
        )
        parsed = _rendered_map(
            capture,
            number=index + 1,
            status=map_status,
            source_id=source_id,
        )
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
        # The dialog is asynchronous and not present on every navigation.
        pass


def _event_from_page(
    page: Page, link: SofaLink, *, api_timeout_seconds: float = 10.0
) -> SofaEvent | None:
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
    if not isinstance(home_image, str) or not home_image:
        home_image = _rendered_team_image(page, str(home_id), home_name)
    if not isinstance(away_image, str) or not away_image:
        away_image = _rendered_team_image(page, str(away_id), away_name)
    home_score = raw.get("homeScore")
    away_score = raw.get("awayScore")
    home_current = _safe_int(home_score.get("current")) if isinstance(home_score, dict) else None
    away_current = _safe_int(away_score.get("current")) if isinstance(away_score, dict) else None
    best_of = _safe_int(raw.get("bestOf")) or 1
    if best_of not in {1, 3, 5}:
        best_of = 1
    status = _status(raw)
    source_id = str(raw.get("id") or link.source_id)
    rendered = _visible_signals(page) if status in {"live", "finished"} else {}
    if status in {"live", "finished"}:
        maps = _visible_maps(
            page,
            event_status=status,
            source_id=source_id,
        )
        if maps:
            maps = _enrich_rendered_maps(source_id, maps, api_timeout_seconds)
            rendered["maps"] = maps
            map_numbers = [number for item in maps if isinstance(number := item.get("number"), int)]
            highest_map = max(map_numbers, default=0)
            if highest_map > best_of:
                best_of = 3 if highest_map <= 3 else 5
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
        # SofaScore currently calls this tab "Matches" in English and
        # "Matchs" in the French locale.  The test id is not stable across
        # event templates, so keep a DOM/text fallback as well.  This is still
        # a normal rendered-page interaction; any optional lineup enrichment is
        # performed separately and remains non-blocking.
        for test_id, labels in (
            ("tab-games", ("Games", "Jeux")),
            ("tab-matches", ("Matches", "Matchs")),
        ):
            tab_root = page.get_by_test_id(test_id)
            if tab_root.count():
                try:
                    tab_root.first.click(timeout=DETAIL_TAB_TIMEOUT_MS)
                except Exception:
                    tab_root.first.evaluate("(element) => element.click()")
                page.wait_for_timeout(1_000)
                return
            for label in labels:
                tab = tab_root.get_by_role("link", name=label, exact=True)
                if not tab.count():
                    tab = tab_root.get_by_text(label, exact=True)
                if tab.count():
                    tab.first.click(timeout=DETAIL_TAB_TIMEOUT_MS)
                    page.wait_for_timeout(1_000)
                    return
        for label in ("Games", "Jeux", "Matches", "Matchs"):
            for role in ("link", "button"):
                tab = page.get_by_role(role, name=label, exact=True)
                if tab.count():
                    tab.first.click(timeout=DETAIL_TAB_TIMEOUT_MS)
                    page.wait_for_timeout(1_000)
                    return
    except Exception:
        # Some event pages do not render the tab (or are not yet hydrated).
        pass


SCHEDULE_DAYS_BEFORE = 7
SCHEDULE_DAYS_AFTER = 7
DETAIL_TAB_TIMEOUT_MS = 2_000


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


def scrape(
    settings: Settings,
    today: date | None = None,
    known_stable_ids: set[str] | frozenset[str] | None = None,
) -> list[SofaEvent]:
    """Scrape the UI window (J-7 through J+7) through rendered pages.

    The source is discovered incrementally.  A scheduler tick visits only a
    small number of day listings and event pages, while the in-memory cache
    retains the rest of the already discovered window.  This keeps the normal
    five-minute refresh useful without turning one run into a burst of dozens
    of navigations that can trigger a source cooldown.
    """
    if not settings.sofascore_enabled:
        raise ValueError("SofaScore collection is disabled")
    stable_ids = frozenset(known_stable_ids or ())
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
        _should_refresh_event(link, clock.monotonic(), settings, stable_ids)
        for link in unique.values()
    ):
        return [
            (_STATE.events or {})[source_id]
            for source_id in unique
            if source_id in (_STATE.events or {})
        ]
    events = _STATE.events or {}
    fetched_at = _STATE.event_fetched_at or {}
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
    )
    refreshable.sort(key=lambda link: _refresh_sort_key(link, current, live_ids))
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
            event = _event_from_page(
                page,
                link,
                api_timeout_seconds=min(settings.sofascore_timeout_seconds, 15),
            )
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
