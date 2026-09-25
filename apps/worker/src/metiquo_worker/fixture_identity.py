"""Pure, conservative fixture identity rules. No provider-specific team exceptions."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from metiquo_worker.matching import normalize_name

VERSION = "fixture-identity-v2"
TIME_TOLERANCE = timedelta(minutes=30)
GENERIC_TEAM_WORDS = {"team", "esports", "gaming", "club"}
UNKNOWN_NAMES = {"", "tbd", "tba", "unknown", "to be determined", "winner", "loser"}


def team_key(name: str) -> str:
    # Preserve word order, digits and academy qualifiers; no substring/acronym guesses.
    return " ".join(x for x in normalize_name(name).split() if x not in GENERIC_TEAM_WORDS)


@dataclass(frozen=True)
class Competition:
    brand: str
    years: frozenset[str]
    edition: frozenset[str]
    phase: str | None


def competition_identity(name: str) -> Competition:
    normalized = normalize_name(name)
    years = frozenset(re.findall(r"\b20\d{2}\b", normalized))
    normalized = re.sub(r"\b20\d{2}\b", " ", normalized)
    edition = frozenset(
        re.findall(
            r"\b(?:spring|summer|winter|fall|autumn|split\s+\d+|season\s+\d+|week\s+\d+)\b",
            normalized,
        )
    )
    for value in edition:
        normalized = normalized.replace(value, " ")
    phases = {
        "regular season": "regular",
        "group stage": "groups",
        "groups": "groups",
        "playoffs": "playoffs",
        "playoff": "playoffs",
        "play ins": "playins",
        "play in": "playins",
        "promotion": "promotion",
        "qualifiers": "qualifier",
        "qualifier": "qualifier",
        "lcq": "lcq",
    }
    phase = None
    for suffix, identity in phases.items():
        if re.search(rf"\b{suffix}\s*$", normalized):
            phase = identity
            normalized = re.sub(rf"\b{suffix}\s*$", "", normalized)
            break
    return Competition(" ".join(normalized.split()), years, edition, phase)


def competitions_agree(left: str, right: str) -> bool:
    a, b = competition_identity(left), competition_identity(right)
    return bool(
        a.brand
        and a.brand == b.brand
        and not (a.years and b.years and a.years != b.years)
        and not (a.edition and b.edition and a.edition != b.edition)
        and not (a.phase and b.phase and a.phase != b.phase)
    )


@dataclass(frozen=True)
class ParticipantIdentity:
    position: int
    name: str
    source_id: str | None = None


@dataclass(frozen=True)
class FixtureIdentity:
    id: UUID
    provider: str
    source_id: str
    game: str
    competition_key: str
    competition: str
    starts_at: datetime | None
    participants: tuple[ParticipantIdentity, ...]
    evidence: dict[str, object] = field(default_factory=dict)
    verified_starts: tuple[datetime, ...] = ()


@dataclass(frozen=True)
class TeamIdentity:
    id: str
    names: tuple[str, ...]
    source_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Alias:
    id: str
    provider: str
    game: str
    name: str
    competition_key: str
    target_provider: str
    target_id: str
    valid_from: datetime
    valid_until: datetime

    def applies(self, fixture: FixtureIdentity, participant: ParticipantIdentity) -> bool:
        return bool(
            fixture.provider == self.provider
            and fixture.game == self.game
            and fixture.competition_key == self.competition_key
            and normalize_name(participant.name) == normalize_name(self.name)
            and any(
                self.valid_from <= at < self.valid_until
                for at in (fixture.starts_at, *fixture.verified_starts)
                if at is not None
            )
        )


@dataclass(frozen=True)
class Candidate:
    id: UUID
    starts_at: datetime
    competition: str
    home: TeamIdentity
    away: TeamIdentity
    sources: tuple[dict[str, object], ...]
    game: str = "league-of-legends"


@dataclass(frozen=True)
class Decision:
    status: str
    match_id: UUID | None
    evidence: dict[str, object]


def _participant_proof(
    fixture: FixtureIdentity,
    participant: ParticipantIdentity,
    team: TeamIdentity,
    aliases: tuple[Alias, ...],
) -> dict[str, object] | None:
    key = team_key(participant.name)
    if key in UNKNOWN_NAMES or re.match(r"^(?:winner|loser|tbd|tba)\b", key):
        return None
    scoped = [alias for alias in aliases if alias.applies(fixture, participant)]
    if scoped:
        targets = {(alias.target_provider, alias.target_id) for alias in scoped}
        if len(targets) != 1:
            return None
        provider, target = next(iter(targets))
        if target not in team.source_ids.get(provider, ()):
            return None  # A reviewed alias cannot fall back to a contradictory name.
        return {"basis": "reviewed-alias", "aliasIds": sorted(alias.id for alias in scoped)}
    ids = team.source_ids.get(fixture.provider, ())
    if participant.source_id and ids:
        if participant.source_id not in ids:
            return None
        return {"basis": "provider-team-id", "sourceId": participant.source_id}
    names = sorted({value for value in team.names if team_key(value) == key})
    return {"basis": "exact-name", "names": names} if names else None


def resolve_fixture(
    fixture: FixtureIdentity,
    candidates: list[Candidate],
    aliases: tuple[Alias, ...] = (),
    previous_match_id: UUID | None = None,
) -> Decision:
    evidence: dict[str, object] = {
        "version": VERSION,
        "fixture": fixture.evidence,
        "provider": fixture.provider,
        "sourceId": fixture.source_id,
        "competition": fixture.competition,
        "startsAt": fixture.starts_at.isoformat() if fixture.starts_at else None,
        "verifiedStartsAt": [at.isoformat() for at in fixture.verified_starts],
        "toleranceSeconds": int(TIME_TOLERANCE.total_seconds()),
    }

    def result(status: str, reason: str, match_id: UUID | None = None) -> Decision:
        if previous_match_id is not None and match_id != previous_match_id:
            status = "conflict"
            evidence["previousMatchId"] = str(previous_match_id)
        evidence.update(
            {
                "status": status,
                "reason": reason,
                "matchId": str(match_id) if status == "linked" else None,
            }
        )
        return Decision(status, match_id if status == "linked" else None, evidence)

    if fixture.game != "league-of-legends":
        return result("pending", "unsupported-game")
    if fixture.starts_at is None or fixture.starts_at.utcoffset() is None:
        return result("pending", "missing-verified-time")
    if len(fixture.participants) != 2 or len({p.position for p in fixture.participants}) != 2:
        return result("pending", "incomplete-participants")
    if not fixture.competition:
        return result("pending", "missing-competition")
    for participant in fixture.participants:
        targets = {
            (a.target_provider, a.target_id) for a in aliases if a.applies(fixture, participant)
        }
        if len(targets) > 1:
            return result("conflict", "contradictory-aliases")
    verified_starts = tuple(sorted({fixture.starts_at, *fixture.verified_starts}))
    considered = []
    matches: list[tuple[Candidate, list[dict[str, object]]]] = []
    for candidate in sorted(candidates, key=lambda c: str(c.id)):
        delta = abs((candidate.starts_at - fixture.starts_at).total_seconds())
        nearest_verified_delta = min(
            abs((candidate.starts_at - at).total_seconds()) for at in verified_starts
        )
        # Once linked, old provisional schedules cannot make a later rematch
        # plausible forever. Recheck the retained ID and today's rival fixtures.
        eligible_delta = delta if previous_match_id is not None else nearest_verified_delta
        if candidate.game != fixture.game or (
            eligible_delta > TIME_TOLERANCE.total_seconds() and candidate.id != previous_match_id
        ):
            continue
        competition_ok = competitions_agree(fixture.competition, candidate.competition)
        orientations: list[list[dict[str, object]]] = []
        for teams in ((candidate.home, candidate.away), (candidate.away, candidate.home)):
            proofs = [
                _participant_proof(fixture, p, team, aliases)
                for p, team in zip(fixture.participants, teams, strict=True)
            ]
            if all(proofs) and teams[0].id != teams[1].id:
                orientations.append(
                    [
                        {"position": p.position, "name": p.name, "teamId": team.id, "proof": proof}
                        for p, team, proof in zip(fixture.participants, teams, proofs, strict=True)
                    ]
                )
        if competition_ok or orientations:
            considered.append(
                {
                    "matchId": str(candidate.id),
                    "competition": candidate.competition,
                    "startsAt": candidate.starts_at.isoformat(),
                    "deltaSeconds": delta,
                    "nearestVerifiedDeltaSeconds": nearest_verified_delta,
                    "retainedMatch": candidate.id == previous_match_id
                    and eligible_delta > TIME_TOLERANCE.total_seconds(),
                    "competitionAgrees": competition_ok,
                    "teamOrientations": len(orientations),
                    "teams": [list(candidate.home.names), list(candidate.away.names)],
                }
            )
        if competition_ok:
            matches.extend((candidate, orientation) for orientation in orientations)
    evidence["candidates"] = considered
    if len(matches) > 1:
        return result("ambiguous", "multiple-plausible-identities")
    if not matches:
        return result("pending", "no-demonstrated-candidate")
    candidate, mapping = matches[0]
    evidence["participants"] = mapping
    evidence["sources"] = list(candidate.sources)
    evidence["candidateStartsAt"] = candidate.starts_at.isoformat()
    evidence["candidateCompetition"] = candidate.competition
    selected_delta = abs((candidate.starts_at - fixture.starts_at).total_seconds())
    selected_verified_delta = min(
        abs((candidate.starts_at - at).total_seconds()) for at in verified_starts
    )
    if selected_delta <= TIME_TOLERANCE.total_seconds():
        basis = "current-schedule"
    elif selected_verified_delta <= TIME_TOLERANCE.total_seconds():
        basis = "observed-schedule"
    else:
        basis = "retained-identity"
    evidence["scheduleBasis"] = basis
    return result("linked", f"teams-competition-{basis}", candidate.id)
