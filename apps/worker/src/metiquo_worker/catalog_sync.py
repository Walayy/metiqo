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
from metiquo_core.catalog import CATALOG_LOCK_ID, import_catalog
from metiquo_core.config import Settings
from metiquo_core.contracts import Catalog, LeagueData, TeamData
from metiquo_core.models import CatalogMetadata, CatalogVersion, IngestionRun
from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session

from metiquo_worker.artifacts import store_bytes
from metiquo_worker.catalog_images import fetch_image, read_response
from metiquo_worker.jobs import fail_run, source_lock, start_run
from metiquo_worker.sources.lol import ROOT_URL, SOURCE, Reference, parse_page, text

logger = logging.getLogger(__name__)
LOCK_ID = CATALOG_LOCK_ID


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
    client: httpx.Client, document: dict[str, object], cache: dict[str, object], settings: Settings
) -> dict[str, object]:
    catalog = Catalog.model_validate(document["catalog"])
    assets: list[LeagueData | TeamData] = [*catalog.leagues, *catalog.teams]
    urls = sorted({asset.source_image for asset in assets if asset.source_image})

    def fetch(url: str) -> tuple[str, dict[str, object]]:
        previous = cache.get(url, {})
        item = cast(dict[str, object], previous) if isinstance(previous, dict) else {}
        try:
            return url, fetch_image(client, url, item, settings)
        except Exception as error:
            logger.error("LoL logo failed: %s (%s: %s)", url, type(error).__name__, error)
            raise

    with ThreadPoolExecutor(max_workers=6) as executor:
        images = dict(executor.map(fetch, urls))
    for asset in assets:
        if asset.source_image:
            asset.image = f"/api/v1/catalog/logos/{images[asset.source_image]['sha256']}.webp"
    document["catalog"] = catalog.model_dump(mode="json", by_alias=True)
    document["images"] = [
        {key: value for key, value in item.items() if key not in ("etag", "lastModified")}
        for item in images.values()
    ]
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
                        len(current.leagues) < len(previous_catalog.leagues) * 0.8
                        or len(current.teams) < len(previous_catalog.teams) * 0.8
                    )
                ):
                    raise ValueError(
                        "Riot coverage dropped by more than 20%; inspect source before publication"
                    )
                stage = "logos"
                images = attach_images(client, document, cache, settings)
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
