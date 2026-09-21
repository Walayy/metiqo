"""Shared validation for match series assembled from source snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy


def merge_completed_map(
    previous: dict[str, object],
    current: dict[str, object],
) -> dict[str, object]:
    """Fill unavailable historical fields only across the same completed game.

    Current explicit values (including zero) win. Players must match by name
    and role, and conflicting winners/picks never borrow each other's stats.
    """
    result = deepcopy(current)
    if (
        previous.get("status") != "finished"
        or current.get("status") != "finished"
        or previous.get("winnerId") != current.get("winnerId")
        or previous.get("number") != current.get("number")
        or (
            previous.get("sourceGameId")
            and current.get("sourceGameId")
            and previous["sourceGameId"] != current["sourceGameId"]
        )
    ):
        return result
    if result.get("durationSeconds") is None:
        result["durationSeconds"] = previous.get("durationSeconds")
    current_bans, old_bans = unique_bans(current.get("bans")), unique_bans(previous.get("bans"))
    if all(any(_same_ban(current, old) for old in old_bans) for current in current_bans):
        # Keep an older complete draft, but never replace a newly identified
        # portrait with its previously unknown name.
        result["bans"] = unique_bans([*old_bans, *current_bans])
    old_sides, new_sides = previous.get("sides"), result.get("sides")
    if not isinstance(old_sides, list) or not isinstance(new_sides, list):
        return result
    for side in new_sides:
        if not isinstance(side, dict):
            continue
        old = next(
            (
                item
                for item in old_sides
                if isinstance(item, dict) and item.get("teamId") == side.get("teamId")
            ),
            None,
        )
        if old is None:
            continue
        for key in ("side", "towers", "dragons", "barons", "heralds", "grubs", "inhibitors"):
            if side.get(key) is None:
                side[key] = old.get(key)
        players, old_players = side.get("players"), old.get("players")
        if not isinstance(players, list) or not isinstance(old_players, list):
            continue
        if not players and len(old_players) == 5:
            side["players"] = deepcopy(old_players)
            if previous.get("updatedAt"):
                result["updatedAt"] = previous["updatedAt"]
            continue
        for player in players:
            if not isinstance(player, dict):
                continue
            prior = next(
                (
                    item
                    for item in old_players
                    if isinstance(item, dict)
                    and item.get("role") == player.get("role")
                    and str(item.get("name", "")).casefold()
                    == str(player.get("name", "")).casefold()
                ),
                None,
            )
            if prior is None or (
                player.get("champion")
                and prior.get("champion")
                and player["champion"] != prior["champion"]
            ):
                continue
            for key in (
                "champion",
                "championImage",
                "level",
                "kills",
                "deaths",
                "assists",
                "cs",
                "gold",
            ):
                if player.get(key) is None or player.get(key) == "":
                    player[key] = prior.get(key)
    return result


def source_game(payload: object) -> str | None:
    """Read the source's game category without inferring it from the listing URL."""
    if not isinstance(payload, dict):
        return None
    event = payload.get("event")
    tournament = event.get("tournament") if isinstance(event, dict) else None
    category = tournament.get("category") if isinstance(tournament, dict) else None
    slug = category.get("slug") if isinstance(category, dict) else None
    return slug if isinstance(slug, str) else None


def _same_ban(left: dict[str, object], right: dict[str, object]) -> bool:
    if left.get("teamId") != right.get("teamId"):
        return False
    a, b = left.get("champion"), right.get("champion")
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().casefold() == b.strip().casefold()
    image = left.get("championImage")
    return isinstance(image, str) and bool(image) and image == right.get("championImage")


def unique_bans(value: object) -> list[dict[str, object]]:
    """Deduplicate repeated provider entries; reject ambiguous overfull drafts."""
    if not isinstance(value, list):
        return []
    bans: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        team, champion = item.get("teamId"), item.get("champion")
        image = item.get("championImage")
        if not isinstance(team, str) or not team:
            continue
        if not (isinstance(champion, str) and champion.strip()):
            if champion is not None or not isinstance(image, str) or not image:
                continue
        duplicate = next((prior for prior in bans if _same_ban(prior, item)), None)
        if duplicate is None:
            bans.append(item)
        elif duplicate.get("champion") is None and champion is not None:
            bans[bans.index(duplicate)] = item
    if len(bans) > 10 or any(
        sum(ban["teamId"] == item["teamId"] for ban in bans) > 5 for item in bans
    ):
        return []
    return bans


def completed_series_summary(
    maps: object, home_id: str, away_id: str, format_name: str | None
) -> tuple[str, int, int] | None:
    """Validate completion against the independently sourced series format.

    Completed games alone cannot distinguish a BO1 from the first game of a BO5.
    Never infer a smaller format from a partial historical import.
    """

    target = {"BO1": 1, "BO3": 2, "BO5": 3}.get(format_name or "")
    if (
        format_name is None
        or target is None
        or not isinstance(maps, list)
        or not maps
        or home_id == away_id
    ):
        return None
    games: list[tuple[int, str]] = []
    for item in maps:
        if not isinstance(item, Mapping):
            return None
        number = item.get("number")
        status = item.get("status")
        winner_id = item.get("winnerId")
        if (
            isinstance(number, bool)
            or not isinstance(number, int)
            or number < 1
            or number > 5
            or status != "finished"
            or not isinstance(winner_id, str)
            or winner_id not in {home_id, away_id}
        ):
            return None
        games.append((number, winner_id))

    numbers = sorted(number for number, _ in games)
    if numbers != list(range(1, len(games) + 1)):
        return None
    home_wins = away_wins = 0
    for _, winner in sorted(games):
        if max(home_wins, away_wins) >= target:
            return None
        home_wins += winner == home_id
        away_wins += winner == away_id
    if max(home_wins, away_wins) != target:
        return None
    return format_name, home_wins, away_wins
