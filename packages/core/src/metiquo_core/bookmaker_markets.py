"""Strictly identify supported Stake winner markets from public labels."""

import re

MATCH_WINNER = re.compile(r"^vainqueur du match(?:\s*-\s*two options)?$", re.I)
MAP_WINNER = re.compile(
    r"^(?:(?:map|carte)\s+(\d+)\s+(?:gagnant|vainqueur)"
    r"|vainqueur de la carte\s+(\d+))(?:\s*-\s*two options)?$",
    re.I,
)


def supported_winner_market(
    label: str, scope: str, period: int | None
) -> tuple[str, int | None] | None:
    normalized = " ".join(label.strip().split())
    if MATCH_WINNER.fullmatch(normalized) and scope == "match" and period is None:
        return "match_winner", None
    match = MAP_WINNER.fullmatch(normalized)
    if match and scope == "period":
        number = int(match.group(1) or match.group(2))
        if 1 <= number <= 5 and period == number:
            return "map_winner", number
    return None
