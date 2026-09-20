"""Project complete Oracle's Elixir games into match detail snapshots.

Oracle's Elixir is a historical source: it is authoritative for completed maps
when a complete row set exists, but it must never replace a newer live
SofaScore snapshot with an empty or partial payload.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from metiquo_core.matches import completed_series_summary
from metiquo_core.models import (
    Dataset,
    DatasetVersion,
    EsportMatch,
    MatchSnapshot,
    MatchSourceLink,
    OracleRow,
    Team,
)
from sqlalchemy import Engine, and_, or_, select
from sqlalchemy.orm import Session

from metiquo_worker.matching import name_score, normalize_name

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


def _timestamp(payload: dict[str, str]) -> datetime | None:
    value = _value(payload, "date")
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def _team_name(row: OracleRow) -> str | None:
    return _value(row.payload, "teamname")


def _team_score(name: str, team: Team) -> float:
    return name_score(
        name,
        str(team.data.get("name", "")),
        str(team.data.get("code", "")),
        str(team.data.get("slug", "")),
    )


def _best_name(rows: list[OracleRow], team: Team) -> tuple[str, float] | None:
    names = sorted({value for row in rows if (value := _team_name(row)) is not None})
    if not names:
        return None
    scored = sorted(((_team_score(name, team), name) for name in names), reverse=True)
    score, name = scored[0]
    return (name, score) if score >= 0.57 else None


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
                    "gold": _required(row.payload, "totalgold"),
                }
            )
        bans: list[dict[str, object]] = []
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
                "towers": _required(team_row.payload, "towers"),
                "dragons": _required(team_row.payload, "dragons"),
                "barons": _required(team_row.payload, "barons"),
                "heralds": _required(team_row.payload, "heralds"),
                "grubs": _required(team_row.payload, "void_grubs"),
                "inhibitors": _required(team_row.payload, "inhibitors"),
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
    result = _map_for_game(game_id, rows, match, teams)
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


def sync_oracle_match_details(
    engine: Engine,
    observed_at: datetime | None = None,
    match_ids: set[UUID] | None = None,
) -> dict[str, object]:
    """Publish complete Oracle maps for matches already known by Metiquo."""
    now = observed_at or datetime.now(UTC)
    with Session(engine) as session, session.begin():
        match_query = select(EsportMatch)
        if match_ids:
            match_query = match_query.where(EsportMatch.id.in_(match_ids))
        matches = list(session.scalars(match_query).all())
        if not matches:
            return {"matches": 0, "published": 0, "games": 0}
        teams = {team.id: team for team in session.scalars(select(Team)).all()}
        ranges = [
            and_(
                OracleRow.payload["date"].astext
                >= (match.starts_at - MATCH_WINDOW).strftime("%Y-%m-%d %H:%M:%S"),
                OracleRow.payload["date"].astext
                <= (match.starts_at + MATCH_WINDOW).strftime("%Y-%m-%d %H:%M:%S"),
            )
            for match in matches
        ]
        rows = list(
            session.scalars(
                select(OracleRow)
                .join(DatasetVersion, DatasetVersion.id == OracleRow.version_id)
                .join(Dataset, Dataset.active_version_id == DatasetVersion.id)
                .where(Dataset.source == SOURCE, or_(*ranges))
            ).all()
        )
        groups: dict[str, list[OracleRow]] = defaultdict(list)
        for row in rows:
            groups[row.game_id].append(row)
        published = 0
        games = 0
        for match in matches:
            candidates: list[tuple[float, str, list[OracleRow]]] = []
            home = teams.get(match.home_id)
            away = teams.get(match.away_id)
            if home is None or away is None:
                continue
            for game_id, game_rows in groups.items():
                dates = [timestamp for row in game_rows if (timestamp := _timestamp(row.payload))]
                if not dates:
                    continue
                start = min(dates)
                delta = abs((start - match.starts_at).total_seconds())
                if delta > MATCH_WINDOW.total_seconds():
                    continue
                home_score = max((_team_score(name, home) for name in _names(game_rows)), default=0)
                away_score = max((_team_score(name, away) for name in _names(game_rows)), default=0)
                if home_score < 0.57 or away_score < 0.57:
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
            for _, game_id, game_rows in sorted(candidates, key=lambda item: item[1]):
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
            summary = completed_series_summary(maps, match.home_id, match.away_id)
            if summary is None:
                logger.info(
                    "Oracle history is incomplete for match %s; keeping the live snapshot",
                    match.id,
                )
                continue
            format_name, home_wins, away_wins = summary
            # Oracle contains the completed series and is authoritative when its
            # maps form a coherent result. This also repairs a stale SofaScore
            # best-of value (for example BO5 with a completed 2-0 series).
            match.format = format_name
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
            }
            source_id = _source_id(match.id, game_ids)
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
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
            else:
                link.source_id = source_id
                link.source_url = source_url
                link.source_names = {"matchId": str(match.id), "games": game_ids}
                link.last_seen_at = now
            if (
                session.scalar(
                    select(MatchSnapshot.id).where(
                        MatchSnapshot.match_id == match.id,
                        MatchSnapshot.sha256 == _fingerprint(payload),
                    )
                )
                is None
            ):
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
        return {"matches": len(matches), "published": published, "games": games}


def _names(rows: list[OracleRow]) -> set[str]:
    return {name for row in rows if (name := _team_name(row)) is not None}
