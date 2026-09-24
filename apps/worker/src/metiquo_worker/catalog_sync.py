import copy
import gzip
import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import httpx
from metiquo_core.catalog import CATALOG_LOCK_ID, import_catalog, other_game_identities
from metiquo_core.catalog_logos import fill_team_logos
from metiquo_core.config import Settings
from metiquo_core.contracts import Catalog, LeagueData, TeamData
from metiquo_core.models import (
    CatalogMetadata,
    CatalogVersion,
    EsportMatch,
    IngestionRun,
    League,
    MatchSnapshot,
    Team,
)
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from metiquo_worker.artifacts import store_bytes
from metiquo_worker.catalog_images import cache_valid, fetch_image, read_response
from metiquo_worker.jobs import fail_run, source_lock, start_run
from metiquo_worker.loltv_policy import LoltvPolicy
from metiquo_worker.loltv_publication import _competition_brand_from_source
from metiquo_worker.sources.lol import ROOT_URL, SOURCE, Reference, parse_page, text

logger = logging.getLogger(__name__)
LOCK_ID = CATALOG_LOCK_ID
LEAGUE_FIELDS = {"id", "slug", "name", "region", "image", "sourceImage", "tier"}
TEAM_FIELDS = {"id", "name", "code", "slug", "leagueId", "image", "sourceImage"}


def retain_known_identities(
    document: dict[str, object],
    leagues: list[dict[str, object]],
    teams: list[dict[str, object]],
) -> None:
    """Keep valid historical/source identities absent from today's Riot pages.

    Riot pages are the primary discovery source, while teams already observed
    through another approved source remain useful for existing matches. They
    keep their explicit league relation and provenance; no new affiliation is
    inferred here.
    """
    catalog = cast(dict[str, object], document["catalog"])
    league_items = cast(list[dict[str, object]], catalog["leagues"])
    team_items = cast(list[dict[str, object]], catalog["teams"])
    known_leagues = {str(item["id"]) for item in league_items}
    known_teams = {str(item["id"]) for item in team_items}
    retained_leagues = 0
    retained_teams = 0
    for data in leagues:
        identity = data.get("id")
        if not isinstance(identity, str) or identity in known_leagues:
            continue
        try:
            item = LeagueData.model_validate(
                {key: value for key, value in data.items() if key in LEAGUE_FIELDS}
            ).model_dump(mode="json", by_alias=True)
        except Exception:
            continue
        league_items.append(item)
        known_leagues.add(identity)
        retained_leagues += 1
    for data in teams:
        identity = data.get("id")
        league_id = data.get("leagueId")
        if (
            not isinstance(identity, str)
            or identity in known_teams
            or not isinstance(league_id, str)
            or league_id not in known_leagues
        ):
            continue
        enriched = dict(data)
        if not enriched.get("sourceImage"):
            source_images = enriched.get("sourceImages")
            if isinstance(source_images, dict):
                live_images = source_images.get("loltv")
                if isinstance(live_images, list):
                    enriched["sourceImage"] = next(
                        (value for value in live_images if isinstance(value, str) and value), ""
                    )
        try:
            item = TeamData.model_validate(
                {key: value for key, value in enriched.items() if key in TEAM_FIELDS}
            ).model_dump(mode="json", by_alias=True)
        except Exception:
            continue
        team_items.append(item)
        known_teams.add(identity)
        retained_teams += 1
    league_items.sort(key=lambda item: str(item["id"]))
    team_items.sort(key=lambda item: str(item["id"]))
    coverage = document.get("coverage")
    if isinstance(coverage, dict):
        coverage["retainedKnownLeagues"] = retained_leagues
        coverage["retainedKnownTeams"] = retained_teams


def repair_known_brands(session: Session, leagues: list[League]) -> list[dict[str, object]]:
    """Reuse stored source parent metadata; no extra LoLTV navigation."""
    payloads = {
        league_id: payload
        for league_id, payload in session.execute(
            select(EsportMatch.league_id, MatchSnapshot.payload)
            .join(MatchSnapshot, MatchSnapshot.match_id == EsportMatch.id)
            .where(MatchSnapshot.source == "loltv")
            .distinct(EsportMatch.league_id)
            .order_by(
                EsportMatch.league_id, MatchSnapshot.observed_at.desc(), MatchSnapshot.id.desc()
            )
        ).all()
    }
    result = []
    for league in leagues:
        data = dict(league.data)
        brand = _competition_brand_from_source(
            str(data.get("name", "")), payloads.get(league.id, {}), leagues
        )
        if brand is not None and brand.id != league.id:
            for field in ("image", "sourceImage"):
                if not data.get(field) and brand.data.get(field):
                    data[field] = brand.data[field]
        result.append(data)
    return result


def discover_catalog(
    client: httpx.Client, settings: Settings
) -> tuple[Reference, list[dict[str, object]]]:
    reference = Reference()
    pages: list[dict[str, object]] = []
    pending = {ROOT_URL}
    visited: set[str] = set()
    while pending:
        url = min(pending)
        pending.remove(url)
        if len(visited) >= settings.catalog_max_pages:
            raise ValueError("Riot discovery exceeds page limit; refusing a partial publication")
        with client.stream("GET", url) as response:
            raw = read_response(response, settings.catalog_max_page_bytes)
        page = parse_page(raw.decode("utf-8"))
        reference.add_page(page, url)
        digest, path = store_bytes(
            settings.artifact_dir, "pages", gzip.compress(raw, mtime=0), "html.gz"
        )
        pages.append(
            {
                "url": url,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "artifactSha256": digest,
                "path": path,
                "retrievedAt": datetime.now(UTC).isoformat(),
            }
        )
        visited.add(url)
        pending.update(
            f"{ROOT_URL}/leagues/{text(league.get('slug'))}"
            for league in reference.leagues.values()
            if f"{ROOT_URL}/leagues/{text(league.get('slug'))}" not in visited
        )
        logger.info("LoL source page %s: %s", len(visited), url)
    return reference, pages


def attach_images(
    client: httpx.Client,
    document: dict[str, object],
    cache: dict[str, object],
    settings: Settings,
    policy: LoltvPolicy | None = None,
) -> dict[str, object]:
    catalog = Catalog.model_validate(document["catalog"])
    assets: list[LeagueData | TeamData] = [*catalog.leagues, *catalog.teams]
    urls = sorted({asset.source_image for asset in assets if asset.source_image})

    def fetch(url: str) -> tuple[str, dict[str, object] | None]:
        previous = cache.get(url, {})
        item = cast(dict[str, object], previous) if isinstance(previous, dict) else {}
        try:
            return url, fetch_image(client, url, item, settings, policy=policy)
        except Exception as error:
            logger.error("LoL logo failed: %s (%s: %s)", url, type(error).__name__, error)
            return (url, item) if cache_valid(settings.artifact_dir, item) else (url, None)

    with ThreadPoolExecutor(max_workers=6) as executor:
        images = {url: item for url, item in executor.map(fetch, urls) if item is not None}
    for asset in assets:
        if asset.source_image and asset.source_image in images:
            asset.image = f"/api/v1/catalog/logos/{images[asset.source_image]['sha256']}.webp"
    document["logoReuses"] = fill_team_logos(catalog.teams)
    document["catalog"] = catalog.model_dump(mode="json", by_alias=True)
    document["images"] = [
        {
            key: value
            for key, value in item.items()
            if key not in ("etag", "lastModified", "checkedAt")
        }
        for item in images.values()
    ]
    document["logoCoverage"] = {
        "leagues": len(catalog.leagues),
        "localLeagueLogos": sum(bool(league.image) for league in catalog.leagues),
        "missingLeagueIds": [league.id for league in catalog.leagues if not league.image],
        "teams": len(catalog.teams),
        "teamLogos": sum(bool(team.image) for team in catalog.teams),
        "missingTeamIds": [team.id for team in catalog.teams if not team.image],
    }
    return cast(dict[str, object], images)


def fingerprint(document: dict[str, object]) -> str:
    semantic = copy.deepcopy(document)
    catalog = cast(dict[str, object], semantic["catalog"])
    catalog.pop("retrievedAt", None)
    return hashlib.sha256(
        json.dumps(semantic, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def publish(
    session: Session,
    document: dict[str, object],
    cache: dict[str, object],
    pages: list[dict[str, object]],
    run_id: UUID,
) -> dict[str, object]:
    catalog = Catalog.model_validate(document["catalog"])
    digest = fingerprint(document)
    version = session.scalar(
        select(CatalogVersion).where(
            CatalogVersion.source == SOURCE, CatalogVersion.sha256 == digest
        )
    )
    changed = version is None
    now = datetime.now(UTC)
    if version is None:
        version = CatalogVersion(
            id=uuid4(),
            source=SOURCE,
            run_id=run_id,
            sha256=digest,
            retrieved_at=now,
            document=document,
        )
        session.add(version)
        session.flush()
    # Historical identities stay available to existing matches. The public snapshot
    # is read through one version pointer rather than several mutable table queries.
    import_catalog(session, catalog)
    session.flush()
    metadata = session.get(CatalogMetadata, 1)
    assert metadata is not None
    metadata.active_version_id = version.id
    metadata.retrieved_at = version.retrieved_at.date()
    metadata.checked_at = now
    metadata.image_cache = cache
    details: dict[str, object] = {
        "versionId": str(version.id),
        "sha256": digest,
        "changed": changed,
        "leagues": len(catalog.leagues),
        "teams": len(catalog.teams),
        "logos": len(cache),
        "pages": pages,
    }
    session.execute(
        update(IngestionRun)
        .where(IngestionRun.id == run_id)
        .values(status="succeeded", finished_at=func.now(), details=details)
    )
    return details


def sync_catalog(engine: Engine, settings: Settings, *, allow_coverage_drop: bool = False) -> UUID:
    if not settings.catalog_enabled:
        raise ValueError("LoL catalog collection is disabled")
    with source_lock(engine, LOCK_ID):
        run_id = start_run(engine, SOURCE, "all")
        stage = "discovery"
        try:
            with Session(engine) as session:
                metadata = session.get(CatalogMetadata, 1)
                cache = metadata.image_cache if metadata else {}
                excluded_leagues, excluded_teams = other_game_identities(session)
                known_leagues = repair_known_brands(
                    session,
                    [
                        item
                        for item in session.scalars(select(League)).all()
                        if item.id not in excluded_leagues
                    ],
                )
                known_teams = [
                    dict(item.data)
                    for item in session.scalars(select(Team)).all()
                    if item.id not in excluded_teams and item.league_id not in excluded_leagues
                ]
                previous = (
                    session.get(CatalogVersion, metadata.active_version_id)
                    if metadata and metadata.active_version_id
                    else None
                )
                previous_catalog = (
                    Catalog.model_validate(previous.document["catalog"]) if previous else None
                )
            with httpx.Client(
                timeout=settings.catalog_timeout_seconds,
                headers={"User-Agent": "Metiquo/0.1 catalog collector"},
            ) as client:
                reference, pages = discover_catalog(client, settings)
                document = reference.document(datetime.now(UTC).date().isoformat())
                current = Catalog.model_validate(document["catalog"])
                coverage = cast(dict[str, object], document["coverage"])
                coverage["discoveredLeagues"] = len(current.leagues)
                coverage["discoveredTeams"] = len(current.teams)
                previous_coverage = previous.document.get("coverage", {}) if previous else {}
                previous_coverage = previous_coverage if isinstance(previous_coverage, dict) else {}
                previous_leagues = previous_coverage.get("discoveredLeagues")
                previous_teams = previous_coverage.get("discoveredTeams")
                if previous_catalog:
                    if not isinstance(previous_leagues, int):
                        previous_leagues = sum(
                            not item.id.startswith(("sofascore:", "loltv:"))
                            for item in previous_catalog.leagues
                        )
                    if not isinstance(previous_teams, int):
                        previous_teams = sum(
                            not item.id.startswith(("sofascore:", "loltv:"))
                            for item in previous_catalog.teams
                        )
                with Session(engine) as session, session.begin():
                    session.execute(
                        update(IngestionRun)
                        .where(IngestionRun.id == run_id)
                        .values(
                            details={
                                "pages": pages,
                                "leagues": len(current.leagues),
                                "teams": len(current.teams),
                            }
                        )
                    )
                if (
                    not allow_coverage_drop
                    and previous_catalog
                    and (
                        len(current.leagues) < cast(int, previous_leagues) * 0.8
                        or len(current.teams) < cast(int, previous_teams) * 0.8
                    )
                ):
                    raise ValueError(
                        "Riot coverage dropped by more than 20%; inspect source before publication"
                    )
                retain_known_identities(document, known_leagues, known_teams)
                stage = "logos"
                images = attach_images(
                    client, document, cache, settings, LoltvPolicy(engine, settings)
                )
            stage = "database publication"
            with Session(engine) as session, session.begin():
                details = publish(session, document, images, pages, run_id)
            logger.info(
                "LoL catalog %s succeeded: %s leagues, %s teams, changed=%s",
                run_id,
                details["leagues"],
                details["teams"],
                details["changed"],
            )
            return run_id
        except Exception as error:
            message = fail_run(engine, run_id, stage, error)
            logger.error("LoL catalog %s failed: %s", run_id, message)
            raise RuntimeError(message) from None
