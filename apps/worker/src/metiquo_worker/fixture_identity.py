"""Pure, conservative fixture identity rules. No provider-specific team exceptions."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from metiquo_worker.matching import TEAM_GENERIC_WORDS, TEAM_QUALIFIERS, normalize_name

VERSION = "fixture-identity-v4"
TIME_TOLERANCE = timedelta(minutes=30)
GENERIC_TEAM_WORDS = {"team", "esports", "gaming", "club"}
GENERIC_COMPETITION_WORDS = {
    "league",
    "cup",
    "tournament",
    "championship",
    "series",
    "esports",
    "international",
    "masters",
    "invitational",
}
COMPETITION_DIVISIONS = {
    "academy",
    "academies",
    "challenger",
    "challengers",
    "junior",
    "youth",
    "women",
    "female",
    "cl",
}
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
        "swiss stage": "swiss",
        "swiss": "swiss",
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
    codes: tuple[str, ...] = ()


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
class CompetitionAlias:
    id: str
    provider: str
    game: str
    name: str
    competition_key: str
    target_provider: str
    target_id: str
    valid_from: datetime
    valid_until: datetime

    def applies(self, fixture: FixtureIdentity) -> bool:
        return bool(
            fixture.provider == self.provider
            and fixture.game == self.game
            and fixture.competition_key == self.competition_key
            and normalize_name(fixture.competition) == normalize_name(self.name)
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
    if names:
        return {"basis": "exact-name", "names": names}
    codes = sorted({value for value in team.codes if team_key(value) == key})
    return {"basis": "sourced-team-code", "codes": codes} if codes else None


def _edition_compatible(left: str, right: str) -> bool:
    """A fixture can corroborate a differently named tournament, never a different edition."""
    a, b = competition_identity(left), competition_identity(right)
    return not (
        (a.years and b.years and a.years != b.years)
        or (a.edition and b.edition and a.edition != b.edition)
        or (a.phase and b.phase and a.phase != b.phase)
    )


def _brand_anchor(left: str, right: str) -> bool:
    a, b = competition_identity(left).brand, competition_identity(right).brand
    if not a or not b:
        return False
    if a == "".join(word[0] for word in b.split()) or b == "".join(word[0] for word in a.split()):
        return len(a) >= 2 and len(b) >= 2
    if (set(a.split()) & COMPETITION_DIVISIONS) != (set(b.split()) & COMPETITION_DIVISIONS):
        return False
    first = set(a.split()) - GENERIC_COMPETITION_WORDS
    second = set(b.split()) - GENERIC_COMPETITION_WORDS
    return bool(first & second)


def _source_competition(candidate: Candidate) -> dict[str, str] | None:
    source_ids: set[str] = set()
    for source in candidate.sources:
        names = source.get("names")
        source_id = names.get("competitionSourceId") if isinstance(names, dict) else None
        if source.get("provider") == "loltv" and isinstance(source_id, str) and source_id:
            source_ids.add(source_id)
    if len(source_ids) != 1:
        return None
    return {"provider": "loltv", "sourceId": next(iter(source_ids))}


def _distinctive_team_words(name: str) -> set[str]:
    return {
        word
        for word in normalize_name(name).split()
        if len(word) >= 3 and word not in TEAM_GENERIC_WORDS | TEAM_QUALIFIERS | {"the"}
    }


def _contextual_team_proof(
    fixture: FixtureIdentity,
    participant: ParticipantIdentity,
    team: TeamIdentity,
    aliases: tuple[Alias, ...],
    known_names: dict[str, set[str]],
    retained_target_id: str | None = None,
) -> dict[str, object] | None:
    """Use a unique sourced fixture to identify one otherwise unknown participant."""
    key = team_key(participant.name)
    if (
        key in UNKNOWN_NAMES
        or re.match(r"^(?:winner|loser|tbd|tba)\b", key)
        or any(
            alias.provider == fixture.provider
            and alias.game == fixture.game
            and alias.competition_key == fixture.competition_key
            and normalize_name(alias.name) == normalize_name(participant.name)
            for alias in aliases
        )
        or participant.source_id is not None
        or known_names.get(key, set()) - {team.id}
    ):
        return None
    # Academy and other squad qualifiers are part of the identity, never decoration.
    qualifiers = set(normalize_name(participant.name).split()) & TEAM_QUALIFIERS
    if not team.names or not any(
        set(normalize_name(name).split()) & TEAM_QUALIFIERS == qualifiers for name in team.names
    ):
        return None
    meaningful = _distinctive_team_words(participant.name)
    if retained_target_id is None and (
        not meaningful or not any(meaningful & _distinctive_team_words(name) for name in team.names)
    ):
        return None
    source_ids = team.source_ids.get("loltv", ())
    if len(source_ids) != 1 or (retained_target_id and source_ids[0] != retained_target_id):
        return None
    return {"basis": "unique-fixture-context", "targetProvider": "loltv", "targetId": source_ids[0]}


def _competition_proof(
    fixture: FixtureIdentity,
    candidate: Candidate,
    aliases: tuple[CompetitionAlias, ...],
) -> dict[str, object] | None:
    scoped = [alias for alias in aliases if alias.applies(fixture)]
    if scoped:
        targets = {(alias.target_provider, alias.target_id) for alias in scoped}
        if len(targets) != 1:
            return None
        provider, target_id = next(iter(targets))
        for source in candidate.sources:
            names = source.get("names")
            if (
                source.get("provider") == provider
                and isinstance(names, dict)
                and names.get("competitionSourceId") == target_id
            ):
                return {
                    "basis": "reviewed-alias",
                    "aliasIds": sorted(a.id for a in scoped),
                    "targetId": target_id,
                }
        return None
    if competitions_agree(fixture.competition, candidate.competition):
        return {"basis": "exact-competition"}
    return None


def resolve_fixture(
    fixture: FixtureIdentity,
    candidates: list[Candidate],
    aliases: tuple[Alias, ...] = (),
    previous_match_id: UUID | None = None,
    competition_aliases: tuple[CompetitionAlias, ...] = (),
    previous_evidence: dict[str, object] | None = None,
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
    competition_targets = {
        (a.target_provider, a.target_id) for a in competition_aliases if a.applies(fixture)
    }
    if len(competition_targets) > 1:
        return result("conflict", "contradictory-competition-aliases")
    verified_starts = tuple(sorted({fixture.starts_at, *fixture.verified_starts}))
    considered = []
    matches: list[tuple[Candidate, list[dict[str, object]]]] = []
    contextual: list[tuple[Candidate, list[dict[str, object]], dict[str, object]]] = []
    known_names: dict[str, set[str]] = {}
    for candidate in candidates:
        for team in (candidate.home, candidate.away):
            for name in (*team.names, *team.codes):
                known_names.setdefault(team_key(name), set()).add(team.id)
    has_competition_alias = any(
        alias.provider == fixture.provider
        and alias.game == fixture.game
        and alias.competition_key == fixture.competition_key
        and normalize_name(alias.name) == normalize_name(fixture.competition)
        for alias in competition_aliases
    )

    def retained_contextual_team(
        candidate: Candidate, missing: int, team: TeamIdentity
    ) -> str | None:
        if previous_match_id != candidate.id or previous_evidence is None:
            return None
        if previous_evidence.get("matchId") != str(candidate.id):
            return None
        mapping = previous_evidence.get("participants")
        if not isinstance(mapping, list):
            return None
        participant = fixture.participants[missing]
        for row in mapping:
            if not isinstance(row, dict):
                continue
            proof = row.get("proof")
            if (
                row.get("position") == participant.position
                and row.get("teamId") == team.id
                and isinstance(row.get("name"), str)
                and team_key(row["name"]) == team_key(participant.name)
                and isinstance(proof, dict)
                and proof.get("basis") == "unique-fixture-context"
                and isinstance(proof.get("targetId"), str)
            ):
                target_id = proof["targetId"]
                if isinstance(target_id, str):
                    return target_id
        return None

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
        competition_proof = _competition_proof(fixture, candidate, competition_aliases)
        competition_ok = competition_proof is not None
        orientations: list[list[dict[str, object]]] = []
        contextual_orientations: list[tuple[list[dict[str, object]], dict[str, object]]] = []
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
            if teams[0].id == teams[1].id:
                continue
            contextual_competition = None
            contextual_proofs = proofs[:]
            if competition_ok and sum(proof is not None for proof in proofs) == 1:
                missing = 0 if proofs[0] is None else 1
                retained_target_id = retained_contextual_team(candidate, missing, teams[missing])
                if previous_match_id is None or retained_target_id is not None:
                    contextual_proofs[missing] = _contextual_team_proof(
                        fixture,
                        fixture.participants[missing],
                        teams[missing],
                        aliases,
                        known_names,
                        retained_target_id,
                    )
                    if contextual_proofs[missing] is not None:
                        contextual_competition = competition_proof
            elif (
                not competition_ok
                and not has_competition_alias
                and all(proofs)
                and _edition_compatible(fixture.competition, candidate.competition)
                and _brand_anchor(fixture.competition, candidate.competition)
            ):
                source_competition = _source_competition(candidate)
                if source_competition is not None:
                    contextual_competition = {
                        "basis": "unique-fixture-context",
                        "source": source_competition,
                    }
            if contextual_competition is not None and all(contextual_proofs):
                contextual_orientations.append(
                    (
                        [
                            {
                                "position": p.position,
                                "name": p.name,
                                "teamId": team.id,
                                "proof": proof,
                            }
                            for p, team, proof in zip(
                                fixture.participants, teams, contextual_proofs, strict=True
                            )
                        ],
                        contextual_competition,
                    )
                )
        if competition_ok or orientations or contextual_orientations:
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
                    "competitionProof": competition_proof,
                    "teamOrientations": len(orientations),
                    "contextualOrientations": len(contextual_orientations),
                    "teams": [list(candidate.home.names), list(candidate.away.names)],
                }
            )
        if competition_ok:
            matches.extend((candidate, orientation) for orientation in orientations)
        contextual.extend(
            (candidate, orientation, proof) for orientation, proof in contextual_orientations
        )
    evidence["candidates"] = considered
    if len(matches) > 1:
        return result("ambiguous", "multiple-plausible-identities")
    if matches:
        candidate, mapping = matches[0]
        # Contextual evidence cannot override a fully demonstrated but different fixture.
        if any(other.id != candidate.id for other, _, _ in contextual):
            return result("ambiguous", "conflicting-contextual-identity")
    elif len(contextual) == 1:
        candidate, mapping, competition_proof = contextual[0]
        evidence["contextualCompetitionProof"] = competition_proof
    elif contextual:
        return result("ambiguous", "multiple-contextual-identities")
    else:
        return result("pending", "no-demonstrated-candidate")
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
