"""Durable publication of rendered SofaScore LoL match snapshots."""

import copy
import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from metiquo_core.config import Settings
from metiquo_core.models import (
    EsportMatch,
    IngestionRun,
    League,
    MatchSnapshot,
    MatchSourceLink,
    Team,
)
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from metiquo_worker.jobs import source_lock
from metiquo_worker.matching import (
    MatchIdentity,
    MatchResolution,
    normalize_name,
    resolve_match,
    resolve_team,
    serializable_source_names,
)
from metiquo_worker.oracle_match_sync import sync_oracle_match_details
from metiquo_worker.sources.sofascore import SOURCE, SofaEvent, SofaScoreBlocked, scrape

logger = logging.getLogger(__name__)
LOCK_ID = 7_346_810_207


def _source_key(kind: str, value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return f"sofascore:{kind}:{normalized or 'unknown'}"


def _ensure_competition(session: Session, event: SofaEvent) -> League:
    competition_id = _source_key("tournament", event.competition_source_id)
    league = session.get(League, competition_id)
    event_name = normalize_name(event.competition)
    event_base_name = re.sub(r"\s+(?:group|groupe)\s+[a-z0-9]+$", "", event_name).strip()
    if league is None:
        for candidate in session.scalars(select(League)).all():
            candidate_name = normalize_name(str(candidate.data.get("name", "")))
            candidate_slug = normalize_name(str(candidate.data.get("slug", "")))
            if candidate_name in {event_name, event_base_name}:
                league = candidate
                break
            if (
                candidate_slug == "wsci"
                and "world star challengers invitational" in event_base_name
            ):
                league = candidate
                break
    if league is None:
        league = League(
            id=competition_id,
            data={
                "id": competition_id,
                "slug": event.competition_slug,
                "name": event.competition,
                "region": "INTERNATIONAL",
                "image": "",
                "sourceImage": event.competition_image,
                "tier": "international",
                "sourceId": event.competition_source_id,
            },
        )
        session.add(league)
        session.flush()
    return league


def _ensure_team(
    session: Session,
    teams: list[Team],
    event: SofaEvent,
    competition: League,
    *,
    home: bool,
) -> Team:
    name = event.home_name if home else event.away_name
    image = event.home_image if home else event.away_image
    source_id = event.home_source_id if home else event.away_source_id
    competition_teams = [team for team in teams if team.league_id == competition.id]
    resolution = resolve_team(name, competition_teams)
    if resolution is None:
        resolution = resolve_team(name, teams)
    if resolution is not None and resolution.score < 0.9:
        resolution = None
    if resolution is not None:
        return next(team for team in teams if team.id == resolution.team_id)
    team_id = _source_key("team", source_id)
    existing = session.get(Team, team_id)
    if existing is None:
        competition_id = competition.id
        existing = Team(
            id=team_id,
            league_id=competition_id,
            data={
                "id": team_id,
                "name": name,
                "code": "",
                "slug": re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-"),
                "leagueId": competition_id,
                "image": "",
                "sourceImage": image,
                "sourceId": source_id,
            },
        )
        session.add(existing)
        session.flush()
    if all(team.id != existing.id for team in teams):
        teams.append(existing)
    return existing


def _fingerprint(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _format(best_of: int) -> str:
    return f"BO{best_of}" if best_of in {1, 3, 5} else "BO1"


def _payload(event: SofaEvent) -> dict[str, object]:
    result = copy.deepcopy(event.payload)
    current_score = None
    if event.home_score is not None or event.away_score is not None:
        current_score = {
            "home": event.home_score or 0,
            "away": event.away_score or 0,
        }
    result.update(
        {
            "status": event.status,
            "startsAt": event.starts_at.isoformat(),
            "format": _format(event.best_of),
            "currentScore": current_score,
            "maps": [],
            "seriesScore": None,
            "patch": None,
            "stage": event.competition,
            "matchIdentity": {
                "home": event.home_name,
                "away": event.away_name,
                "competition": event.competition,
            },
        }
    )
    return result


def _save_event(
    session: Session,
    event: SofaEvent,
    competition: League,
    home_team: Team,
    away_team: Team,
    teams: list[Team],
    leagues: list[League],
    existing: list[EsportMatch],
    now: datetime,
) -> tuple[bool, bool]:
    identity = MatchIdentity(
        home_name=event.home_name,
        away_name=event.away_name,
        starts_at=event.starts_at,
        competition=event.competition,
        provider=SOURCE,
        provider_id=event.source_id,
    )
    link = session.scalar(
        select(MatchSourceLink).where(
            MatchSourceLink.provider == SOURCE, MatchSourceLink.source_id == event.source_id
        )
    )
    linked_match = session.get(EsportMatch, link.match_id) if link is not None else None
    resolution: MatchResolution | None = None
    match: EsportMatch | None
    if linked_match is not None:
        match = linked_match
        created = False
        match.home_id = home_team.id
        match.away_id = away_team.id
        match.league_id = competition.id
    else:
        resolution = resolve_match(identity, teams, leagues, existing)
        if resolution is None:
            logger.warning(
                "SofaScore match left unmatched: %s vs %s", event.home_name, event.away_name
            )
            return False, False
        match = resolution.existing_match
        created = match is None
    if match is None:
        assert resolution is not None
        match = EsportMatch(
            id=uuid4(),
            source=SOURCE,
            source_id=event.source_id,
            league_id=competition.id,
            home_id=home_team.id,
            away_id=away_team.id,
            starts_at=event.starts_at,
            registered_at=now,
            format=_format(event.best_of),
        )
        session.add(match)
        session.flush()
        existing.append(match)
    else:
        match.starts_at = event.starts_at
        match.format = _format(event.best_of)
        match.league_id = competition.id
        match.home_id = home_team.id
        match.away_id = away_team.id

    names = serializable_source_names(identity)
    names.update(
        {
            "competitionSourceId": event.competition_source_id,
            "homeSourceId": event.home_source_id,
            "awaySourceId": event.away_source_id,
        }
    )
    if link is None:
        session.add(
            MatchSourceLink(
                match_id=match.id,
                provider=SOURCE,
                source_id=event.source_id,
                source_url=event.url,
                source_names=names,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
    else:
        link.match_id = match.id
        link.source_url = event.url
        link.source_names = names
        link.last_seen_at = now
    payload = _payload(event)
    digest = _fingerprint(payload)
    if (
        session.scalar(
            select(MatchSnapshot.id).where(
                MatchSnapshot.match_id == match.id, MatchSnapshot.sha256 == digest
            )
        )
        is None
    ):
        session.add(
            MatchSnapshot(
                match_id=match.id,
                source=SOURCE,
                source_id=event.source_id,
                source_url=event.url,
                status=event.status,
                observed_at=now,
                sha256=digest,
                payload=payload,
            )
        )
    return True, created


def sync_sofascore(engine: Engine, settings: Settings) -> UUID:
    with source_lock(engine, LOCK_ID):
        run_id = uuid4()
        now = datetime.now(UTC)
        with Session(engine) as session, session.begin():
            session.add(IngestionRun(id=run_id, source=SOURCE, scope="days:-7..+7"))
        try:
            events = scrape(settings)
            with Session(engine) as session, session.begin():
                teams = list(session.scalars(select(Team)).all())
                leagues = list(session.scalars(select(League)).all())
                existing = list(session.scalars(select(EsportMatch)).all())
                matched = 0
                created = 0
                for event in events:
                    competition = _ensure_competition(session, event)
                    if all(league.id != competition.id for league in leagues):
                        leagues.append(competition)
                    home_team = _ensure_team(session, teams, event, competition, home=True)
                    away_team = _ensure_team(session, teams, event, competition, home=False)
                    did_match, did_create = _save_event(
                        session,
                        event,
                        competition,
                        home_team,
                        away_team,
                        teams,
                        leagues,
                        existing,
                        now,
                    )
                    matched += int(did_match)
                    created += int(did_create)
                details: dict[str, object] = {
                    "events": len(events),
                    "matched": matched,
                    "created": created,
                    "live": sum(event.status == "live" for event in events),
                    "unmatched": len(events) - matched,
                }
                run = session.get(IngestionRun, run_id)
                assert run is not None
                run.status = "succeeded"
                run.finished_at = now
                run.details = details
            # A live page can be the last observation before SofaScore stops
            # listing the event. Oracle may already contain the completed maps;
            # include live events in the reconciliation so the next collection
            # can backfill them immediately.
            detail_source_ids = {
                event.source_id for event in events if event.status in {"live", "finished"}
            }
            match_ids: set[UUID] = set()
            if detail_source_ids:
                with Session(engine) as session:
                    match_ids = set(
                        session.scalars(
                            select(MatchSourceLink.match_id).where(
                                MatchSourceLink.provider == SOURCE,
                                MatchSourceLink.source_id.in_(detail_source_ids),
                            )
                        ).all()
                    )
            if match_ids:
                try:
                    match_details = sync_oracle_match_details(engine, match_ids=match_ids)
                except Exception as error:
                    match_details = {"status": "failed", "error": type(error).__name__}
                    logger.exception("Oracle match detail projection failed after SofaScore sync")
                with Session(engine) as session, session.begin():
                    run = session.get(IngestionRun, run_id)
                    assert run is not None
                    run.details = {**details, "matchDetails": match_details}
            return run_id
        except Exception as error:
            with Session(engine) as session, session.begin():
                run = session.get(IngestionRun, run_id)
                assert run is not None
                run.status = "failed"
                run.finished_at = datetime.now(UTC)
                run.error = (
                    str(error) if isinstance(error, SofaScoreBlocked) else type(error).__name__
                )
            detail = str(error) if isinstance(error, SofaScoreBlocked) else type(error).__name__
            raise RuntimeError(f"SofaScore collection failed: {detail}") from None
