"""Transactional LoLTV identity reconciliation and immutable publication."""

import copy
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from metiquo_core.catalog import CATALOG_WRITE_LOCK_ID
from metiquo_core.models import EsportMatch, League, MatchSnapshot, MatchSourceLink, Team
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from metiquo_worker.matching import (
    MatchIdentity,
    MatchResolution,
    normalize_name,
    resolve_match,
    resolve_team,
    serializable_source_names,
)
from metiquo_worker.reconciliation import lock_identities, reconcile_in_session
from metiquo_worker.sources.loltv import SOURCE, LoltvEvent, image_url

COMPETITION_PHASE_SUFFIX = re.compile(
    r"\s+(?:regular season|playoffs?|play[ -]?ins?|group stage|qualifiers?|promotion)$"
)


def _source_key(kind: str, value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return f"loltv:{kind}:{normalized or 'unknown'}"


def _competition_base_name(value: str) -> str:
    normalized = normalize_name(value)
    normalized = re.sub(r"\s+20\d{2}\b", "", normalized)
    normalized = re.sub(
        r"\s+(?:(?:spring|summer|winter|fall|autumn)(?:\s+split)?|split\s+\d+)$", "", normalized
    )
    normalized = re.sub(r"\s+(?:group|groupe)\s+[a-z0-9]+$", "", normalized).strip()
    return COMPETITION_PHASE_SUFFIX.sub("", normalized).strip()


def _competition_brand(event: LoltvEvent, leagues: list[League]) -> League | None:
    return _competition_brand_from_source(event.competition, event.payload, leagues)


def _competition_brand_from_source(
    name: str, payload: dict[str, object], leagues: list[League]
) -> League | None:
    event_name = normalize_name(name)
    event_base_name = _competition_base_name(name)
    names = {event_base_name}
    raw = payload.get("sourceMatch")
    stage = raw.get("stage") if isinstance(raw, dict) else None
    tournament = stage.get("tournament") if isinstance(stage, dict) else None
    logo = image_url(tournament.get("image")) if isinstance(tournament, dict) else ""
    official = [
        candidate for candidate in leagues if not candidate.id.startswith(("loltv:", "sofascore:"))
    ]
    same_logo = [
        candidate
        for candidate in official
        if logo and image_url(candidate.data.get("sourceImage")) == logo
    ]
    if len(same_logo) == 1:
        return same_logo[0]
    # Prefer the sourced catalogue brand over a stage with the same label.
    for candidate in sorted(
        leagues,
        key=lambda item: (
            item.id.startswith(("loltv:", "sofascore:")),
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


def _ensure_competition(session: Session, event: LoltvEvent) -> League:
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
        # LoLTV's tournament object often has no image. Refresh an already
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
    event: LoltvEvent,
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
                "leagueAssignment": "participation",
                "participationEvidence": {
                    "provider": SOURCE,
                    "matchId": event.source_id,
                    "url": event.url,
                    "leagueId": competition_id,
                    "startsAt": event.starts_at.isoformat(),
                },
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


def _format(best_of: int | None) -> str | None:
    return f"BO{best_of}" if best_of in {1, 3, 5} else None


def _rendered_maps(event: LoltvEvent, home_team: Team, away_team: Team) -> list[dict[str, object]]:
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
                "sourceGameId": source_map.get("sourceGameId"),
                "sourceObservedAt": source_map.get("sourceObservedAt"),
                "status": source_map.get("status"),
                "durationSeconds": source_map.get("durationSeconds"),
                "durationSource": source_map.get("durationSource"),
                "winnerId": winner_id,
                "bans": bans,
                "sides": sides,
            }
        )
    return result


def _payload(event: LoltvEvent, home_team: Team, away_team: Team) -> dict[str, object]:
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
            "patch": event.payload.get("patch"),
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
    event: LoltvEvent,
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
    else:
        # A stable LoLTV event id always represents a schedulable match.
        # Resolution is only used to reuse a match from another provider; a
        # different LoLTV id must never collapse onto an earlier fixture.
        already_linked = set(
            session.scalars(
                select(MatchSourceLink.match_id).where(MatchSourceLink.provider == SOURCE)
            )
        )
        resolution = resolve_match(
            identity,
            teams,
            leagues,
            [
                candidate
                for candidate in existing
                if candidate.source != SOURCE and candidate.id not in already_linked
            ],
        )
        match = resolution.existing_match if resolution is not None else None
        created = match is None
    reversed_order = (
        match is not None and match.home_id == away_team.id and match.away_id == home_team.id
    )
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
        if event.best_of is not None:
            match.format = _format(event.best_of)
        match.league_id = competition.id
        if not reversed_order:
            match.home_id = home_team.id
            match.away_id = away_team.id

    names = serializable_source_names(identity)
    names.update(
        {
            "competitionSourceId": event.competition_source_id,
            "homeSourceId": event.home_source_id,
            "awaySourceId": event.away_source_id,
            "resolution": resolution.reason if resolution is not None else "source-id",
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
    if reversed_order:
        for field in ("currentScore", "seriesScore"):
            score = payload.get(field)
            if isinstance(score, dict):
                payload[field] = {"home": score["away"], "away": score["home"]}
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


def _publish_events(engine: Engine, events: list[LoltvEvent]) -> tuple[int, int]:
    if not events:
        return 0, 0
    observed_at = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        lock_identities(session)
        session.execute(select(func.pg_advisory_xact_lock(CATALOG_WRITE_LOCK_ID)))
        teams = list(session.scalars(select(Team)).all())
        leagues = list(session.scalars(select(League)).all())
        existing = list(
            session.scalars(
                select(EsportMatch).where(
                    EsportMatch.starts_at
                    >= min(event.starts_at for event in events) - timedelta(hours=72),
                    EsportMatch.starts_at
                    <= max(event.starts_at for event in events) + timedelta(hours=72),
                )
            ).all()
        )
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
        reconcile_in_session(session)
    return matched, created
