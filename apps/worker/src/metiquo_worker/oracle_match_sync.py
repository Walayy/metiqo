"""Project complete Oracle's Elixir games into match detail snapshots.

Oracle's Elixir is a historical source: it is authoritative for completed maps
when a complete row set exists, but it must never replace a newer live
LoLTV snapshot with an empty or partial payload.
"""

from __future__ import annotations

import hashlib
import json
import logging
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from metiquo_core.matches import completed_series_summary
from metiquo_core.models import (
    Dataset,
    DatasetVersion,
    EsportMatch,
    League,
    MatchSnapshot,
    MatchSourceLink,
    OracleRow,
    Team,
)
from sqlalchemy import Engine, and_, func, or_, select
from sqlalchemy.orm import Session

from metiquo_worker.matching import normalize_name, resolve_team

SOURCE = "oracles-elixir"
SOURCE_URL = "https://oracleselixir.com/tools/downloads"
MATCH_WINDOW = timedelta(hours=36)
TEAM_PARTICIPANTS = {"100", "200"}
ROLE_MAP = {
    "top": "TOP",
    "jng": "JGL",
    "jg": "JGL",
    "jungle": "JGL",
    "mid": "MID",
    "bot": "BOT",
    "adc": "BOT",
    "sup": "SUP",
    "support": "SUP",
}
POSITION_ORDER = {"TOP": 0, "JGL": 1, "MID": 2, "BOT": 3, "SUP": 4}
logger = logging.getLogger(__name__)


def _value(payload: dict[str, str], key: str) -> str | None:
    raw = payload.get(key)
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value if value and value.casefold() not in {"na", "n/a", "nan", "null"} else None


def _integer(payload: dict[str, str], key: str) -> int | None:
    value = _value(payload, key)
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return int(number) if number.is_integer() and number >= 0 else None


def _timestamp(payload: dict[str, str], source_timezone: str | None = None) -> datetime | None:
    value = _value(payload, "date")
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        if source_timezone is None:
            return None
        parsed = parsed.replace(tzinfo=ZoneInfo(source_timezone))
    return parsed.astimezone(UTC)


def _team_name(row: OracleRow) -> str | None:
    return _value(row.payload, "teamname")


def _team_score(name: str, team: Team) -> float:
    resolved = resolve_team(name, [team])
    return resolved.score if resolved is not None else 0.0


def _best_name(rows: list[OracleRow], team: Team) -> tuple[str, float] | None:
    names = sorted({value for row in rows if (value := _team_name(row)) is not None})
    if not names:
        return None
    ids = team.data.get("sourceIds")
    provider_ids = ids.get(SOURCE) if isinstance(ids, dict) else None
    sourced_names = {
        name
        for row in rows
        if (name := _team_name(row)) is not None
        and isinstance(provider_ids, list)
        and _value(row.payload, "teamid") in provider_ids
    }
    scored = sorted(
        ((1.0 if name in sourced_names else _team_score(name, team), name) for name in names),
        reverse=True,
    )
    score, name = scored[0]
    if len(scored) > 1 and score - scored[1][0] < 0.08:
        return None
    return (name, score) if score >= 0.9 else None


def _side(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_name(value)
    if normalized == "blue":
        return "blue"
    if normalized == "red":
        return "red"
    return None


def _required(payload: dict[str, str], key: str) -> int:
    value = _integer(payload, key)
    if value is None:
        raise ValueError(f"Oracle field {key} is incomplete")
    return value


def _map_for_game(
    game_id: str,
    rows: list[OracleRow],
    match: EsportMatch,
    teams: dict[str, Team],
) -> tuple[dict[str, object], str | None] | None:
    home_team = teams.get(match.home_id)
    away_team = teams.get(match.away_id)
    if home_team is None or away_team is None:
        return None
    home_name = _best_name(rows, home_team)
    away_name = _best_name(rows, away_team)
    if home_name is None or away_name is None or home_name[0] == away_name[0]:
        return None
    selected = {"home": home_name[0], "away": away_name[0]}
    sides: list[dict[str, object]] = []
    map_bans: list[dict[str, object]] = []
    patches: list[str] = []
    winner_id: str | None = None
    map_number = _integer(rows[0].payload, "game")
    if map_number is None or not 1 <= map_number <= 5:
        return None
    duration = _integer(rows[0].payload, "gamelength")
    if duration is None:
        return None
    for label, team_id in (("home", match.home_id), ("away", match.away_id)):
        team_name = selected[label]
        team_rows = [row for row in rows if _team_name(row) == team_name]
        team_row = next(
            (
                row
                for row in team_rows
                if row.participant_id in TEAM_PARTICIPANTS
                or _value(row.payload, "position") == "team"
            ),
            None,
        )
        player_rows = [
            row
            for row in team_rows
            if row.participant_id not in TEAM_PARTICIPANTS
            and _value(row.payload, "position") != "team"
        ]
        if team_row is None or len(player_rows) != 5:
            return None
        side = _side(_value(team_row.payload, "side")) or _side(
            _value(player_rows[0].payload, "side")
        )
        if side is None or any(
            _side(_value(row.payload, "side")) not in {side, None} for row in player_rows
        ):
            return None
        result = _integer(team_row.payload, "result")
        if result not in {0, 1}:
            return None
        if result == 1:
            if winner_id is not None:
                return None
            winner_id = team_id
        players: list[dict[str, object]] = []
        for row in sorted(
            player_rows,
            key=lambda item: POSITION_ORDER.get(
                ROLE_MAP.get((_value(item.payload, "position") or "").casefold(), ""), 99
            ),
        ):
            role = ROLE_MAP.get((_value(row.payload, "position") or "").casefold())
            player_name = _value(row.payload, "playername")
            if role is None or player_name is None:
                return None
            players.append(
                {
                    "id": _value(row.payload, "playerid") or row.participant_id,
                    "name": player_name,
                    "role": role,
                    "champion": _value(row.payload, "champion"),
                    "championImage": "",
                    "level": None,
                    "kills": _required(row.payload, "kills"),
                    "deaths": _required(row.payload, "deaths"),
                    "assists": _required(row.payload, "assists"),
                    "cs": _required(row.payload, "total cs"),
                    "gold": _integer(row.payload, "totalgold"),
                }
            )
        bans: list[dict[str, object]] = []
        if (
            len({player["role"] for player in players}) != 5
            or len({player["id"] for player in players}) != 5
        ):
            return None
        for index in range(1, 6):
            champion = _value(team_row.payload, f"ban{index}")
            if champion is not None:
                bans.append({"teamId": team_id, "champion": champion, "championImage": ""})
        map_bans.extend(bans)
        patch = _value(team_row.payload, "patch")
        if patch is not None:
            patches.append(patch)
        sides.append(
            {
                "teamId": team_id,
                "side": side,
                "towers": _integer(team_row.payload, "towers"),
                "dragons": _integer(team_row.payload, "dragons"),
                "barons": _integer(team_row.payload, "barons"),
                "heralds": _integer(team_row.payload, "heralds"),
                "grubs": _integer(team_row.payload, "void_grubs"),
                "inhibitors": _integer(team_row.payload, "inhibitors"),
                "players": players,
            }
        )
    if len(sides) != 2 or len({side["side"] for side in sides}) != 2 or winner_id is None:
        return None
    return (
        {
            "number": map_number,
            "status": "finished",
            "durationSeconds": duration,
            "winnerId": winner_id,
            "bans": map_bans,
            "sides": sides,
        },
        patches[0] if patches else None,
    )


def _build_map(
    game_id: str,
    rows: list[OracleRow],
    match: EsportMatch,
    teams: dict[str, Team],
) -> tuple[dict[str, object], str | None] | None:
    try:
        result = _map_for_game(game_id, rows, match, teams)
    except ValueError:
        # An incomplete game must not roll back every other projected match.
        return None
    if result is None:
        return None
    return result


def _fingerprint(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _source_id(match_id: UUID, game_ids: list[str]) -> str:
    digest = hashlib.sha256("|".join(game_ids).encode()).hexdigest()[:16]
    return f"oracle:{match_id}:{digest}"


def _map_number(map_data: dict[str, object]) -> int:
    value = map_data.get("number")
    return value if isinstance(value, int) else 0


def _league_matches(name: str, league: League, leagues: dict[str, League]) -> bool:
    """Use sourced names, slugs and explicit aliases; never a similar league."""
    candidates = [league]
    parent_id = league.data.get("parentLeagueId")
    if isinstance(parent_id, str) and parent_id in leagues:
        candidates.append(leagues[parent_id])
    from metiquo_worker.loltv_publication import _competition_base_name

    incoming = normalize_name(name)
    for candidate in candidates:
        aliases = candidate.data.get("aliases")
        names = [str(candidate.data.get("name", "")), str(candidate.data.get("slug", ""))]
        if isinstance(aliases, list):
            names.extend(value for value in aliases if isinstance(value, str))
        if incoming and any(incoming == _competition_base_name(value) for value in names):
            return True
    return False


def _date_ranges(matches: list[EsportMatch]) -> list[tuple[date, date]]:
    """Merge overlapping SQL windows before loading the large raw row store.

    One extra calendar day covers source offsets; actual ownership still
    requires a verified timestamp and MATCH_WINDOW below.
    """
    ranges: list[tuple[date, date]] = []
    padding = MATCH_WINDOW + timedelta(days=1)
    for match in sorted(matches, key=lambda item: item.starts_at):
        first, last = (match.starts_at - padding).date(), (match.starts_at + padding).date()
        if ranges and first <= ranges[-1][1] + timedelta(days=1):
            ranges[-1] = ranges[-1][0], max(last, ranges[-1][1])
        else:
            ranges.append((first, last))
    return ranges


def game_signature(game: object) -> tuple[object, ...] | None:
    """An exact completed-game identity, independent of an unverified timezone."""
    if not isinstance(game, dict) or game.get("status") != "finished":
        return None
    sides = game.get("sides")
    if not isinstance(sides, list) or len(sides) != 2 or not game.get("winnerId"):
        return None
    players = []
    for side in sides:
        if not isinstance(side, dict) or not isinstance(side.get("players"), list):
            return None
        if len(side["players"]) != 5 or not side.get("teamId"):
            return None
        for player in side["players"]:
            if not isinstance(player, dict) or not player.get("champion"):
                return None
            if any(not isinstance(player.get(key), int) for key in ("kills", "deaths", "assists")):
                return None
            players.append(
                (
                    str(side["teamId"]),
                    str(player.get("role")),
                    # Riot IDs omit spaces/punctuation (JarvanIV, Kaisa).
                    # MonkeyKing is Riot's ID for the published name Wukong.
                    "".join(normalize_name(str(player["champion"])).split()).replace(
                        "monkeyking", "wukong"
                    ),
                    player["kills"],
                    player["deaths"],
                    player["assists"],
                )
            )
    if len({(player[0], player[1]) for player in players}) != 10:
        return None
    return (game.get("number"), game["winnerId"], tuple(sorted(players)))


def sync_oracle_match_details(
    engine: Engine,
    observed_at: datetime | None = None,
    match_ids: set[UUID] | None = None,
    source_timezone: str | None = None,
) -> dict[str, object]:
    """Publish complete Oracle maps for matches already known by Metiquo."""
    now = observed_at or datetime.now(UTC)
    with Session(engine) as session, session.begin():
        if not session.scalar(select(func.pg_try_advisory_xact_lock(7_346_810_208))):
            return {"deferred": "oracle-projection-busy", "published": 0, "games": 0}
        known_matches = list(
            session.scalars(select(EsportMatch).order_by(EsportMatch.starts_at)).all()
        )
        known_starts = [match.starts_at for match in known_matches]
        matches = [match for match in known_matches if match_ids is None or match.id in match_ids]
        if not matches:
            return {"matches": 0, "published": 0, "games": 0}
        teams = {team.id: team for team in session.scalars(select(Team)).all()}
        leagues = {league.id: league for league in session.scalars(select(League)).all()}
        date_ranges = _date_ranges(matches)
        version_times = {
            version_id: checked_at
            for version_id, checked_at in session.execute(
                select(DatasetVersion.id, Dataset.checked_at)
                .join(Dataset, Dataset.active_version_id == DatasetVersion.id)
                .where(
                    Dataset.source == SOURCE,
                    Dataset.file_year >= date_ranges[0][0].year,
                    Dataset.file_year <= date_ranges[-1][1].year,
                )
            ).all()
        }
        ranges = [
            and_(
                func.left(OracleRow.payload["date"].astext, 10) >= first.isoformat(),
                func.left(OracleRow.payload["date"].astext, 10) <= last.isoformat(),
            )
            for first, last in date_ranges
        ]
        rows = list(
            session.scalars(
                select(OracleRow).where(OracleRow.version_id.in_(version_times), or_(*ranges))
            ).all()
        )
        groups: dict[str, list[OracleRow]] = defaultdict(list)
        for row in rows:
            groups[row.game_id].append(row)
        # Resolve each game once across all plausible fixtures, never once per
        # fixture: rematches must not receive the same historical game.
        owners: dict[str, UUID] = {}
        ownership_basis: dict[str, str] = {}
        signatures: dict[UUID, set[tuple[object, ...]]] = defaultdict(set)
        latest_maps: dict[tuple[UUID, int], object] = {}
        for observation in session.scalars(
            select(MatchSnapshot)
            .where(MatchSnapshot.source == "loltv")
            .order_by(MatchSnapshot.observed_at, MatchSnapshot.id)
        ):
            observed_maps = observation.payload.get("maps")
            if isinstance(observed_maps, list):
                for game in observed_maps:
                    if isinstance(game, dict) and isinstance(game.get("number"), int):
                        if game_signature(game) is not None:
                            latest_maps[(observation.match_id, game["number"])] = game
        for (match_id, _), game in latest_maps.items():
            if (signature := game_signature(game)) is not None:
                signatures[match_id].add(signature)
        skipped_timezone = 0
        ambiguous_games = 0
        for game_id, game_rows in groups.items():
            dates = [at for row in game_rows if (at := _timestamp(row.payload, source_timezone))]
            if not dates:
                # A naive timestamp never becomes UTC by assumption. Ten exact
                # champions, roles, K/D/A, team identities, number and winner can
                # independently prove ownership; more than one match rejects it.
                exact = []
                for candidate in known_matches:
                    if not signatures.get(candidate.id):
                        continue
                    league = leagues.get(candidate.league_id)
                    if league is None or not any(
                        _league_matches(value, league, leagues)
                        for row in game_rows
                        if (value := _value(row.payload, "league"))
                    ):
                        continue
                    built = _build_map(game_id, game_rows, candidate, teams)
                    if built and game_signature(built[0]) in signatures[candidate.id]:
                        exact.append(candidate.id)
                if len(exact) == 1:
                    owners[game_id] = exact[0]
                    ownership_basis[game_id] = "exact-game-statistics"
                elif exact:
                    ambiguous_games += 1
                else:
                    skipped_timezone += 1
                continue
            start = min(dates)
            ranked: list[tuple[float, UUID]] = []
            for candidate in known_matches[
                bisect_left(known_starts, start - MATCH_WINDOW) : bisect_right(
                    known_starts, start + MATCH_WINDOW
                )
            ]:
                league = leagues.get(candidate.league_id)
                source_leagues = {_value(row.payload, "league") for row in game_rows}
                if league is None or not any(
                    _league_matches(value, league, leagues) for value in source_leagues if value
                ):
                    continue
                home, away = teams.get(candidate.home_id), teams.get(candidate.away_id)
                if home is None or away is None:
                    continue
                names = (_best_name(game_rows, home), _best_name(game_rows, away))
                if names[0] is None or names[1] is None or names[0][0] == names[1][0]:
                    continue
                delta = abs((start - candidate.starts_at).total_seconds())
                if delta <= MATCH_WINDOW.total_seconds():
                    ranked.append((delta, candidate.id))
            ranked.sort(key=lambda item: item[0])
            if ranked and (len(ranked) == 1 or ranked[1][0] - ranked[0][0] >= 6 * 3600):
                owners[game_id] = ranked[0][1]
                ownership_basis[game_id] = "teams-league-verified-time"
            elif ranked:
                ambiguous_games += 1
        published = 0
        games = 0
        for match in matches:
            candidates: list[tuple[float, str, list[OracleRow]]] = []
            home = teams.get(match.home_id)
            away = teams.get(match.away_id)
            if home is None or away is None:
                continue
            for game_id, game_rows in groups.items():
                if owners.get(game_id) != match.id:
                    continue
                dates = [
                    timestamp
                    for row in game_rows
                    if (timestamp := _timestamp(row.payload, source_timezone))
                ]
                exact_stats = ownership_basis.get(game_id) == "exact-game-statistics"
                if not dates and not exact_stats:
                    continue
                delta = abs((min(dates) - match.starts_at).total_seconds()) if dates else 0.0
                if delta > MATCH_WINDOW.total_seconds():
                    continue
                home_name, away_name = _best_name(game_rows, home), _best_name(game_rows, away)
                home_score = home_name[1] if home_name else 0
                away_score = away_name[1] if away_name else 0
                if home_score < 0.9 or away_score < 0.9:
                    continue
                candidates.append(
                    (
                        home_score
                        + away_score
                        + max(0.0, 1 - delta / MATCH_WINDOW.total_seconds()),
                        game_id,
                        game_rows,
                    )
                )
            maps: list[dict[str, object]] = []
            patches: list[str] = []
            game_ids: list[str] = []
            source_url = SOURCE_URL
            duplicate_numbers = {
                number
                for _, _, group in candidates
                if (number := _integer(group[0].payload, "game")) is not None
                and sum(_integer(g[0].payload, "game") == number for _, _, g in candidates) > 1
            }
            for _, game_id, game_rows in sorted(candidates, key=lambda item: item[1]):
                if _integer(game_rows[0].payload, "game") in duplicate_numbers:
                    continue
                built = _build_map(game_id, game_rows, match, teams)
                if built is None:
                    continue
                game_map, patch = built
                if any(existing["number"] == game_map["number"] for existing in maps):
                    continue
                maps.append(game_map)
                game_ids.append(game_id)
                if patch is not None:
                    patches.append(patch)
                for row in game_rows:
                    candidate_url = _value(row.payload, "url")
                    if candidate_url is not None:
                        source_url = candidate_url
                        break
            if not maps:
                continue
            maps.sort(key=_map_number)
            summary = completed_series_summary(maps, match.home_id, match.away_id, match.format)
            if summary is None:
                logger.info(
                    "Oracle history is incomplete for match %s; keeping the live snapshot",
                    match.id,
                )
                continue
            signature = (match.home_id, match.away_id, match.starts_at, match.format)
            session.refresh(match, with_for_update=True)
            if signature != (match.home_id, match.away_id, match.starts_at, match.format):
                continue
            format_name, home_wins, away_wins = summary
            payload: dict[str, object] = {
                "status": "finished",
                "startsAt": match.starts_at.isoformat(),
                "format": format_name,
                "currentScore": {"home": home_wins, "away": away_wins},
                "seriesScore": {"home": home_wins, "away": away_wins},
                "maps": maps,
                "patch": patches[0] if patches else None,
                "stage": None,
                "sourceUrl": source_url,
                "completionBasis": "sourced-format",
                "matchingEvidence": {game_id: ownership_basis[game_id] for game_id in game_ids},
            }
            source_id = _source_id(match.id, game_ids)
            source_checked_at = min(
                version_times[row.version_id] for game_id in game_ids for row in groups[game_id]
            )
            link = session.scalar(
                select(MatchSourceLink).where(
                    MatchSourceLink.provider == SOURCE, MatchSourceLink.match_id == match.id
                )
            )
            if link is None:
                session.add(
                    MatchSourceLink(
                        match_id=match.id,
                        provider=SOURCE,
                        source_id=source_id,
                        source_url=source_url,
                        source_names={"matchId": str(match.id), "games": game_ids},
                        first_seen_at=source_checked_at,
                        last_seen_at=source_checked_at,
                    )
                )
            else:
                link.source_id = source_id
                link.source_url = source_url
                link.source_names = {"matchId": str(match.id), "games": game_ids}
                link.last_seen_at = source_checked_at
            latest_digest = session.scalar(
                select(MatchSnapshot.sha256)
                .where(MatchSnapshot.match_id == match.id, MatchSnapshot.source == SOURCE)
                .order_by(MatchSnapshot.observed_at.desc(), MatchSnapshot.id.desc())
                .limit(1)
            )
            if latest_digest != _fingerprint(payload):
                session.add(
                    MatchSnapshot(
                        match_id=match.id,
                        source=SOURCE,
                        source_id=source_id,
                        source_url=source_url,
                        status="finished",
                        observed_at=now,
                        sha256=_fingerprint(payload),
                        payload=payload,
                    )
                )
                published += 1
            games += len(maps)
        return {
            "matches": len(matches),
            "published": published,
            "games": games,
            "unverifiedDateGames": skipped_timezone,
            "ambiguousGames": ambiguous_games,
            "unmatchedGames": len(groups) - len(owners) - skipped_timezone,
        }


def _names(rows: list[OracleRow]) -> set[str]:
    return {name for row in rows if (name := _team_name(row)) is not None}
