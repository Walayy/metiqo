"""Durable publication of rendered SofaScore LoL match snapshots."""

import copy
import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from metiquo_core.catalog import CATALOG_WRITE_LOCK_ID
from metiquo_core.config import Settings
from metiquo_core.models import (
    EsportMatch,
    IngestionRun,
    League,
    MatchSnapshot,
    MatchSourceLink,
    Team,
)
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from metiquo_worker.jobs import source_lock, start_run
from metiquo_worker.matching import (
    MatchIdentity,
    MatchResolution,
    normalize_name,
    resolve_match,
    resolve_team,
    serializable_source_names,
)
from metiquo_worker.oracle_match_sync import sync_oracle_match_details
from metiquo_worker.sofascore_policy import SofaScorePolicy
from metiquo_worker.sources import sofascore as source
from metiquo_worker.sources.sofascore import (
    SOURCE,
    SofaEvent,
    SofaLink,
    SofaScoreBlocked,
    scrape,
)

logger = logging.getLogger(__name__)
LOCK_ID = 7_346_810_207
COMPETITION_PHASE_SUFFIX = re.compile(
    r"\s+(?:regular season|playoffs?|play[ -]?ins?|group stage|qualifiers?|promotion)$"
)


def _source_key(kind: str, value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return f"sofascore:{kind}:{normalized or 'unknown'}"


def _competition_base_name(value: str) -> str:
    normalized = normalize_name(value)
    normalized = re.sub(r"\s+(?:group|groupe)\s+[a-z0-9]+$", "", normalized).strip()
    return COMPETITION_PHASE_SUFFIX.sub("", normalized).strip()


def _competition_brand(event: SofaEvent, leagues: list[League]) -> League | None:
    return _competition_brand_from_source(event.competition, event.payload, leagues)


def _competition_brand_from_source(
    name: str, payload: dict[str, object], leagues: list[League]
) -> League | None:
    event_name = normalize_name(name)
    event_base_name = _competition_base_name(name)
    names = {event_base_name}
    raw = payload.get("event")
    tournament = raw.get("tournament") if isinstance(raw, dict) else None
    parent = tournament.get("uniqueTournament") if isinstance(tournament, dict) else None
    if isinstance(parent, dict):
        names.update(
            normalize_name(value)
            for key in ("name", "slug")
            if isinstance(value := parent.get(key), str)
        )
    # Prefer the sourced catalogue brand over a stage with the same label.
    for candidate in sorted(
        leagues,
        key=lambda item: (
            item.id.startswith("sofascore:"),
            not bool(item.data.get("image")),
            item.id,
        ),
    ):
        candidate_name = normalize_name(str(candidate.data.get("name", "")))
        candidate_slug = normalize_name(str(candidate.data.get("slug", "")))
        if names & {candidate_name, candidate_slug}:
            return candidate
        if candidate_slug == "wsci" and "world star challengers invitational" in names:
            return candidate
    for candidate in leagues:
        if normalize_name(str(candidate.data.get("name", ""))) == event_name:
            return candidate
    return None


def _ensure_competition(session: Session, event: SofaEvent) -> League:
    competition_id = _source_key("tournament", event.competition_source_id)
    league = session.get(League, competition_id)
    leagues = list(session.scalars(select(League)).all())
    brand = _competition_brand(event, leagues)
    event_name = normalize_name(event.competition)
    event_base_name = _competition_base_name(event.competition)
    if brand is not None and (
        normalize_name(str(brand.data.get("name", ""))) in {event_name, event_base_name}
        or normalize_name(str(brand.data.get("slug", ""))) in {event_name, event_base_name}
        or (
            normalize_name(str(brand.data.get("slug", ""))) == "wsci"
            and "world star challengers invitational" in event_base_name
        )
    ):
        # Exact competitions and WSCI groups share one stable catalogue identity.
        if (
            event_name == event_base_name
            or "world star challengers invitational" in event_base_name
        ):
            return brand
    if league is None:
        brand_data = brand.data if brand is not None else {}
        league = League(
            id=competition_id,
            data={
                "id": competition_id,
                "slug": event.competition_slug,
                "name": event.competition,
                "region": str(brand_data.get("region", "INTERNATIONAL")),
                "image": str(brand_data.get("image", "")),
                "sourceImage": event.competition_image or str(brand_data.get("sourceImage", "")),
                "tier": str(brand_data.get("tier", "international")),
                "sourceId": event.competition_source_id,
                "parentLeagueId": brand.id if brand is not None else None,
            },
        )
        session.add(league)
        session.flush()
    elif brand is not None:
        # SofaScore's tournament object often has no image. Refresh an already
        # provisioned stage from the versioned catalogue without losing its
        # source identity or stage label.
        brand_data = brand.data
        league.data = {
            **league.data,
            "region": str(brand_data.get("region", league.data.get("region", "INTERNATIONAL"))),
            "image": str(brand_data.get("image", league.data.get("image", ""))),
            "sourceImage": event.competition_image
            or str(brand_data.get("sourceImage", league.data.get("sourceImage", ""))),
            "tier": str(brand_data.get("tier", league.data.get("tier", "international"))),
            "parentLeagueId": brand.id,
        }
    elif event.competition_image:
        league.data = {**league.data, "sourceImage": event.competition_image}
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
    for candidate in teams:
        source_ids = candidate.data.get("sourceIds")
        provider_ids = source_ids.get(SOURCE) if isinstance(source_ids, dict) else None
        if isinstance(provider_ids, list) and source_id in provider_ids:
            _remember_team_identity(candidate, name, source_id, image)
            return candidate
    # A different stable provider id is not an alias just because names match.
    available = []
    for team in teams:
        ids = team.data.get("sourceIds")
        existing_ids = ids.get(SOURCE) if isinstance(ids, dict) else None
        if not existing_ids:
            available.append(team)
    competition_teams = [team for team in available if team.league_id == competition.id]
    resolution = resolve_team(name, competition_teams)
    if resolution is None:
        resolution = resolve_team(name, available)
    if resolution is not None and resolution.score < 0.9:
        resolution = None
    if resolution is not None:
        resolved = next(team for team in teams if team.id == resolution.team_id)
        _remember_team_identity(resolved, name, source_id, image)
        return resolved
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
                "aliases": [name],
                "sourceIds": {SOURCE: [source_id]},
                "sourceImages": {SOURCE: [image]} if image else {},
            },
        )
        session.add(existing)
        session.flush()
    if all(team.id != existing.id for team in teams):
        teams.append(existing)
    return existing


def _remember_team_identity(team: Team, name: str, source_id: str, image: str) -> None:
    """Persist only high-confidence, observed provider aliases and ids."""
    data: dict[str, object] = dict(team.data)
    alias_values = data.get("aliases")
    aliases = (
        {value for value in alias_values if isinstance(value, str) and value.strip()}
        if isinstance(alias_values, list)
        else set()
    )
    aliases.add(name)
    source_id_values = data.get("sourceIds")
    source_ids = (
        {
            key: list(value)
            for key, value in source_id_values.items()
            if isinstance(key, str) and isinstance(value, list)
        }
        if isinstance(source_id_values, dict)
        else {}
    )
    provider_ids = {value for value in source_ids.get(SOURCE, []) if isinstance(value, str)}
    provider_ids.add(source_id)
    source_ids[SOURCE] = sorted(provider_ids)
    source_image_values = data.get("sourceImages")
    source_images = (
        {
            key: list(value)
            for key, value in source_image_values.items()
            if isinstance(key, str) and isinstance(value, list)
        }
        if isinstance(source_image_values, dict)
        else {}
    )
    if image:
        provider_images = {
            value for value in source_images.get(SOURCE, []) if isinstance(value, str)
        }
        provider_images.add(image)
        source_images[SOURCE] = sorted(provider_images)
        if not data.get("sourceImage"):
            data["sourceImage"] = image
    data["aliases"] = sorted(aliases, key=str.casefold)
    data["sourceIds"] = source_ids
    data["sourceImages"] = source_images
    team.data = data


def _fingerprint(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _format(best_of: int) -> str:
    return f"BO{best_of}" if best_of in {1, 3, 5} else "BO1"


def _rendered_maps(event: SofaEvent, home_team: Team, away_team: Team) -> list[dict[str, object]]:
    rendered = event.payload.get("rendered")
    source_maps = rendered.get("maps") if isinstance(rendered, dict) else None
    if not isinstance(source_maps, list):
        return []
    team_ids = {"home": home_team.id, "away": away_team.id}
    result: list[dict[str, object]] = []
    for source_map in source_maps:
        if not isinstance(source_map, dict):
            continue
        sides: list[dict[str, object]] = []
        source_sides = source_map.get("sides")
        if not isinstance(source_sides, list):
            continue
        for source_side in source_sides:
            if not isinstance(source_side, dict):
                continue
            position = source_side.get("position")
            if position not in team_ids:
                continue
            sides.append(
                {
                    key: value
                    for key, value in source_side.items()
                    if key
                    in {
                        "side",
                        "towers",
                        "dragons",
                        "barons",
                        "heralds",
                        "grubs",
                        "inhibitors",
                        "players",
                    }
                }
                | {"teamId": team_ids[position]}
            )
        winner = source_map.get("winner")
        winner_id = team_ids.get(winner) if isinstance(winner, str) else None
        source_bans = source_map.get("bans")
        bans: list[dict[str, object]] = []
        if isinstance(source_bans, list):
            for source_ban in source_bans:
                if not isinstance(source_ban, dict):
                    continue
                team_id = source_ban.get("teamId")
                if not isinstance(team_id, str) or team_id not in team_ids:
                    continue
                champion = source_ban.get("champion")
                if champion is not None and (not isinstance(champion, str) or not champion.strip()):
                    continue
                if champion is None and not source_ban.get("championImage"):
                    continue
                bans.append({**source_ban, "teamId": team_ids[team_id]})
        result.append(
            {
                "number": source_map.get("number"),
                "status": source_map.get("status"),
                "durationSeconds": source_map.get("durationSeconds"),
                "winnerId": winner_id,
                "bans": bans,
                "sides": sides,
            }
        )
    return result


def _payload(event: SofaEvent, home_team: Team, away_team: Team) -> dict[str, object]:
    result = copy.deepcopy(event.payload)
    current_score = None
    if event.home_score is not None and event.away_score is not None:
        current_score = {
            "home": event.home_score,
            "away": event.away_score,
        }
    maps = _rendered_maps(event, home_team, away_team)
    series_score = current_score
    result.update(
        {
            "status": event.status,
            "startsAt": event.starts_at.isoformat(),
            "format": _format(event.best_of),
            "currentScore": current_score,
            "maps": maps,
            "seriesScore": series_score,
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


def _known_stable_event_ids(session: Session, now: datetime, settings: Settings) -> set[str]:
    rows = session.execute(
        select(
            MatchSourceLink.source_id,
            EsportMatch.starts_at,
            MatchSnapshot.status,
            MatchSourceLink.last_seen_at,
            MatchSnapshot.payload,
        )
        .join(EsportMatch, EsportMatch.id == MatchSourceLink.match_id)
        .join(MatchSnapshot, MatchSnapshot.match_id == EsportMatch.id)
        .where(
            MatchSourceLink.provider == SOURCE,
            MatchSnapshot.source == SOURCE,
            EsportMatch.starts_at >= now - timedelta(days=8),
            EsportMatch.starts_at <= now + timedelta(days=8),
        )
        .distinct(MatchSourceLink.source_id)
        .order_by(
            MatchSourceLink.source_id, MatchSnapshot.observed_at.desc(), MatchSnapshot.id.desc()
        )
    ).all()
    seen: set[str] = set()
    stable: set[str] = set()
    for source_id, starts_at, status, observed_at, payload in rows:
        if source_id in seen:
            continue
        seen.add(source_id)
        maps = payload.get("maps") if isinstance(payload, dict) else None
        if (
            status == "finished"
            and isinstance(maps, list)
            and bool(maps)
            and observed_at > now - timedelta(seconds=settings.sofascore_finished_refresh_seconds)
        ) or (
            status == "scheduled"
            and starts_at > now + timedelta(minutes=30)
            and observed_at > now - timedelta(seconds=settings.sofascore_upcoming_refresh_seconds)
        ):
            stable.add(source_id)
    return stable


def _restore_known_links(session: Session, now: datetime) -> None:
    """Existing fixtures remain refreshable even if absent from today's listing."""
    start = datetime.combine(
        now.astimezone(source.PARIS).date() - timedelta(days=7), datetime.min.time(), source.PARIS
    )
    rows = session.execute(
        select(MatchSourceLink, EsportMatch.starts_at, MatchSnapshot.status)
        .join(EsportMatch, EsportMatch.id == MatchSourceLink.match_id)
        .join(MatchSnapshot, MatchSnapshot.match_id == EsportMatch.id)
        .where(
            MatchSourceLink.provider == SOURCE,
            MatchSnapshot.source == SOURCE,
            EsportMatch.starts_at >= start,
            EsportMatch.starts_at < start + timedelta(days=15),
            func.coalesce(
                MatchSnapshot.payload["event"]["tournament"]["category"]["slug"].astext, "lol"
            )
            == "lol",
        )
        .distinct(MatchSourceLink.source_id)
        .order_by(
            MatchSourceLink.source_id, MatchSnapshot.observed_at.desc(), MatchSnapshot.id.desc()
        )
    ).all()
    links = dict(source._STATE.links or {})
    live_ids = []
    for link, starts_at, status in rows:
        links[link.source_id] = SofaLink(
            link.source_url, link.source_id, starts_at.astimezone(source.PARIS).date(), ""
        )
        if status == "live":
            live_ids.append(link.source_id)
    source._STATE.links = links
    source._STATE.priority_live_ids = live_ids


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
    if linked_match is None:
        linked_match = session.scalar(
            select(EsportMatch).where(
                EsportMatch.source == SOURCE, EsportMatch.source_id == event.source_id
            )
        )
    resolution: MatchResolution | None = None
    match: EsportMatch | None
    if linked_match is not None:
        match = linked_match
        created = False
        match.home_id = home_team.id
        match.away_id = away_team.id
        match.league_id = competition.id
    else:
        # A stable SofaScore event id always represents a schedulable match.
        # Resolution is only used to reuse a match from another provider; a
        # different SofaScore id must never collapse onto an earlier fixture.
        resolution = resolve_match(
            identity,
            teams,
            leagues,
            [candidate for candidate in existing if candidate.source != SOURCE],
        )
        match = resolution.existing_match if resolution is not None else None
        created = match is None
    if match is None:
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
    payload = _payload(event, home_team, away_team)
    digest = _fingerprint(payload)
    latest_digest = session.scalar(
        select(MatchSnapshot.sha256)
        .where(MatchSnapshot.match_id == match.id, MatchSnapshot.source == SOURCE)
        .order_by(MatchSnapshot.observed_at.desc(), MatchSnapshot.id.desc())
        .limit(1)
    )
    if latest_digest != digest:
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
        policy = SofaScorePolicy(engine, settings)
        policy.check()
        source._POLICY = policy
        source._BLOCK_ERROR = None
        source.restore_checkpoint(policy.read().get("checkpoint"))
        try:
            return _sync_sofascore(engine, settings)
        finally:
            try:
                source.idle_browser()
                policy.checkpoint(source.checkpoint())
            finally:
                source._POLICY = None
                source._BLOCK_ERROR = None


def _sync_sofascore(engine: Engine, settings: Settings) -> UUID:
    run_id = start_run(engine, SOURCE, "days:-7..+7")
    started_at = datetime.now(UTC)
    try:
        with Session(engine) as session:
            known_stable_ids = _known_stable_event_ids(session, started_at, settings)
            _restore_known_links(session, started_at)
        blocked: SofaScoreBlocked | None = None
        try:
            events = scrape(settings, known_stable_ids=known_stable_ids)
            if source._POLICY is not None:
                source._POLICY.check()
        except SofaScoreBlocked as error:
            # Publish observations completed before a later source refusal.
            # Never count old cache entries as newly fetched matches.
            blocked = error
            events = list(source._STATE.fresh or [])
        observed_at = datetime.now(UTC)
        with Session(engine) as session, session.begin():
            session.execute(select(func.pg_advisory_xact_lock(CATALOG_WRITE_LOCK_ID)))
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
                    observed_at,
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
            run.finished_at = datetime.now(UTC)
            run.details = details
        source._STATE.fresh = []
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
                match_details = sync_oracle_match_details(
                    engine, match_ids=match_ids, source_timezone=settings.oracle_date_timezone
                )
            except Exception as error:
                match_details = {"status": "failed", "error": type(error).__name__}
                logger.exception("Oracle match detail projection failed after SofaScore sync")
            with Session(engine) as session, session.begin():
                run = session.get(IngestionRun, run_id)
                assert run is not None
                run.details = {**details, "matchDetails": match_details}
        if blocked is not None:
            raise blocked
        if source._POLICY is not None and events:
            source._POLICY.healthy()
        return run_id
    except Exception as error:
        # If publication failed, the cache must not suppress another attempt.
        for event in source._STATE.fresh or []:
            (source._STATE.event_fetched_at or {}).pop(event.source_id, None)
            # Unpublished completed maps must not suppress their next DOM read.
            (source._STATE.events or {}).pop(event.source_id, None)
        with Session(engine) as session, session.begin():
            run = session.get(IngestionRun, run_id)
            assert run is not None
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.error = str(error) if isinstance(error, SofaScoreBlocked) else type(error).__name__
            if isinstance(error, SofaScoreBlocked):
                run.details = {
                    **run.details,
                    "blocked": True,
                    "reason": error.reason,
                    "httpStatus": error.status,
                    "retryAt": error.retry_at,
                }
        if isinstance(error, SofaScoreBlocked):
            raise
        detail = str(error) if isinstance(error, SofaScoreBlocked) else type(error).__name__
        raise RuntimeError(f"SofaScore collection failed: {detail}") from None
