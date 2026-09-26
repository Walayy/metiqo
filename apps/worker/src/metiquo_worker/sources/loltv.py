"""LoLTV public HTML parser. No JavaScript evaluation or direct data API calls."""

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import cast
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup
from pydantic import JsonValue

from metiquo_worker.loltv_diagnostics import LoltvSourceError, record_issue
from metiquo_worker.matching import normalize_name
from metiquo_worker.sources.lol import array, obj, objects, text

SOURCE = "loltv"
ROOT_URL = "https://loltv.gg"
CDN_URL = "https://cdn.loltv.gg"
STATES = {
    "UNSTARTED": "scheduled",
    "STARTED": "live",
    "PAUSED": "live",
    "COMPLETED": "finished",
    "CANCELLED": "cancelled",
    "CANCELED": "cancelled",
    "POSTPONED": "postponed",
    "WALKOVER": "walkover",
}
ROLES = {"TOP": "TOP", "JUNGLE": "JGL", "MID": "MID", "BOTTOM": "BOT", "SUPPORT": "SUP"}


@dataclass(frozen=True)
class LoltvEvent:
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
    best_of: int | None
    status: str
    home_score: int | None
    away_score: int | None
    payload: dict[str, object]


def integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("LoLTV timestamp is missing")
    parsed = datetime.fromisoformat(value.removeprefix("$D").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("LoLTV timestamp has no timezone")
    return parsed


def image_url(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    url = urljoin(CDN_URL, value)
    parsed = urlsplit(url)
    if parsed.hostname == "cdn.loltv.gg" and parsed.path == "/image-resizing":
        nested = parse_qs(parsed.query).get("image", [])
        if nested:
            return image_url(nested[0])
    if parsed.hostname not in {
        "cdn.loltv.gg",
        "static.lolesports.com",
        "ddragon.leagueoflegends.com",
    }:
        return ""
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return ""
    return url.replace("http://", "https://", 1)


def flight_records(html: str) -> dict[str, JsonValue]:
    """Decode JSON-only React Flight records, including byte-sized text records.

    Text records need not end with a newline. Chunk boundaries may split JSON;
    joining the embedded transport strings first is necessary. Never eval JS.
    """
    parts: list[str] = []
    decoder = json.JSONDecoder()
    for script in BeautifulSoup(html, "html.parser").find_all("script"):
        source = script.get_text()
        for match in re.finditer(r"self\.__next_f\.push\(", source):
            value, _ = decoder.raw_decode(source[match.end() :])
            if isinstance(value, list) and len(value) == 2 and value[0] == 1:
                if isinstance(value[1], str):
                    parts.append(value[1])
    data = "".join(parts).encode("utf-8")
    records: dict[str, JsonValue] = {}
    position = 0
    while position < len(data):
        record_match = re.match(rb"([0-9a-f]*):", data[position:])
        if not record_match:
            raise ValueError("Unrecognized LoLTV HTML transport record")
        key = record_match.group(1).decode()
        position += record_match.end()
        if data[position : position + 1] == b"T":
            comma = data.index(b",", position)
            length = int(data[position + 1 : comma], 16)
            end = comma + 1 + length
            if end > len(data):
                raise ValueError("Truncated LoLTV HTML transport")
            records[key] = data[comma + 1 : end].decode("utf-8")
            position = end
        else:
            end = data.find(b"\n", position)
            if end == -1:
                end = len(data)
            value = data[position:end]
            if value[:1] in {b"[", b"{", b'"'} or value in {b"null", b"true", b"false"}:
                records[key] = cast(JsonValue, json.loads(value))
            position = end + 1
    if not records:
        raise ValueError("LoLTV HTML contains no recognized source data")
    return records


def page_objects(html: str) -> list[dict[str, JsonValue]]:
    return objects(cast(JsonValue, flight_records(html)))


def listing(
    html: str, url: str, *, metrics: dict[str, object] | None = None
) -> tuple[list[LoltvEvent], list[str], list[datetime]]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    if main is None:
        raise ValueError("LoLTV listing has no main content")
    slugs = {
        str(a.get("href", "")).removeprefix("/match/") for a in main.select('a[href^="/match/"]')
    }
    events: dict[str, LoltvEvent] = {}
    dates: list[datetime] = []
    rows = page_objects(html)
    for row in rows:
        if row.get("slug") not in slugs or not row.get("id") or "date" not in row:
            continue
        starts_at = timestamp(row["date"])
        dates.append(starts_at)
        home, away = obj(row.get("team1")), obj(row.get("team2"))
        # TBD slots are not team identities; retain them in the page evidence only.
        if not home.get("id") or not away.get("id") or home["id"] == away["id"]:
            continue
        stage = obj(row.get("stage"))
        tournament = obj(stage.get("tournament"))
        competition = text(tournament.get("name"))
        if not competition:
            continue
        state = STATES.get(text(row.get("state")))
        if state is None:
            error = LoltvSourceError("loltv_unknown_state", "Unknown LoLTV match state")
            if metrics is None:
                raise error
            record_issue(metrics, url, error, event_id=text(row["id"]))
            continue
        if row.get("postponed") is True:
            state = "postponed"
        competition_slug = re.sub(r"[^a-z0-9]+", "-", normalize_name(competition)).strip("-")
        raw = {
            k: v
            for k, v in row.items()
            if k
            in {
                "id",
                "slug",
                "date",
                "team1",
                "team2",
                "team1_name",
                "team2_name",
                "team1_score",
                "team2_score",
                "best_of",
                "state",
                "winner_side",
                "postponed",
                "name",
                "group",
                "stage",
            }
        }
        event = LoltvEvent(
            source_id=text(row["id"]),
            url=urljoin(ROOT_URL, "/match/" + text(row["slug"])),
            home_name=text(home.get("name")),
            away_name=text(away.get("name")),
            competition=competition,
            competition_source_id=text(tournament.get("id")) or competition_slug,
            competition_slug=competition_slug,
            home_source_id=text(home["id"]),
            away_source_id=text(away["id"]),
            home_image=image_url(home.get("image")),
            away_image=image_url(away.get("image")),
            competition_image=image_url(tournament.get("image")),
            starts_at=starts_at,
            best_of=integer(row.get("best_of")),
            status=state,
            home_score=integer(row.get("team1_score")) if state != "scheduled" else None,
            away_score=integer(row.get("team2_score")) if state != "scheduled" else None,
            payload={
                "sourceMatch": raw,
                "listingUrl": url,
                "game": "lol",
                "rendered": {"maps": []},
            },
        )
        events[event.source_id] = event
    if not dates and (slugs or not any(row.get("matches") == [] for row in rows)):
        raise ValueError("LoLTV listing identities could not be decoded")
    paths = sorted(
        {
            urljoin(ROOT_URL, str(a.get("href")))
            for a in soup.select("nav a[href]")
            if re.fullmatch(r"/matches/(?:results/)?all/\d+", str(a.get("href")))
        }
    )
    return list(events.values()), paths, dates


def _position(team: dict[str, JsonValue], event: LoltvEvent) -> str | None:
    identity = obj(team.get("team"))
    name = text(identity.get("name")) or text(team.get("team_name"))
    matches = [
        position
        for position, expected in (("home", event.home_name), ("away", event.away_name))
        if normalize_name(name) in team_names(event, position)
    ]
    return matches[0] if len(matches) == 1 else None


def team_names(event: LoltvEvent, position: str) -> set[str]:
    names = {normalize_name(event.home_name if position == "home" else event.away_name)}
    raw = event.payload.get("sourceMatch")
    if isinstance(raw, dict):
        alias = raw.get("team1_name" if position == "home" else "team2_name")
        if isinstance(alias, str) and alias.casefold() != "tbd":
            names.add(normalize_name(alias))
    return names


def source_maps(games: list[JsonValue], event: LoltvEvent) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for value in games:
        game = obj(value)
        number = integer(game.get("number"))
        state = STATES.get(text(game.get("state")))
        if not number or number > 5 or state not in {"live", "finished"}:
            continue
        sides: list[dict[str, object]] = []
        bans: list[dict[str, object]] = []
        winners: list[str] = []
        for raw in array(game.get("teams")):
            side = obj(raw)
            position = _position(side, event)
            if position is None:
                continue
            players: list[dict[str, object]] = []
            for raw_player in array(side.get("players")):
                player = obj(raw_player)
                role = ROLES.get(text(player.get("role")))
                if (
                    role is None
                    or not text(player.get("summoner_name"))
                    or any(
                        integer(player.get(key)) is None
                        for key in ("kills", "deaths", "assists", "creep_score")
                    )
                ):
                    continue
                players.append(
                    {
                        "id": "loltv:player:"
                        + (text(player.get("id")) or text(player["summoner_name"])),
                        "name": player["summoner_name"],
                        "role": role,
                        "champion": text(player.get("champion_id")) or None,
                        "championImage": "",
                        **{
                            key: integer(player.get(source))
                            for key, source in (
                                ("level", "level"),
                                ("kills", "kills"),
                                ("deaths", "deaths"),
                                ("assists", "assists"),
                                ("cs", "creep_score"),
                                ("gold", "total_gold_earned"),
                            )
                        },
                    }
                )
            # Empty livefeed teams contain default zeros, not observed objectives.
            populated = len(players) == 5 and len({p["role"] for p in players}) == 5
            sides.append(
                {
                    "position": position,
                    "side": text(side.get("side")).casefold()
                    if populated and side.get("side") in {"BLUE", "RED"}
                    else None,
                    "players": players if populated else [],
                    **{
                        key: integer(side.get(source)) if populated else None
                        for key, source in (
                            ("towers", "towers"),
                            ("dragons", "dragons"),
                            ("barons", "barons"),
                            ("heralds", "herald"),
                            ("grubs", "horde"),
                            ("inhibitors", "inhibitors"),
                        )
                    },
                }
            )
            for raw_ban in array(side.get("bans")):
                ban = obj(raw_ban)
                champion = text(ban.get("champion_id"))
                if champion:
                    bans.append({"teamId": position, "champion": champion, "championImage": ""})
            if side.get("win") is True:
                winners.append(position)
        if len(sides) != 2 or len({s["position"] for s in sides}) != 2:
            continue
        if state == "finished" and len(winners) != 1:
            continue
        result.append(
            {
                "sourceGameId": game.get("id"),
                "number": number,
                "status": state,
                "durationSeconds": integer(game.get("duration")) or None,
                "winner": winners[0] if state == "finished" and len(winners) == 1 else None,
                "bans": bans,
                "sides": sides,
                "provenance": "html-embedded",
            }
        )
    return result


def detail(html: str, event: LoltvEvent, *, require_score: bool = False) -> LoltvEvent:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    header = main.find("section") if main else None
    if header is None:
        raise ValueError("LoLTV match header missing")
    rows = page_objects(html)
    candidates = [row for row in rows if row.get("matchId") == event.source_id and "games" in row]
    if len(candidates) != 1:
        raise LoltvSourceError(
            "loltv_detail_missing", "LoLTV HTML does not identify the requested match"
        )
    data = candidates[0]
    names = [str(a.get("aria-label")) for a in header.select('a[href^="/team/"][aria-label]')]
    if len(names) != 2 or any(
        normalize_name(name) not in team_names(event, position)
        for name, position in zip(names, ("home", "away"), strict=True)
    ):
        raise ValueError("LoLTV detail teams disagree with the listing")
    header_text = header.get_text(" ", strip=True)
    scores = [
        found
        for span in header.select("span")
        if (found := re.fullmatch(r"(\d+)\s*:\s*(\d+)", span.get_text(" ", strip=True)))
    ]
    score = scores[0] if len(scores) == 1 else None
    if require_score and score is None:
        raise ValueError("LoLTV detail has no verified series score")
    best = re.search(r"\bBO\s*(\d+)\b", header_text)
    state = STATES.get(text(data.get("state")))
    if state is None:
        raise ValueError("Unknown LoLTV detail state")
    maps = source_maps(array(data.get("games")), event)
    # Keep relevant original game records, not the unrelated item/rune dictionaries.
    raw_games = [
        {k: v for k, v in obj(g).items() if k != "events"} for g in array(data.get("games"))
    ]
    return replace(
        event,
        status=state,
        starts_at=timestamp(data.get("matchDate")),
        best_of=int(best[1]) if best else event.best_of,
        home_score=int(score[1]) if score else event.home_score,
        away_score=int(score[2]) if score else event.away_score,
        payload={
            **event.payload,
            "sourceGames": raw_games,
            "rendered": {"maps": maps},
            "patch": text(data.get("patch_version")) or None,
        },
    )
