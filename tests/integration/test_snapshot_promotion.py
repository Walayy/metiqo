"""Commit unique du snapshot, du pointeur courant et du run d'ingestion."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.manifest import SnapshotManifest
from metiquo.ingestion.object_store import FilesystemObjectStore, StoredObject
from metiquo.ingestion.promotion import SnapshotPromotionService
from metiquo.ingestion.quarantine import SnapshotReader
from metiquo.ingestion.source_errors import AtomicPromotionFailed

ROOT = Path(__file__).resolve().parents[2]
INSTANT = datetime(2026, 9, 5, 23, tzinfo=UTC)


def alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


def _seed_catalog_and_run(connection: Connection) -> tuple[UUID, UUID, UUID, str]:
    catalog_id = uuid4()
    run_id = uuid4()
    old_snapshot_id = uuid4()
    unique = catalog_id.hex
    drive_file_id = f"drive-{unique}"
    connection.execute(
        text(
            """
            INSERT INTO raw.source_catalog (
              id, provider, dataset, season_year, landing_page, drive_file_id,
              source_name, origin, status, discovered_at
            ) VALUES (
              :catalog_id, 'oracles_elixir', :dataset, 2026,
              'https://oracleselixir.com/tools/downloads', :drive_file_id,
              '2026_LoL_esports_match_data_from_OraclesElixir.csv',
              'discovered', 'active', :instant
            )
            """
        ),
        {
            "catalog_id": catalog_id,
            "dataset": f"league-of-legends-{unique}",
            "drive_file_id": drive_file_id,
            "instant": INSTANT,
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO raw.snapshots (
              id, source_catalog_id, year, source_file_id, status, sha256,
              byte_size, content_type, object_key, received_at, validated_at
            ) VALUES (
              :snapshot_id, :catalog_id, 2026, :drive_file_id, 'validated', :sha256,
              1, 'text/csv', :object_key, :instant, :instant
            )
            """
        ),
        {
            "snapshot_id": old_snapshot_id,
            "catalog_id": catalog_id,
            "drive_file_id": drive_file_id,
            "sha256": unique * 2,
            "object_key": f"year=2026/sha256={unique * 2}/source.csv",
            "instant": INSTANT,
        },
    )
    connection.execute(
        text(
            "UPDATE raw.source_catalog SET current_snapshot_id = :snapshot_id "
            "WHERE id = :catalog_id"
        ),
        {"snapshot_id": old_snapshot_id, "catalog_id": catalog_id},
    )
    connection.execute(
        text(
            """
            INSERT INTO raw.ingestion_runs (
              id, source_catalog_id, run_kind, status, attempt,
              transport, correlation_id, started_at, counters
            ) VALUES (
              :run_id, :catalog_id, 'sync', 'running', 1,
              'local-fixture', :correlation_id, :instant, '{"downloaded": 1}'::jsonb
            )
            """
        ),
        {
            "run_id": run_id,
            "catalog_id": catalog_id,
            "correlation_id": f"promotion-{unique}",
            "instant": INSTANT,
        },
    )
    return catalog_id, run_id, old_snapshot_id, drive_file_id


def _stored_and_manifest(
    tmp_path: Path,
    drive_file_id: str,
) -> tuple[FilesystemObjectStore, StoredObject, SnapshotManifest]:
    payload = f"gameid,side,result\n{drive_file_id},Blue,1\n".encode()
    digest = hashlib.sha256(payload).hexdigest()
    store = FilesystemObjectStore(tmp_path / "object-store")
    manifest = SnapshotManifest(
        provider="oracles_elixir",
        season_year=2026,
        drive_file_id=drive_file_id,
        requested_at=INSTANT,
        downloaded_at=INSTANT,
        transport="local-fixture",
        byte_size=len(payload),
        sha256=digest,
        content_type_observed="text/csv",
        compression="none",
        encoding="utf-8",
        delimiter=",",
        schema_fingerprint="a" * 64,
        row_count=1,
        min_event_date=None,
        max_event_date=None,
        quality_status="passed",
        quality={"blocking": 0},
        ingestion_code_version="test-commit",
    )
    stored = store.put_source(
        year=2026,
        chunks=[payload],
        source_kind="csv",
        manifest=manifest.to_dict(),
        quality_report={"status": "passed", "blocking": 0},
    )
    return store, stored, manifest


def _assert_uncommitted_state(
    engine: Engine,
    catalog_id: UUID,
    run_id: UUID,
    old_snapshot_id: UUID,
    new_sha256: str,
) -> None:
    with engine.connect() as observer:
        pointer = observer.execute(
            text("SELECT current_snapshot_id FROM raw.source_catalog WHERE id = :id"),
            {"id": catalog_id},
        ).scalar_one()
        run_status = observer.execute(
            text("SELECT status FROM raw.ingestion_runs WHERE id = :id"),
            {"id": run_id},
        ).scalar_one()
        visible_new_snapshots = observer.execute(
            text(
                "SELECT count(*) FROM raw.snapshots "
                "WHERE source_catalog_id = :catalog_id AND sha256 = :sha256"
            ),
            {"catalog_id": catalog_id, "sha256": new_sha256},
        ).scalar_one()
    assert pointer == old_snapshot_id
    assert run_status == "running"
    assert visible_new_snapshots == 0


@pytest.mark.integration
def test_promotion_publishes_pointer_and_succeeds_run_only_after_commit(
    postgresql_url: str,
    tmp_path: Path,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with engine.begin() as connection:
        catalog_id, run_id, old_snapshot_id, drive_file_id = _seed_catalog_and_run(connection)
    store, stored, manifest = _stored_and_manifest(tmp_path, drive_file_id)
    observed_before_commit = False

    def observe_before_commit(_connection: Connection) -> None:
        nonlocal observed_before_commit
        _assert_uncommitted_state(
            engine,
            catalog_id,
            run_id,
            old_snapshot_id,
            manifest.sha256,
        )
        observed_before_commit = True

    result = SnapshotPromotionService(
        engine=engine,
        object_store=store,
        clock=FixedClock(UtcInstant(INSTANT)),
        before_commit=observe_before_commit,
    ).promote(
        source_catalog_id=catalog_id,
        run_id=run_id,
        stored=stored,
        manifest=manifest,
    )

    assert observed_before_commit is True
    assert result.previous_snapshot_id == old_snapshot_id
    assert result.reused is False
    with engine.connect() as connection:
        current = SnapshotReader(connection).current(catalog_id)
        assert current is not None
        assert current.id == result.snapshot_id
        run = (
            connection.execute(
                text(
                    "SELECT status, snapshot_id, finished_at, counters "
                    "FROM raw.ingestion_runs WHERE id = :id"
                ),
                {"id": run_id},
            )
            .mappings()
            .one()
        )
        assert run["status"] == "succeeded"
        assert run["snapshot_id"] == result.snapshot_id
        assert run["finished_at"] == INSTANT
        assert run["counters"] == {
            "downloaded": 1,
            "snapshotPromoted": 1,
            "snapshotReused": 0,
        }
    engine.dispose()


@pytest.mark.integration
def test_fault_before_commit_rolls_back_pointer_snapshot_and_run(
    postgresql_url: str,
    tmp_path: Path,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with engine.begin() as connection:
        catalog_id, run_id, old_snapshot_id, drive_file_id = _seed_catalog_and_run(connection)
    store, stored, manifest = _stored_and_manifest(tmp_path, drive_file_id)

    def fail_before_commit(_connection: Connection) -> None:
        _assert_uncommitted_state(
            engine,
            catalog_id,
            run_id,
            old_snapshot_id,
            manifest.sha256,
        )
        raise RuntimeError("injected crash")

    with pytest.raises(AtomicPromotionFailed) as captured:
        SnapshotPromotionService(
            engine=engine,
            object_store=store,
            clock=FixedClock(UtcInstant(INSTANT)),
            before_commit=fail_before_commit,
        ).promote(
            source_catalog_id=catalog_id,
            run_id=run_id,
            stored=stored,
            manifest=manifest,
        )

    assert captured.value.context == {
        "operation": "transaction",
        "errorType": "RuntimeError",
    }
    _assert_uncommitted_state(
        engine,
        catalog_id,
        run_id,
        old_snapshot_id,
        manifest.sha256,
    )
    assert stored.source_path.is_file()
    engine.dispose()
