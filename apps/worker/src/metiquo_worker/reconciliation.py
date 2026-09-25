"""Transactional event reconciliation and an immutable, reproducible decision journal."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from metiquo_core.models import (
    BookmakerEvent,
    BookmakerEventObservation,
    BookmakerMatchDecision,
    BookmakerMatchLink,
    BookmakerMatchResolution,
    BookmakerPayload,
    BookmakerSnapshot,
    EsportMatch,
    League,
    MatchCompetitionAlias,
    MatchIdentityAlias,
    MatchSourceLink,
    Team,
)
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator
from sqlalchemy import Engine, and_, func, or_, select
from sqlalchemy.orm import Session

from metiquo_worker.fixture_identity import (
    TIME_TOLERANCE,
    Alias,
    Candidate,
    CompetitionAlias,
    Decision,
    FixtureIdentity,
    ParticipantIdentity,
    TeamIdentity,
    competitions_agree,
    resolve_fixture,
    team_key,
)
from metiquo_worker.stake_types import EventMetadata, fingerprint

# All identity writers acquire this before event/catalog/match row locks. One
# transaction publishes source changes and their links; readers never see a torn state.
IDENTITY_LOCK = 7_346_810_215
SPORT_SOURCES = {"loltv", "oracles-elixir"}


def lock_identities(db: Session) -> None:
    db.execute(select(func.pg_advisory_xact_lock(IDENTITY_LOCK)))


def observe_event(db: Session, metadata: EventMetadata) -> None:
    payload = metadata.model_dump(mode="json", exclude={"observed_at"})
    digest = fingerprint(payload)
    latest = db.scalar(
        select(BookmakerEventObservation)
        .where(BookmakerEventObservation.event_id == metadata.id)
        .order_by(BookmakerEventObservation.id.desc())
        .limit(1)
    )
    if latest is None or latest.sha256 != digest:
        db.add(
            BookmakerEventObservation(
                event_id=metadata.id,
                observed_at=metadata.observed_at,
                sha256=digest,
                payload=payload,
            )
        )
        db.flush()


def _participants(raw: object) -> tuple[ParticipantIdentity, ...]:
    if not isinstance(raw, list):
        return ()
    result = []
    for item in raw:
        if not isinstance(item, dict):
            return ()
        position, name, source_id = item.get("position"), item.get("name"), item.get("source_id")
        if not isinstance(position, int) or isinstance(position, bool) or not isinstance(name, str):
            return ()
        result.append(
            ParticipantIdentity(position, name, source_id if isinstance(source_id, str) else None)
        )
    return tuple(sorted(result, key=lambda p: p.position))


def _aware_start(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return value if value.utcoffset() is not None else None


def fixture_from_event(
    event: BookmakerEvent,
    snapshot: BookmakerSnapshot | None = None,
    metadata: dict[str, object] | None = None,
) -> FixtureIdentity:
    participants = _participants(event.participants)
    start = event.starts_at
    proof: dict[str, object] = {
        "eventId": str(event.id),
        "url": event.source_url,
        "identitySha256": fingerprint(
            {
                "participants": event.participants,
                "competition": event.competition_name,
                "competitionKey": event.competition_key,
                "startsAt": start.isoformat() if start else None,
            }
        ),
    }
    if snapshot is not None and metadata is not None:
        old_participants = _participants(metadata.get("participants"))
        # Missing fields can be recovered from a complete source capture, never
        # across a changed pair/competition. The evidence remains dated to that capture.
        if (
            len(participants) == 2
            and [(p.position, team_key(p.name)) for p in participants]
            == [(p.position, team_key(p.name)) for p in old_participants]
            and metadata.get("competition_key") == event.competition_key
        ):
            recovered = _aware_start(metadata.get("starts_at"))
            if recovered and start in {None, recovered}:
                start = start or recovered
                proof["timeEvidence"] = {
                    "snapshotId": str(snapshot.id),
                    "payloadSha256": snapshot.payload_sha256,
                    "observedAt": snapshot.finished_at.isoformat(),
                    "basis": "retained-source-time",
                }
    return FixtureIdentity(
        event.id,
        event.bookmaker,
        event.source_id,
        event.game,
        event.competition_key,
        event.competition_name or "",
        start,
        participants,
        proof,
    )


def with_schedule_observations(
    fixture: FixtureIdentity, observations: list[BookmakerEventObservation]
) -> FixtureIdentity:
    """Keep only dated observations of this same bookmaker fixture as time anchors."""
    anchors: dict[datetime, BookmakerEventObservation] = {}
    for observation in observations:
        payload = observation.payload
        source_start = _aware_start(payload.get("starts_at"))
        if source_start is None:
            continue
        source_competition = payload.get("competition_name")
        source_participants = _participants(payload.get("participants"))
        if (
            not isinstance(source_competition, str)
            or payload.get("competition_key") != fixture.competition_key
            or not competitions_agree(source_competition, fixture.competition)
            or [(p.position, team_key(p.name)) for p in source_participants]
            != [(p.position, team_key(p.name)) for p in fixture.participants]
            or any(
                old.source_id is not None
                and current.source_id is not None
                and old.source_id != current.source_id
                for old, current in zip(source_participants, fixture.participants, strict=True)
            )
        ):
            continue
        instant = source_start.astimezone(UTC)
        if fixture.starts_at is None or instant != fixture.starts_at.astimezone(UTC):
            anchors.setdefault(instant, observation)
    proof = fixture.evidence.copy()
    if anchors:
        proof["scheduleObservations"] = [
            {
                "id": anchors[at].id,
                "sha256": anchors[at].sha256,
                "observedAt": anchors[at].observed_at.isoformat(),
                "startsAt": at.isoformat(),
            }
            for at in sorted(anchors)
        ]
    latest = observations[-1] if observations else None
    if latest is not None:
        payload = latest.payload
        if (
            _aware_start(payload.get("starts_at")) == fixture.starts_at
            and _participants(payload.get("participants")) == fixture.participants
            and payload.get("competition_name") == fixture.competition
        ):
            proof["sourceObservation"] = {
                "id": latest.id,
                "sha256": latest.sha256,
                "observedAt": latest.observed_at.isoformat(),
            }
    return replace(fixture, evidence=proof, verified_starts=tuple(sorted(anchors)))


def _team(team: Team) -> TeamIdentity:
    names = [team.data.get("name")]
    raw_aliases = team.data.get("aliases")
    if isinstance(raw_aliases, list):
        names.extend(raw_aliases)
    ids = team.data.get("sourceIds")
    source_ids = (
        {
            provider: tuple(value for value in values if isinstance(value, str))
            for provider, values in ids.items()
            if isinstance(values, list)
        }
        if isinstance(ids, dict)
        else {}
    )
    return TeamIdentity(
        team.id, tuple(sorted({n for n in names if isinstance(n, str) and n})), source_ids
    )


def load_candidates(
    db: Session, starts: list[datetime], retained_ids: set[UUID] | None = None
) -> list[Candidate]:
    windows: list[tuple[datetime, datetime]] = []
    for at in sorted(set(starts)):
        first, last = at - TIME_TOLERANCE, at + TIME_TOLERANCE
        if windows and first <= windows[-1][1]:
            windows[-1] = windows[-1][0], max(last, windows[-1][1])
        else:
            windows.append((first, last))
    filters = [
        and_(EsportMatch.starts_at >= first, EsportMatch.starts_at <= last)
        for first, last in windows
    ]
    if retained_ids:
        filters.append(EsportMatch.id.in_(retained_ids))
    if not filters:
        return []
    matches = list(db.scalars(select(EsportMatch).where(or_(*filters))))
    teams = {
        t.id: _team(t)
        for t in db.scalars(
            select(Team).where(
                Team.id.in_({team_id for m in matches for team_id in (m.home_id, m.away_id)})
            )
        )
    }
    leagues = {
        league.id: league
        for league in db.scalars(
            select(League).where(League.id.in_({m.league_id for m in matches}))
        )
    }
    links: dict[UUID, list[MatchSourceLink]] = defaultdict(list)
    for link in db.scalars(
        select(MatchSourceLink).where(
            MatchSourceLink.provider.in_(SPORT_SOURCES),
            MatchSourceLink.match_id.in_([m.id for m in matches]),
        )
    ):
        links[link.match_id].append(link)
    candidates = []
    for match in matches:
        sources = links.get(match.id, [])
        if not sources and match.source not in SPORT_SOURCES:
            continue
        league = leagues.get(match.league_id)
        home, away = teams.get(match.home_id), teams.get(match.away_id)
        if league is None or home is None or away is None:
            continue
        competition = str(league.data.get("name", ""))
        for source in sources:
            name = source.source_names.get("competition")
            if source.provider == "loltv" and isinstance(name, str) and name:
                competition = name  # Original tournament label preserves edition/phase.
        evidence: tuple[dict[str, object], ...] = tuple(
            {
                "provider": link.provider,
                "sourceId": link.source_id,
                "url": link.source_url,
                "names": link.source_names,
            }
            for link in sorted(sources, key=lambda s: (s.provider, s.source_id))
        )
        if not evidence:
            evidence = ({"provider": match.source, "sourceId": match.source_id},)
        candidates.append(Candidate(match.id, match.starts_at, competition, home, away, evidence))
    return candidates


def load_aliases(db: Session) -> tuple[Alias, ...]:
    return tuple(
        Alias(
            a.id,
            a.provider,
            a.game,
            a.name,
            a.competition_key,
            a.target_provider,
            a.target_id,
            a.valid_from,
            a.valid_until,
        )
        for a in db.scalars(select(MatchIdentityAlias).where(MatchIdentityAlias.active.is_(True)))
    )


def load_competition_aliases(db: Session) -> tuple[CompetitionAlias, ...]:
    return tuple(
        CompetitionAlias(
            a.id,
            a.provider,
            a.game,
            a.name,
            a.competition_key,
            a.target_provider,
            a.target_id,
            a.valid_from,
            a.valid_until,
        )
        for a in db.scalars(
            select(MatchCompetitionAlias).where(MatchCompetitionAlias.active.is_(True))
        )
    )


def reconcile_in_session(
    db: Session,
    *,
    event_ids: set[UUID] | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    lock_identities(db)
    db.flush()
    statement = select(BookmakerEvent).order_by(BookmakerEvent.id)
    if event_ids is not None:
        statement = statement.where(BookmakerEvent.id.in_(event_ids))
    events = list(db.scalars(statement))
    snapshots = {
        snapshot.event_id: (snapshot, metadata)
        for snapshot, metadata in db.execute(
            select(BookmakerSnapshot, BookmakerPayload.document["metadata"])
            .join(BookmakerPayload, BookmakerPayload.sha256 == BookmakerSnapshot.payload_sha256)
            .where(BookmakerSnapshot.event_id.in_([e.id for e in events]))
            .distinct(BookmakerSnapshot.event_id)
            .order_by(
                BookmakerSnapshot.event_id,
                BookmakerSnapshot.finished_at.desc(),
                BookmakerSnapshot.id,
            )
        )
    }
    fixtures = {}
    schedule_history: dict[UUID, list[BookmakerEventObservation]] = defaultdict(list)
    for row in db.scalars(
        select(BookmakerEventObservation)
        .where(
            BookmakerEventObservation.event_id.in_([e.id for e in events]),
            BookmakerEventObservation.payload["starts_at"].astext.is_not(None),
        )
        .order_by(BookmakerEventObservation.observed_at, BookmakerEventObservation.id)
    ):
        schedule_history[row.event_id].append(row)
    latest_readings = {
        row.event_id: row
        for row in db.scalars(
            select(BookmakerEventObservation)
            .where(BookmakerEventObservation.event_id.in_([e.id for e in events]))
            .distinct(BookmakerEventObservation.event_id)
            .order_by(
                BookmakerEventObservation.event_id,
                BookmakerEventObservation.observed_at.desc(),
                BookmakerEventObservation.id.desc(),
            )
        )
    }
    for event in events:
        snapshot, raw = snapshots.get(event.id, (None, None))
        fixtures[event.id] = with_schedule_observations(
            fixture_from_event(event, snapshot, raw if isinstance(raw, dict) else None),
            schedule_history[event.id],
        )
    states = {
        state.event_id: state
        for state in db.scalars(
            select(BookmakerMatchResolution).where(
                BookmakerMatchResolution.event_id.in_([e.id for e in events])
            )
        )
    }
    links = {
        link.event_id: link
        for link in db.scalars(
            select(BookmakerMatchLink).where(
                BookmakerMatchLink.event_id.in_([e.id for e in events])
            )
        )
    }
    retained_ids = {
        state.last_match_id for state in states.values() if state.last_match_id is not None
    } | {link.match_id for link in links.values()}
    candidates = load_candidates(
        db,
        [
            at
            for fixture in fixtures.values()
            for at in (fixture.starts_at, *fixture.verified_starts)
            if at
        ],
        retained_ids,
    )
    aliases = load_aliases(db)
    competition_aliases = load_competition_aliases(db)
    now = datetime.now(UTC)
    report: list[dict[str, object]] = []
    for event in events:
        fixture = fixtures[event.id]
        state = states.get(event.id)
        link = links.get(event.id)
        previous = (
            state.last_match_id
            if state and state.last_match_id
            else link.match_id
            if link
            else None
        )
        decision = resolve_fixture(fixture, candidates, aliases, previous, competition_aliases)
        reading = latest_readings.get(event.id)
        if reading is not None and decision.match_id is not None:
            participants = _participants(reading.payload.get("participants"))
            competition = reading.payload.get("competition_name")
            if len(participants) == 2 and (
                participants != fixture.participants
                or (competition and competition != fixture.competition)
            ):
                alternate = replace(
                    fixture,
                    participants=participants,
                    competition=competition
                    if isinstance(competition, str) and competition
                    else fixture.competition,
                )
                checked = resolve_fixture(
                    alternate, candidates, aliases, decision.match_id, competition_aliases
                )
                if checked.match_id != decision.match_id:
                    decision = Decision(
                        "conflict",
                        None,
                        {
                            **decision.evidence,
                            "status": "conflict",
                            "matchId": None,
                            "reason": "contradictory-latest-reading",
                            "readingId": reading.id,
                            "readingSha256": reading.sha256,
                            "readingObservedAt": reading.observed_at.isoformat(),
                            "retainedCandidateId": str(decision.match_id),
                        },
                    )
        report.append({"eventId": event.source_id, **decision.evidence})
        if dry_run:
            continue
        # Retain pre-existing links before replacing the retired matching engine.
        if state is None and link is not None:
            legacy = {
                "status": "legacy",
                "matchId": str(link.match_id),
                "method": link.method,
                "evidence": link.evidence,
                "linkedAt": link.linked_at.isoformat(),
            }
            db.add(
                BookmakerMatchDecision(
                    event_id=event.id, decided_at=now, sha256=fingerprint(legacy), evidence=legacy
                )
            )
        digest = fingerprint(decision.evidence)
        if state is None:
            state = BookmakerMatchResolution(event_id=event.id)
            db.add(state)
        if state.sha256 != digest:
            db.add(
                BookmakerMatchDecision(
                    event_id=event.id, decided_at=now, sha256=digest, evidence=decision.evidence
                )
            )
        state.status = decision.status
        state.last_match_id = previous or decision.match_id
        state.checked_at = now
        state.sha256 = digest
        state.evidence = decision.evidence
        if decision.match_id is None:
            if link is not None:
                db.delete(link)
        else:
            if link is None:
                link = BookmakerMatchLink(event_id=event.id, linked_at=now)
                db.add(link)
            link.match_id = decision.match_id
            link.method = str(decision.evidence["version"])
            link.evidence = decision.evidence
    return {
        "events": len(report),
        "counts": dict(Counter(str(r["status"]) for r in report)),
        "decisions": report,
        "dryRun": dry_run,
    }


def reconcile_matches(engine: Engine, *, dry_run: bool = False) -> dict[str, object]:
    with Session(engine) as db, db.begin():
        return reconcile_in_session(db, dry_run=dry_run)


class AliasRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1)
    game: str = Field(min_length=1)
    name: str = Field(min_length=1)
    competition_key: str = Field(min_length=1)
    target_provider: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    evidence: dict[str, JsonValue]

    @model_validator(mode="after")
    def require_evidence(self) -> AliasRecord:
        if (
            self.valid_until <= self.valid_from
            or not self.evidence.get("sources")
            or not self.evidence.get("reason")
        ):
            raise ValueError("Alias requires a validity interval, sources and a reviewed reason")
        return self


class AliasDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aliases: list[AliasRecord] = Field(default_factory=list)
    competition_aliases: list[AliasRecord] = Field(default_factory=list)


def import_aliases(engine: Engine, path: Path) -> dict[str, object]:
    document = AliasDocument.model_validate_json(path.read_text(encoding="utf-8"))
    with Session(engine) as db, db.begin():
        lock_identities(db)
        for record in document.aliases:
            digest = fingerprint(record.model_dump(mode="json"))
            if db.get(MatchIdentityAlias, digest) is None:
                db.add(MatchIdentityAlias(id=digest, **record.model_dump(), active=True))
        for record in document.competition_aliases:
            digest = fingerprint({"kind": "competition", "record": record.model_dump(mode="json")})
            if db.get(MatchCompetitionAlias, digest) is None:
                db.add(MatchCompetitionAlias(id=digest, **record.model_dump(), active=True))
        db.flush()
        return reconcile_in_session(db)


def revoke_alias(engine: Engine, alias_id: str) -> dict[str, object]:
    with Session(engine) as db, db.begin():
        lock_identities(db)
        alias = db.get(MatchIdentityAlias, alias_id) or db.get(MatchCompetitionAlias, alias_id)
        if alias is None:
            raise ValueError("Unknown alias")
        alias.active = False
        return reconcile_in_session(db)
