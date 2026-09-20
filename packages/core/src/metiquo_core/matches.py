"""Shared validation for match series assembled from source snapshots."""

from __future__ import annotations

from collections.abc import Mapping


def completed_series_summary(
    maps: object, home_id: str, away_id: str
) -> tuple[str, int, int] | None:
    """Return the inferred format and score only for a complete finished series.

    Oracle's Elixir exposes completed games rather than a reliable best-of field.
    The number of wins therefore determines the completed format: one win is BO1,
    two wins BO3, and three wins BO5. A missing game, a tie, or a partial series
    returns ``None`` so it can never be published as a finished match.
    """

    if not isinstance(maps, list) or not maps:
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
    home_wins = sum(winner_id == home_id for _, winner_id in games)
    away_wins = len(games) - home_wins
    if home_wins == away_wins:
        return None
    winner_wins = max(home_wins, away_wins)
    loser_wins = min(home_wins, away_wins)
    formats = {1: "BO1", 2: "BO3", 3: "BO5"}
    format_name = formats.get(winner_wins)
    if format_name is None or len(games) != winner_wins + loser_wins:
        return None
    if loser_wins >= winner_wins or len(games) > 5:
        return None
    return format_name, home_wins, away_wins
