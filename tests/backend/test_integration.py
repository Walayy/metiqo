import shutil
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from metiquo_api.main import create_app
from metiquo_core.catalog import import_catalog
from metiquo_core.contracts import Catalog, Opportunities, Quote
from metiquo_core.models import (
    Dataset,
    DatasetVersion,
    EsportMatch,
    IngestionRun,
    Market,
    MatchSnapshot,
    MatchSourceLink,
    OddsObservation,
    OracleRow,
    ProbabilityEstimate,
)
from metiquo_core.odds import record_quote
from metiquo_worker import ingestion
from metiquo_worker.archive import validate_archive
from metiquo_worker.cli import due_scope
from metiquo_worker.ingestion import CollectionBusy, collection_lock, import_files
from psycopg import DataError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_archive import csv_bytes, make_archive

pytestmark = pytest.mark.integration


def test_import_idempotence_atomicity_and_version_pagination(database, tmp_path):
    engine, settings = database
    archive, source = make_archive(tmp_path / "source")
    files = validate_archive(archive, [source], archive.parent, 100_000)
    run_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(IngestionRun(id=run_id, source="oracles-elixir", scope="2026"))
        session.flush()
        assert import_files(session, files, settings.artifact_dir, run_id)["imported"] == 1
    with Session(engine) as session, session.begin():
        assert import_files(session, files, settings.artifact_dir, run_id)["unchanged"] == 1
        assert session.scalar(select(func.count()).select_from(OracleRow)) == 2
        assert session.scalar(select(func.count()).select_from(DatasetVersion)) == 1
    with pytest.raises(RuntimeError), Session(engine) as session, session.begin():
        session.get(Dataset, "oracles-elixir:2026").active_version_id = None
        session.flush()
        raise RuntimeError("Interrupted before publication")
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/sources/oracles-elixir/datasets/2026/rows?limit=1")
        assert response.status_code == 200
        first = response.json()
        assert first["items"][0]["data"]["year"] == "2027"
        assert first["nextAfter"] == 1
        assert (
            client.get("/api/v1/sources/oracles-elixir/datasets/2026/rows?after=1").status_code
            == 422
        )
        second = client.get(
            "/api/v1/sources/oracles-elixir/datasets/2026/rows",
            params={"after": 1, "versionId": first["versionId"]},
        ).json()
        assert second["nextAfter"] is None and second["items"][0]["rowNumber"] == 2
        download = client.get("/api/v1/sources/oracles-elixir/datasets/2026/file")
        assert download.content == files[0].path.read_bytes()


def test_failure_is_recorded_without_replacing_active_data(database, tmp_path, monkeypatch):
    engine, settings = database
    archive, source = make_archive(tmp_path / "original")
    files = validate_archive(archive, [source], archive.parent, 100_000)
    run_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            IngestionRun(id=run_id, source="oracles-elixir", scope="all", status="succeeded")
        )
        session.flush()
        import_files(session, files, settings.artifact_dir, run_id)
    monkeypatch.setattr(ingestion, "discover", lambda _: [source])
    monkeypatch.setattr(ingestion, "select_files", lambda inventory, _: inventory)
    monkeypatch.setattr(ingestion, "export_url", lambda *_: "unused")
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"<html>Quota exceeded</html>")
    monkeypatch.setattr(
        ingestion, "download_export", lambda _, target, __: shutil.copy(broken, target)
    )
    with pytest.raises(RuntimeError, match="validation"):
        ingestion.collect(engine, settings)
    with Session(engine) as session:
        dataset = session.get(Dataset, "oracles-elixir:2026")
        assert dataset.active_version_id is not None
        assert session.scalar(select(func.count()).select_from(OracleRow)) == 2
        failed = session.scalar(select(IngestionRun).where(IngestionRun.status == "failed"))
        assert failed.error == "validation: BadZipFile"


def test_parallel_workers_share_database_lock(database):
    engine, _ = database
    with collection_lock(engine), pytest.raises(CollectionBusy), collection_lock(engine):
        pytest.fail("Second collector must not acquire the same lock")
    with collection_lock(engine):
        pass


def test_second_file_database_failure_rolls_back_entire_publication(database, tmp_path):
    engine, settings = database
    archive, source = make_archive(tmp_path / "original")
    originals = validate_archive(archive, [source], archive.parent, 100_000)
    run_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(IngestionRun(id=run_id, source="oracles-elixir", scope="all"))
        session.flush()
        import_files(session, originals, settings.artifact_dir, run_id)
    changed_archive, changed_source = make_archive(
        tmp_path / "changed", csv_bytes().replace(b"game-1", b"game-2")
    )
    invalid_archive, invalid_source = make_archive(
        tmp_path / "invalid", csv_bytes().replace(b"game-1", b"game\x00x"), year=2025
    )
    changed = validate_archive(changed_archive, [changed_source], changed_archive.parent, 100_000)
    invalid = validate_archive(invalid_archive, [invalid_source], invalid_archive.parent, 100_000)
    with pytest.raises(DataError), Session(engine) as session, session.begin():
        import_files(session, changed + invalid, settings.artifact_dir, run_id)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(DatasetVersion)) == 1
        assert session.scalar(select(func.count()).select_from(OracleRow)) == 2
        assert session.get(Dataset, "oracles-elixir:2025") is None
        active = session.get(Dataset, "oracles-elixir:2026").active_version_id
        assert session.get(DatasetVersion, active).sha256 == originals[0].sha256


def catalog_fixture():
    return Catalog.model_validate(
        {
            "retrievedAt": "2026-09-14",
            "source": "https://lolesports.com/en-US",
            "leagues": [
                {
                    "id": "league1",
                    "slug": "l1",
                    "name": "League",
                    "region": "EUROPE",
                    "image": "",
                    "sourceImage": "",
                    "tier": "regional",
                }
            ],
            "teams": [
                {
                    "id": f"team{i}",
                    "name": f"Team {i}",
                    "code": f"T{i}",
                    "slug": f"team{i}",
                    "leagueId": "league1",
                    "image": "",
                    "sourceImage": "",
                }
                for i in (1, 2)
            ],
        }
    )


def test_historical_refresh_does_not_delay_current_year(database, tmp_path):
    engine, settings = database
    now = datetime.now(UTC)
    archive, source = make_archive(tmp_path / "original")
    files = validate_archive(archive, [source], archive.parent, 100_000)
    run_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            IngestionRun(
                id=run_id,
                source="oracles-elixir",
                scope="all",
                status="succeeded",
                finished_at=now - timedelta(days=1),
            )
        )
        session.flush()
        import_files(session, files, settings.artifact_dir, run_id)
        session.get(Dataset, "oracles-elixir:2026").checked_at = now - timedelta(hours=7)
        session.add(
            IngestionRun(source="oracles-elixir", scope="2014", status="succeeded", finished_at=now)
        )
    assert due_scope(engine, settings) == (True, False)


def test_api_contract_quotes_and_estimate_expiry(database):
    engine, settings = database
    now = datetime.now(UTC)
    market_id, match_id = uuid4(), uuid4()
    with Session(engine) as session, session.begin():
        import_catalog(session, catalog_fixture())
        session.flush()
        session.add(
            EsportMatch(
                id=match_id,
                source="test",
                source_id="test1",
                league_id="league1",
                home_id="team1",
                away_id="team2",
                starts_at=now + timedelta(days=1),
                registered_at=now - timedelta(hours=1),
                format="BO3",
            )
        )
        session.flush()
        session.add(
            MatchSourceLink(
                match_id=match_id,
                provider="sofascore",
                source_id="test1",
                source_url="https://example.test/match/test1",
                first_seen_at=now - timedelta(hours=1),
                last_seen_at=now,
            )
        )
        session.add(
            MatchSnapshot(
                match_id=match_id,
                source="sofascore",
                source_id="test1",
                source_url="https://example.test/match/test1",
                status="scheduled",
                observed_at=now - timedelta(minutes=20),
                sha256="a" * 64,
                payload={"format": "BO3", "maps": [], "status": "scheduled"},
            )
        )
        session.flush()
        session.add(
            Market(
                id=market_id,
                match_id=match_id,
                source_id="market1",
                kind="winner",
                pick_id="team1",
                active=True,
            )
        )
        session.flush()
        first = Quote(recorded_at=now - timedelta(minutes=1), odds=2.1)
        record_quote(session, market_id, first)
        session.flush()
        record_quote(session, market_id, first)
        record_quote(session, market_id, Quote(recorded_at=now, odds=1.8))
        session.add(
            ProbabilityEstimate(
                market_id=market_id,
                estimated_at=now,
                valid_until=now + timedelta(hours=1),
                probability=Decimal("0.6"),
                model_version="test-only",
            )
        )
    with Session(engine) as session, session.begin():
        with pytest.raises(ValueError, match="Conflicting"):
            record_quote(session, market_id, Quote(recorded_at=now, odds=2))
        assert session.scalar(select(func.count()).select_from(OddsObservation)) == 2
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/ready").status_code == 200
        Catalog.model_validate(client.get("/api/v1/catalog").json())
        response = client.get("/api/v1/opportunities")
        body = Opportunities.model_validate(response.json())
        assert len(body.items) == 1
        assert [quote.odds for quote in body.items[0].history] == [2.1, 1.8]
        schedule = client.get("/api/v1/matches").json()["items"]
        assert len(schedule) == 1
        assert schedule[0]["id"] == str(match_id)
        assert schedule[0]["status"] == "scheduled"
        assert schedule[0]["maps"] == []
        assert schedule[0]["updatedAt"] == now.isoformat().replace("+00:00", "Z")
        assert schedule[0]["patch"] is None
        assert client.get("/api/v1/performance").json()["items"] == []
        with Session(engine) as session, session.begin():
            estimate = session.get(ProbabilityEstimate, (market_id, now))
            estimate.estimated_at = now - timedelta(minutes=2)
            estimate.valid_until = now - timedelta(minutes=1)
        assert client.get("/api/v1/opportunities").json()["items"] == []
        assert len(client.get("/api/v1/matches").json()["items"]) == 1
