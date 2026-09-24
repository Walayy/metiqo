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
    Decision,
    FixtureIdentity,
    ParticipantIdentity,
    TeamIdentity,
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
            raw_start = metadata.get("starts_at")
            try:
                recovered = (
                    datetime.fromisoformat(raw_start) if isinstance(raw_start, str) else None
                )
            except ValueError:
                recovered = None
            if recovered and recovered.utcoffset() is not None and start in {None, recovered}:
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


def load_candidates(db: Session, starts: list[datetime]) -> list[Candidate]:
    windows: list[tuple[datetime, datetime]] = []
    for at in sorted(set(starts)):
        first, last = at - TIME_TOLERANCE, at + TIME_TOLERANCE
        if windows and first <= windows[-1][1]:
            windows[-1] = windows[-1][0], max(last, windows[-1][1])
        else:
            windows.append((first, last))
    if not windows:
        return []
    matches = list(
        db.scalars(
            select(EsportMatch).where(
                or_(
                    *[
                        and_(EsportMatch.starts_at >= first, EsportMatch.starts_at <= last)
                        for first, last in windows
                    ]
                )
            )
        )
    )
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
    observations = {
        row.event_id: row
        for row in db.scalars(
            select(BookmakerEventObservation)
            .where(
                BookmakerEventObservation.event_id.in_([e.id for e in events]),
                BookmakerEventObservation.payload["starts_at"].astext.is_not(None),
            )
            .distinct(BookmakerEventObservation.event_id)
            .order_by(
                BookmakerEventObservation.event_id,
                BookmakerEventObservation.observed_at.desc(),
                BookmakerEventObservation.id.desc(),
            )
        )
    }
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
        fixtures[event.id] = fixture_from_event(
            event, snapshot, raw if isinstance(raw, dict) else None
        )
        observation = observations.get(event.id)
        if observation is not None:
            payload = observation.payload
            at = payload.get("starts_at")
            if (
                isinstance(at, str)
                and datetime.fromisoformat(at) == fixtures[event.id].starts_at
                and _participants(payload.get("participants")) == fixtures[event.id].participants
                and payload.get("competition_name") == fixtures[event.id].competition
            ):
                fixtures[event.id].evidence["sourceObservation"] = {
                    "id": observation.id,
                    "sha256": observation.sha256,
                    "observedAt": observation.observed_at.isoformat(),
                }
    candidates = load_candidates(db, [f.starts_at for f in fixtures.values() if f.starts_at])
    aliases = load_aliases(db)
    now = datetime.now(UTC)
    report: list[dict[str, object]] = []
    for event in events:
        fixture = fixtures[event.id]
        state = db.get(BookmakerMatchResolution, event.id)
        link = db.get(BookmakerMatchLink, event.id)
        previous = state.last_match_id if state is not None else link.match_id if link else None
        decision = resolve_fixture(fixture, candidates, aliases, previous)
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
                checked = resolve_fixture(alternate, candidates, aliases, decision.match_id)
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
    aliases: list[AliasRecord]


def import_aliases(engine: Engine, path: Path) -> dict[str, object]:
    document = AliasDocument.model_validate_json(path.read_text(encoding="utf-8"))
    with Session(engine) as db, db.begin():
        lock_identities(db)
        for record in document.aliases:
            digest = fingerprint(record.model_dump(mode="json"))
            if db.get(MatchIdentityAlias, digest) is None:
                db.add(MatchIdentityAlias(id=digest, **record.model_dump(), active=True))
        db.flush()
        return reconcile_in_session(db)


def revoke_alias(engine: Engine, alias_id: str) -> dict[str, object]:
    with Session(engine) as db, db.begin():
        lock_identities(db)
        alias = db.get(MatchIdentityAlias, alias_id)
        if alias is None:
            raise ValueError("Unknown alias")
        alias.active = False
        return reconcile_in_session(db)
