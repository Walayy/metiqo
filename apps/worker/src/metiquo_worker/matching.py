"""Provider-independent identity matching for esport fixtures.

The resolver deliberately prefers an explicit provider link and stable internal ids.
Names are only used as a scored fallback; ambiguous candidates are rejected instead
of silently linking the wrong Oracle, SofaScore or future bookmaker match.
"""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from metiquo_core.models import EsportMatch, League, Team


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    value = ascii_value.casefold().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokens(value: str) -> set[str]:
    return set(normalize_name(value).split())


def name_score(incoming: str, canonical: str, code: str = "", slug: str = "") -> float:
    left = normalize_name(incoming)
    candidates = [normalize_name(value) for value in (canonical, code, slug) if value]
    if not left or not candidates:
        return 0.0
    best = 0.0
    left_tokens = tokens(left)
    for candidate in candidates:
        if left == candidate:
            best = max(best, 1.0)
            continue
        candidate_tokens = tokens(candidate)
        if left_tokens and (left_tokens <= candidate_tokens or candidate_tokens <= left_tokens):
            best = max(best, 0.94)
        overlap = len(left_tokens & candidate_tokens) / max(1, len(left_tokens | candidate_tokens))
        best = max(best, 0.72 * overlap + 0.28 * SequenceMatcher(None, left, candidate).ratio())
    return best


TEAM_QUALIFIERS = {
    "academy",
    "challenger",
    "challengers",
    "junior",
    "youth",
    "fem",
    "feminine",
    "fenix",
    "reserve",
}


@dataclass(frozen=True)
class TeamResolution:
    team_id: str
    score: float
    margin: float


def resolve_team(name: str, teams: list[Team]) -> TeamResolution | None:
    incoming_tokens = tokens(name)
    scored: list[tuple[float, str]] = []
    for team in teams:
        canonical_name = str(team.data.get("name", ""))
        canonical_tokens = tokens(canonical_name)
        extra_tokens = incoming_tokens - canonical_tokens
        # A qualifier changes the identity: Bilibili Gaming Junior is not
        # Bilibili Gaming, and T1 Academy is not T1. Let the source team
        # identity be provisioned instead of silently linking the parent.
        if canonical_tokens < incoming_tokens and extra_tokens & TEAM_QUALIFIERS:
            continue
        scored.append(
            (
                name_score(
                    name,
                    canonical_name,
                    str(team.data.get("code", "")),
                    str(team.data.get("slug", "")),
                ),
                team.id,
            )
        )
    scored.sort()
    if not scored:
        return None
    scored.reverse()
    score, team_id = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    margin = score - second
    if score < 0.57 or (score < 0.9 and margin < 0.08):
        return None
    return TeamResolution(team_id=team_id, score=score, margin=margin)


@dataclass(frozen=True)
class MatchIdentity:
    home_name: str
    away_name: str
    starts_at: Any
    competition: str
    provider: str
    provider_id: str


@dataclass(frozen=True)
class MatchResolution:
    home_id: str
    away_id: str
    league_id: str
    existing_match: EsportMatch | None
    confidence: float
    reason: str


def resolve_match(
    identity: MatchIdentity,
    teams: list[Team],
    leagues: list[League],
    existing: list[EsportMatch],
) -> MatchResolution | None:
    home = resolve_team(identity.home_name, teams)
    away = resolve_team(identity.away_name, teams)
    if home is None or away is None or home.team_id == away.team_id:
        return None

    league_scores = sorted(
        (
            name_score(
                identity.competition,
                str(league.data.get("name", "")),
                slug=str(league.data.get("slug", "")),
            ),
            league.id,
        )
        for league in leagues
    )
    if not league_scores or league_scores[-1][0] < 0.82:
        # Never force an international tournament into a regional league just
        # because it is the closest string. The caller may provision the
        # source competition first, after which this score becomes exact.
        return None
    league_id = league_scores[-1][1]
    competition_score = league_scores[-1][0]

    candidates: list[tuple[float, EsportMatch]] = []
    for match in existing:
        same_direction = match.home_id == home.team_id and match.away_id == away.team_id
        reversed_direction = match.home_id == away.team_id and match.away_id == home.team_id
        if not same_direction and not reversed_direction:
            continue
        delta_hours = abs((match.starts_at - identity.starts_at).total_seconds()) / 3600
        if delta_hours > 72:
            continue
        direction_score = 1.0 if same_direction else 0.94
        time_score = max(0.0, 1.0 - delta_hours / 72)
        league_bonus = 0.08 if match.league_id == league_id else 0.0
        candidates.append((direction_score * 0.62 + time_score * 0.3 + league_bonus, match))
    candidates.sort(key=lambda item: item[0], reverse=True)
    if candidates and (len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= 0.06):
        score, match = candidates[0]
        return MatchResolution(
            home_id=home.team_id,
            away_id=away.team_id,
            league_id=match.league_id,
            existing_match=match,
            confidence=min(1.0, score * 0.65 + home.score * 0.2 + away.score * 0.15),
            reason="team-pair-and-time",
        )
    if candidates:
        return None
    return MatchResolution(
        home_id=home.team_id,
        away_id=away.team_id,
        league_id=league_id,
        existing_match=None,
        confidence=min(1.0, home.score * 0.38 + away.score * 0.38 + competition_score * 0.24),
        reason="new-source-link",
    )


def serializable_source_names(identity: MatchIdentity) -> dict[str, object]:
    return {
        "home": identity.home_name,
        "away": identity.away_name,
        "competition": identity.competition,
        "provider": identity.provider,
        "providerId": identity.provider_id,
    }
