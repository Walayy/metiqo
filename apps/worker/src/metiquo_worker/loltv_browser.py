"""Optional DOM enrichment. Only the site's own scripts access its data services."""

import copy
import gzip
import re
import threading
from dataclasses import replace
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from metiquo_core.config import Settings
from patchright.sync_api import BrowserContext, Page, Playwright, Response, sync_playwright

from metiquo_worker.artifacts import store_bytes
from metiquo_worker.loltv_policy import LoltvBlocked, LoltvBudgetExhausted, LoltvPolicy
from metiquo_worker.matching import normalize_name
from metiquo_worker.sources.lol import obj, text
from metiquo_worker.sources.loltv import (
    ROLES,
    LoltvEvent,
    detail,
    image_url,
    page_objects,
    team_names,
)

DOM = (Path(__file__).parent / "sources/loltv_dom.js").read_text(encoding="utf-8")
_LOCAL = threading.local()


class BrowserSession:
    def __init__(self, settings: Settings):
        self.runtime: Playwright = sync_playwright().start()
        self.context: BrowserContext = self.runtime.chromium.launch_persistent_context(
            str(settings.loltv_browser_profile_dir.resolve()),
            channel=settings.loltv_browser_channel,
            headless=settings.browser_headless,
            locale="en-US",
            timezone_id="Europe/Paris",
            viewport={"width": 1440, "height": 1000},
        )
        for page in self.context.pages:
            page.close()

    def close(self) -> None:
        self.context.close()
        self.runtime.stop()


def close_browser() -> None:
    session = cast(BrowserSession | None, getattr(_LOCAL, "browser", None))
    if session is not None:
        session.close()
        _LOCAL.browser = None


def _roles(html: str) -> dict[str, str]:
    roles: dict[str, set[str]] = {}
    for row in page_objects(html):
        player = obj(row.get("player"))
        name = normalize_name(text(player.get("summoner_name")))
        role = ROLES.get(text(row.get("role")))
        if name and role:
            roles.setdefault(name, set()).add(role)
    return {name: next(iter(values)) for name, values in roles.items() if len(values) == 1}


def merge_dom(event: LoltvEvent, value: object, roles: dict[str, str]) -> LoltvEvent:
    if not isinstance(value, dict) or not isinstance(value.get("teams"), list):
        return event
    payload = copy.deepcopy(event.payload)
    rendered = payload.get("rendered")
    maps = rendered.get("maps") if isinstance(rendered, dict) else None
    if not isinstance(maps, list):
        return event
    game = next(
        (m for m in maps if isinstance(m, dict) and m.get("number") == value.get("number")), None
    )
    if game is None or not isinstance(game.get("sides"), list):
        return event
    for side in game["sides"]:
        if not isinstance(side, dict):
            continue
        name = event.home_name if side.get("position") == "home" else event.away_name
        teams = [
            t
            for t in value["teams"]
            if isinstance(t, dict)
            and normalize_name(str(t.get("name", "")))
            in team_names(event, str(side.get("position")))
        ]
        if len(teams) != 1:
            continue
        team = teams[0]
        players = team.get("players")
        if not isinstance(players, list) or len(players) != 5:
            continue
        parsed: list[dict[str, object]] = []
        previous = side.get("players")
        for player in players:
            if not isinstance(player, dict):
                continue
            name = str(player.get("name", ""))
            role = roles.get(normalize_name(name))
            if role is None or any(
                not isinstance(player.get(k), int) for k in ("kills", "deaths", "assists", "cs")
            ):
                continue
            old = (
                next(
                    (
                        p
                        for p in previous
                        if isinstance(p, dict)
                        and normalize_name(str(p.get("name", ""))) == normalize_name(name)
                    ),
                    None,
                )
                if isinstance(previous, list)
                else None
            )
            parsed.append(
                {
                    **player,
                    "id": f"loltv:player:{normalize_name(name)}",
                    "role": role,
                    "championImage": image_url(player.get("championImage")),
                    "gold": old.get("gold")
                    if isinstance(old, dict) and old.get("champion") == player.get("champion")
                    else None,
                }
            )
        if len(parsed) == 5 and len({p["role"] for p in parsed}) == 5:
            side["players"] = parsed
            if isinstance(team.get("towers"), int):
                side["towers"] = team["towers"]
            game["provenance"] = "html-embedded-and-rendered-dom"
    if isinstance(value.get("durationSeconds"), int):
        game["durationSeconds"] = value["durationSeconds"]
    return replace(event, payload=payload)


def render_details(
    event: LoltvEvent,
    html: str,
    settings: Settings,
    policy: LoltvPolicy,
    metrics: dict[str, object],
    acquired: set[str] | None = None,
) -> LoltvEvent:
    policy.check()
    session = cast(BrowserSession | None, getattr(_LOCAL, "browser", None))
    if session is None:
        session = BrowserSession(settings)
        _LOCAL.browser = session
    context = session.context
    page: Page | None = None
    refused: LoltvBlocked | None = None
    exhausted: LoltvBudgetExhausted | None = None
    traffic: dict[str, object] = {"requests": 0, "responses": []}

    def response(received: Response) -> None:
        nonlocal refused
        parsed = urlsplit(received.url)
        host = parsed.hostname or ""
        resource = received.request.resource_type
        # Never persist query tokens or response bodies from data calls.
        cast(list[object], traffic["responses"]).append(
            {
                "url": f"{parsed.scheme}://{host}{parsed.path}",
                "status": received.status,
                "type": resource,
            }
        )
        if (
            refused is None
            and (host == "loltv.gg" or host.endswith(".loltv.gg"))
            and received.status in {403, 429}
        ):
            try:
                refused = policy.block(
                    received.status,
                    "rendered-page",
                    received.headers.get("retry-after"),
                    request_url=received.url,
                    resource_type=resource,
                )
            finally:
                context.set_offline(True)
                for opened in context.pages:
                    opened.close()

    def request(_request: object) -> None:
        nonlocal exhausted, refused
        traffic["requests"] = int(cast(int, traffic["requests"])) + 1
        if refused is not None or exhausted is not None:
            return
        try:
            policy.browser_request()
        except LoltvBudgetExhausted as error:
            exhausted = error
            context.set_offline(True)
            for opened in context.pages:
                opened.close()
        except LoltvBlocked as error:
            refused = error
            context.set_offline(True)
            for opened in context.pages:
                opened.close()

    context.on("response", response)
    context.on("request", request)
    try:
        policy.before_request()
        page = context.new_page()
        page.goto(
            event.url, wait_until="domcontentloaded", timeout=settings.loltv_timeout_seconds * 1000
        )
        if refused:
            raise refused
        page.get_by_role("heading", name="Game stats", exact=True).wait_for(
            timeout=settings.loltv_timeout_seconds * 1000
        )
        source_html = page.content()
        event = detail(source_html, event)
        roles = _roles(source_html)
        rendered = event.payload.get("rendered")
        games = rendered.get("maps") if isinstance(rendered, dict) else None
        if not isinstance(games, list):
            return event
        for game in games:
            if not isinstance(game, dict):
                continue
            if game.get("status") == "finished" and str(game.get("sourceGameId")) in (
                acquired or set()
            ):
                continue
            sides = game.get("sides")
            if (
                game.get("status") == "finished"
                and isinstance(sides, list)
                and all(
                    isinstance(s, dict) and len(cast(list[object], s.get("players", []))) == 5
                    for s in sides
                )
            ):
                continue
            policy.check()
            number = game["number"]
            button = page.get_by_role("button", name="Select the match game")
            if f"Game {number}" not in button.inner_text():
                policy.before_request(wait=lambda seconds: page.wait_for_timeout(seconds * 1000))
                button.click()
                page.get_by_role("option", name=re.compile(rf"^Game {number}(?:\s|$)")).click()
            page.wait_for_function(
                """(number) => document.querySelector(
                    'button[aria-label="Select the match game"]'
                )?.textContent.includes('Game '+number)
                && !/Connecting|Loading/.test(document.querySelector('main')?.innerText || '')
                && document.querySelectorAll(
                    'main ul li a[href^="/stats/champion/"]'
                ).length === 10""",
                arg=number,
                timeout=settings.loltv_timeout_seconds * 1000,
            )
            # Match selector and ten current players must be stable across two DOM reads.
            first = page.evaluate(DOM)
            page.wait_for_timeout(500)
            second = page.evaluate(DOM)
            if (
                not isinstance(first, dict)
                or not isinstance(second, dict)
                or first.get("number") != number
                or second.get("number") != number
            ):
                raise ValueError("LoLTV game selection could not be verified")
            before = [
                (p.get("name"), p.get("champion"))
                for t in first.get("teams", [])
                for p in t.get("players", [])
            ]
            after = [
                (p.get("name"), p.get("champion"))
                for t in second.get("teams", [])
                for p in t.get("players", [])
            ]
            if before != after:
                raise ValueError("LoLTV lineup is still changing")
            event = merge_dom(event, second, roles)
            digest, path = store_bytes(
                settings.artifact_dir,
                "loltv-dom",
                gzip.compress(page.content().encode(), mtime=0),
                "html.gz",
            )
            cast(list[object], metrics.setdefault("renderedPages", [])).append(
                {"url": event.url, "game": number, "sha256": digest, "path": path}
            )
        return event
    except Exception:
        if refused is not None:
            raise refused from None
        if exhausted is not None:
            raise exhausted from None
        raise
    finally:
        context.remove_listener("response", response)
        context.remove_listener("request", request)
        if page is not None and not page.is_closed():
            page.close()
        policy.page_completed()
        cast(list[object], metrics.setdefault("browserNetwork", [])).append(traffic)
        policy.record_traffic(traffic)
        if refused is not None or exhausted is not None:
            close_browser()
