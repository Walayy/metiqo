import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from metiquo_api.main import create_app
from metiquo_core import cli as admin_cli
from metiquo_core.models import CatalogMetadata, CatalogVersion, IngestionRun, League, Team
from metiquo_worker import catalog_sync
from metiquo_worker.catalog_sync import LOCK_ID, attach_images, publish
from metiquo_worker.cli import catalog_due
from metiquo_worker.ingestion import CollectionBusy, collection_lock
from metiquo_worker.jobs import source_lock, start_run
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_lol_catalog import png, source_document

pytestmark = pytest.mark.integration


def prepared(settings):
    document = source_document()
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=png()))
    ) as client:
        cache = attach_images(client, document, {}, settings)
    return document, cache


def test_publication_is_idempotent_and_api_reads_exact_snapshot(database):
    engine, settings = database
    document, cache = prepared(settings)
    assert catalog_due(engine, settings)
    for _ in range(2):
        run_id = start_run(engine, "lol-esports", "all")
        with Session(engine) as session, session.begin():
            summary = publish(session, document, cache, [], run_id)
    assert summary["changed"] is False
    assert not catalog_due(engine, settings)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CatalogVersion)) == 1
    with TestClient(create_app(settings)) as client:
        catalog = client.get("/api/v1/catalog").json()
        assert catalog == document["catalog"]
        logo = client.get(catalog["teams"][0]["image"])
        assert logo.status_code == 200 and logo.headers["content-type"] == "image/webp"
        cached = client.get(
            catalog["teams"][0]["image"], headers={"If-None-Match": logo.headers["etag"]}
        )
        assert cached.status_code == 304
        assert client.get("/api/v1/catalog/logos/not-a-hash.webp").status_code == 404
        reference = client.get("/api/v1/sources/lol-esports/reference").json()
        assert reference["versionId"] == summary["versionId"]
        assert reference["document"]["affiliations"] == document["affiliations"]
    with Session(engine) as session, session.begin():
        session.get(CatalogMetadata, 1).checked_at = datetime.now(UTC) - timedelta(days=2)
    assert catalog_due(engine, settings)


def test_failed_collection_preserves_previous_catalog_and_logos(database, monkeypatch):
    engine, settings = database
    document, cache = prepared(settings)
    run_id = start_run(engine, "lol-esports", "all")
    with Session(engine) as session, session.begin():
        previous = publish(session, document, cache, [], run_id)

    def fail(*_):
        raise ValueError("Riot source changed")

    monkeypatch.setattr(catalog_sync, "discover_catalog", fail)
    with pytest.raises(RuntimeError, match="discovery"):
        catalog_sync.sync_catalog(engine, settings)
    with Session(engine) as session:
        assert str(session.get(CatalogMetadata, 1).active_version_id) == previous["versionId"]
        failed = session.scalar(select(IngestionRun).where(IngestionRun.status == "failed"))
        assert failed.error == "discovery: ValueError"
    with TestClient(create_app(settings)) as client:
        assert client.get(document["catalog"]["teams"][0]["image"]).status_code == 200


def test_api_projects_supplemental_source_identities_onto_public_contract(database):
    engine, settings = database
    document, cache = prepared(settings)
    run_id = start_run(engine, "lol-esports", "all")
    with Session(engine) as session, session.begin():
        publish(session, document, cache, [], run_id)
        league_id = "sofascore:tournament:90739"
        session.add(
            League(
                id=league_id,
                data={
                    "id": league_id,
                    "slug": "vcs",
                    "name": "VCS",
                    "region": "INTERNATIONAL",
                    "image": "",
                    "sourceImage": "https://example.com/vcs.png",
                    "tier": "international",
                    "sourceId": "90739",
                },
            )
        )
        session.add(
            Team(
                id="sofascore:team:1173944",
                league_id=league_id,
                data={
                    "id": "sofascore:team:1173944",
                    "name": "Team Secret Whales",
                    "code": "",
                    "slug": "team-secret-whales",
                    "leagueId": league_id,
                    "image": "",
                    "sourceImage": "https://example.com/team.png",
                    "sourceId": "1173944",
                },
            )
        )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/catalog")

    assert response.status_code == 200
    catalog = response.json()
    league = next(item for item in catalog["leagues"] if item["id"] == league_id)
    team = next(item for item in catalog["teams"] if item["id"] == "sofascore:team:1173944")
    assert "sourceId" not in league
    assert "sourceId" not in team


def test_rollback_retains_previous_pointer_and_old_version_remains_readable(database):
    engine, settings = database
    document, cache = prepared(settings)
    first_run = start_run(engine, "lol-esports", "all")
    with Session(engine) as session, session.begin():
        first = publish(session, document, cache, [], first_run)
    document["catalog"]["teams"][0]["name"] = "Renamed team"
    second_run = start_run(engine, "lol-esports", "all")
    with pytest.raises(RuntimeError), Session(engine) as session, session.begin():
        publish(session, document, cache, [], second_run)
        session.flush()
        raise RuntimeError("Interrupted before commit")
    with Session(engine) as session:
        assert str(session.get(CatalogMetadata, 1).active_version_id) == first["versionId"]
        assert session.scalar(select(func.count()).select_from(CatalogVersion)) == 1
    with Session(engine) as session, session.begin():
        publish(session, document, cache, [], second_run)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/catalog").json()["teams"][0]["name"] == "Renamed team"
        old = client.get(
            "/api/v1/sources/lol-esports/reference", params={"versionId": first["versionId"]}
        )
        assert old.json()["document"]["catalog"]["teams"][0]["name"] == "Primary team"


def test_collectors_have_independent_locks_but_same_source_is_exclusive(database):
    engine, _ = database
    with collection_lock(engine), source_lock(engine, LOCK_ID):
        with pytest.raises(CollectionBusy), source_lock(engine, LOCK_ID):
            pytest.fail("Catalog collection must be exclusive")


def test_legacy_import_cannot_replace_catalog_during_collection(database, monkeypatch, tmp_path):
    engine, _ = database
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(source_document()["catalog"]), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["metiquo-admin", "catalog-import", str(path)])
    with source_lock(engine, LOCK_ID), pytest.raises(SystemExit, match="Catalog busy"):
        admin_cli.main()
