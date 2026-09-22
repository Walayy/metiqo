"""The anonymous feed consultation exposed by LoLTV's public match component.

Discover the current session action in linked JS; never pin a build-specific
action, use account credentials, persist cookies or retry a rejected action.
"""

import copy
import gzip
import hashlib
import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from metiquo_core.config import Settings
from pydantic import JsonValue

from metiquo_worker.artifacts import store_bytes
from metiquo_worker.loltv_clock import frame_duration
from metiquo_worker.loltv_policy import LoltvPolicy
from metiquo_worker.sources.lol import array, obj, text
from metiquo_worker.sources.loltv import ROOT_URL, LoltvEvent, _position, source_maps, timestamp

ACTION = re.compile(r'createServerReference\)\("([a-f0-9]{40,64})",[^;]{0,300}?"getFeedSession"\)')
SESSION_COOKIES = {"loltv.scope", "loltv.scope.flag"}
_local = threading.local()


class AnonymousSessions:
    """Short-lived, match-scoped cookies in this worker thread only, never on disk."""

    def __init__(self) -> None:
        self.entries: dict[str, tuple[str, float, httpx.Cookies]] = {}

    def restore(self, client: httpx.Client, match_id: str, action: str) -> bool:
        now = time.time()
        self.entries = {key: item for key, item in self.entries.items() if item[1] > now}
        for cookie in list(client.cookies.jar):
            if cookie.name in SESSION_COOKIES:
                client.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)
        item = self.entries.get(match_id)
        if item is None or item[0] != action:
            return False
        for cookie in item[2].jar:
            client.cookies.jar.set_cookie(copy.copy(cookie))
        return True

    def remember(self, client: httpx.Client, match_id: str, action: str) -> None:
        now, cookies = time.time(), httpx.Cookies()
        expires = now + 300
        for cookie in client.cookies.jar:
            if (
                cookie.name in SESSION_COOKIES
                and cookie.domain.lstrip(".") == "loltv.gg"
                and not cookie.is_expired(int(now))
            ):
                cookies.jar.set_cookie(copy.copy(cookie))
                if cookie.expires is not None:
                    expires = min(expires, cookie.expires)
        if not any(cookie.name == "loltv.scope" for cookie in cookies.jar):
            raise ValueError("LoLTV did not provide an anonymous feed session")
        if len(self.entries) >= 64 and match_id not in self.entries:
            del self.entries[min(self.entries, key=lambda key: self.entries[key][1])]
        self.entries[match_id] = (action, expires, cookies)


def anonymous_sessions() -> AnonymousSessions:
    if not hasattr(_local, "sessions"):
        _local.sessions = AnonymousSessions()
    return cast(AnonymousSessions, _local.sessions)


def merge_feed(event: LoltvEvent, game_id: str, data: object) -> LoltvEvent:
    if not isinstance(data, dict) or data.get("id") != game_id or data.get("type") != "feed":
        raise ValueError("LoLTV feed does not identify the requested game")
    # Source time is retained separately from our retrieval time.
    timestamp(data.get("timestamp"))
    raw_games = event.payload.get("sourceGames")
    games = copy.deepcopy(raw_games) if isinstance(raw_games, list) else []
    game = next((g for g in games if isinstance(g, dict) and g.get("id") == game_id), None)
    if game is None or not isinstance(data.get("teams"), list) or len(data["teams"]) != 2:
        raise ValueError("LoLTV feed game or teams missing")
    originals = array(game.get("teams"))
    matched: list[dict[str, JsonValue]] = []
    identities: set[str] = set()
    camps: set[str] = set()
    for value in data["teams"]:
        feed = obj(value)
        players = [obj(p) for p in array(feed.get("players"))]
        if len(players) != 5 or feed.get("side") not in {"BLUE", "RED"}:
            raise ValueError("LoLTV feed lineup is incomplete")
        candidates: list[tuple[dict[str, JsonValue], str]] = []
        for original in originals:
            side = obj(original)
            codes = {text(obj(side.get("team")).get("code"))}
            position = _position(side, event)
            raw_match = event.payload.get("sourceMatch")
            if position and isinstance(raw_match, dict):
                listed_team = obj(raw_match.get("team1" if position == "home" else "team2"))
                codes.add(text(listed_team.get("code")))
            # LoLTV's public Game component strips the .A/.C suffix from tags.
            # Only interpret this within these two already identified match teams;
            # two matching candidates still fail, never merge academy identities.
            codes |= {re.sub(r"\.\w+", "", code, count=1) for code in codes}
            codes = {code.casefold() for code in codes}
            # All five published participant tags must match the exact team code.
            # Never fall back to the placeholder side or a substring match.
            for code in codes:
                if code and all(
                    text(p.get("summoner_name")).casefold().startswith(code.casefold() + " ")
                    for p in players
                ):
                    candidates.append((side, code))
        if len(candidates) != 1:
            raise ValueError("LoLTV feed team identity is ambiguous")
        original, code = candidates[0]
        identity = text(original.get("id"))
        if not identity or identity in identities or str(feed["side"]) in camps:
            raise ValueError("LoLTV feed repeats a team or camp")
        identities.add(identity)
        camps.add(str(feed["side"]))
        players = [
            {**p, "summoner_name": text(p.get("summoner_name"))[len(code) + 1 :].strip()}
            for p in players
        ]
        dragons = feed.get("dragons")
        matched.append(
            {
                **original,
                **feed,
                "team": original.get("team"),
                "team_name": original.get("team_name"),
                "id": original.get("id"),
                "win": original.get("win"),
                "players": cast(JsonValue, players),
                "dragons": len(dragons) if isinstance(dragons, list) else None,
                # Unpublished objectives must not inherit SSR placeholder zeros.
                "herald": feed.get("herald"),
                "horde": feed.get("horde"),
                "bans": feed.get("bans", original.get("bans", [])),
            }
        )
    game["teams"] = matched
    duration = frame_duration(data.get("events"))
    # A completed feed has no winner field. Wait for the independently sourced
    # HTML result rather than deriving a winner from kills, towers or camps.
    if data.get("state") in {"STARTED", "PAUSED"} and game.get("state") != "COMPLETED":
        game["state"] = "STARTED"
    maps = source_maps(cast(list[JsonValue], [game]), event)
    if len(maps) == 1 and duration is not None:
        # Zero in SSR is a placeholder; a zero from an observed feed is valid.
        maps[0]["durationSeconds"] = duration
        maps[0]["durationSource"] = "loltv-event-clock"
    sides = maps[0].get("sides") if len(maps) == 1 else None
    if not isinstance(sides, list) or any(len(s["players"]) != 5 for s in sides):
        raise ValueError("LoLTV feed statistics are incomplete")
    maps[0]["provenance"] = "public-html-and-anonymous-feed"
    maps[0]["sourceObservedAt"] = data["timestamp"]
    rendered = event.payload.get("rendered")
    previous = rendered.get("maps", []) if isinstance(rendered, dict) else []
    result = [m for m in previous if isinstance(m, dict) and m.get("sourceGameId") != game_id]
    states = event.payload.get("feedStates")
    return replace(
        event,
        payload={
            **event.payload,
            "feedStates": {
                **(states if isinstance(states, dict) else {}),
                game_id: {"state": data.get("state"), "timestamp": data["timestamp"]},
            },
            "rendered": {"maps": sorted(result + maps, key=lambda m: m["number"])},
        },
    )


class FeedReader:
    def __init__(
        self,
        settings: Settings,
        policy: LoltvPolicy,
        state: dict[str, object],
        metrics: dict[str, object],
        sessions: AnonymousSessions | None = None,
    ):
        self.settings, self.policy, self.state, self.metrics = settings, policy, state, metrics
        self.sessions = sessions if sessions is not None else anonymous_sessions()

    def request(
        self,
        client: httpx.Client,
        url: str,
        kind: str,
        *,
        action: str | None = None,
        match_id: str | None = None,
    ) -> bytes:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme == "https"
            and not parsed.query
            and not parsed.fragment
            and (
                (
                    kind == "script"
                    and parsed.netloc == "loltv.gg"
                    and parsed.path.startswith("/_next/static/")
                    and parsed.path.endswith(".js")
                )
                or (
                    kind == "session"
                    and parsed.netloc == "loltv.gg"
                    and parsed.path.startswith("/match/")
                )
                or (
                    kind == "feed"
                    and parsed.netloc == "feed.loltv.gg"
                    and re.fullmatch(r"/feed/[a-f0-9]{24}", parsed.path)
                )
            )
        )
        if not valid:
            raise ValueError("LoLTV resource outside the source allowlist")
        self.policy.check()
        self.policy.before_request()
        started = time.monotonic()
        headers = {"Accept": "application/json" if kind == "feed" else "*/*"}
        if kind == "session":
            if not action or not match_id:
                raise ValueError("LoLTV anonymous session action missing")
            headers.update(
                {
                    "Next-Action": action,
                    "Accept": "text/x-component",
                    "Content-Type": "text/plain;charset=UTF-8",
                    "Origin": ROOT_URL,
                }
            )
        with client.stream(
            "POST" if kind == "session" else "GET",
            url,
            headers=headers,
            content=json.dumps([match_id]) if kind == "session" else None,
        ) as response:
            if response.status_code in {403, 429}:
                raise self.policy.block(
                    response.status_code,
                    kind,
                    response.headers.get("retry-after"),
                    request_url=url,
                    resource_type="fetch" if kind != "script" else "script",
                )
            response.raise_for_status()
            if response.is_redirect:
                raise ValueError("Unexpected LoLTV resource redirect")
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > self.settings.catalog_max_page_bytes:
                    raise ValueError("LoLTV resource exceeds the size limit")
            if kind == "feed" and "application/json" not in response.headers.get(
                "content-type", ""
            ):
                raise ValueError("LoLTV feed did not return JSON")
            metadata: dict[str, object] = {
                "url": url,
                "kind": kind,
                "status": response.status_code,
                "bytes": len(raw),
                "durationMs": round((time.monotonic() - started) * 1000),
                "retrievedAt": datetime.now(UTC).isoformat(),
                "cacheAge": response.headers.get("age"),
            }
            if kind != "session":
                digest, path = store_bytes(
                    self.settings.artifact_dir,
                    "loltv-resources",
                    gzip.compress(bytes(raw), mtime=0),
                    "json.gz" if kind == "feed" else "js.gz",
                )
                metadata.update(
                    {
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "artifactSha256": digest,
                        "path": path,
                    }
                )
            cast(list[object], self.metrics.setdefault("resources", [])).append(metadata)
        self.policy.page_completed()
        return bytes(raw)

    def discover(self, client: httpx.Client, html: str) -> str:
        scripts = list(
            dict.fromkeys(
                urljoin(ROOT_URL, str(s.get("src")))
                for s in BeautifulSoup(html, "html.parser").select("script[src]")
                if str(s.get("src", "")).startswith("/_next/static/")
            )
        )
        cached = self.state.get("feedAction")
        if (
            isinstance(cached, dict)
            and cached.get("url") in scripts
            and isinstance(cached.get("id"), str)
        ):
            return str(cached["id"])
        # The match component is among the final page-specific chunks, after shared bundles.
        for url in reversed(scripts[-16:]):
            script = self.request(client, url, "script").decode("utf-8")
            found = ACTION.search(script)
            if found:
                self.state["feedAction"] = {"url": url, "id": found[1]}
                self.policy.checkpoint(self.state)
                return found[1]
        raise ValueError("LoLTV public feed session action not found in linked scripts")

    def enrich(
        self,
        client: httpx.Client,
        html: str,
        event: LoltvEvent,
        acquired: set[str],
        publish: Callable[[LoltvEvent], None] | None = None,
    ) -> LoltvEvent:
        games = event.payload.get("sourceGames")
        rendered = event.payload.get("rendered")
        maps = rendered.get("maps", []) if isinstance(rendered, dict) else []
        complete = {
            m.get("sourceGameId")
            for m in maps
            if isinstance(m, dict)
            and m.get("status") == "finished"
            and all(len(s.get("players", [])) == 5 for s in m.get("sides", []))
            and len(m.get("sides", [])) == 2
        }
        pending = (
            [
                g
                for g in games
                if isinstance(g, dict)
                and g.get("livefeed") is True
                and g.get("state") in {"STARTED", "PAUSED", "COMPLETED"}
                and g.get("id") not in acquired | complete
            ]
            if isinstance(games, list)
            else []
        )
        if not pending:
            return event
        # Read the current card before historical complements. An incomplete old
        # feed must not prevent publishing a valid live frame from another card.
        pending.sort(key=lambda game: game.get("state") == "COMPLETED")
        action = self.discover(client, html)
        if self.sessions.restore(client, event.source_id, action):
            self.metrics["reusedSessions"] = (
                int(cast(int, self.metrics.get("reusedSessions", 0))) + 1
            )
        else:
            self.request(client, event.url, "session", action=action, match_id=event.source_id)
            self.sessions.remember(client, event.source_id, action)
        for game in pending:
            game_id = str(game["id"])
            url = "https://feed.loltv.gg/feed/" + game_id
            try:
                raw = self.request(client, url, "feed")
                data = json.loads(raw)
                event = merge_feed(event, game_id, data)
                resources = cast(list[dict[str, object]], self.metrics["resources"])
                resources[-1].update(
                    sourceState=data.get("state"),
                    sourceObservedAt=data["timestamp"],
                    sourceLagSeconds=round(
                        max(0, time.time() - timestamp(data["timestamp"]).timestamp())
                    ),
                )
            except (ValueError, httpx.HTTPError) as error:
                cast(list[object], self.metrics.setdefault("errors", [])).append(
                    {"url": url, "error": type(error).__name__, "message": str(error)[:250]}
                )
                if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 401:
                    self.sessions.entries.pop(event.source_id, None)
                    break  # Renew only on the next due read, never retry the action here.
                continue
            if callable(publish):
                publish(event)
        return event
