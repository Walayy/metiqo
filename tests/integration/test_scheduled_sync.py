"""Confirmation d'un hash inchangé sans transfert ni mutation du snapshot validé."""

import logging
from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from metiquo.contracts.enums import DataMode, FreshnessStatus
from metiquo.db.raw_models import IngestionRun, Snapshot
from metiquo.foundation.errors import BusinessError
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.freshness import FreshnessPolicy
from metiquo.ingestion.local_transports import LocalFixtureTransport
from metiquo.ingestion.operations import verify_snapshot
from metiquo.ingestion.raw_loader import RawTabularLoader
from metiquo.ingestion.sync import OracleElixirYearSync
from metiquo.ingestion.transport import SourceRef, TransportPolicy
from metiquo.repositories.postgres_admin import PostgresAdminRepository
from metiquo.worker.handlers import OracleSyncHandler
from metiquo.worker.queue import PostgresJobQueue
from metiquo.worker.runner import PostgresJobRunner
from tests.integration.test_backfill import _seed_catalogs
from tests.integration.test_job_queue import NOW
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _settings


@pytest.mark.integration
def test_scheduled_unchanged_check_refreshes_proof_without_redownload_or_snapshot_mutation(
    postgresql_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from metiquo.foundation.observability import JsonFormatter

    command.upgrade(alembic_config(postgresql_url), "head")
    caplog.handler.setFormatter(JsonFormatter())
    caplog.set_level("INFO", logger="metiquo.ingestion")
    logger = logging.getLogger("metiquo.ingestion")
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setattr(logger, "handlers", [caplog.handler])
    monkeypatch.setattr(logger, "propagate", False)
    engine = create_engine(postgresql_url)
    _seed_catalogs(engine, dataset="league_of_legends_match_data", years=range(2026, 2027))
    settings = _settings(postgresql_url, "mock").model_copy(update={"object_store_root": tmp_path})
    fixture = Path(__file__).resolve().parents[1] / "fixtures/oracles_elixir/dq_valid.csv"
    first = OracleElixirYearSync(
        engine=engine, settings=settings, clock=FixedClock(UtcInstant(NOW))
    ).sync_year(year=2026, policy=FreshnessPolicy(require_fresh=True), fixture_path=fixture)
    assert first.snapshot_id is not None
    assert f'"snapshot_id":"{first.snapshot_id}"' in caplog.text
    with Session(engine) as session:
        before = session.get(Snapshot, first.snapshot_id)
        assert before is not None
        validated_at, manifest = before.validated_at, before.manifest

    def no_download(*args: object, **kwargs: object) -> None:
        pytest.fail("Le checksum identique doit éviter le téléchargement")

    monkeypatch.setattr(LocalFixtureTransport, "download", no_download)
    later = NOW + timedelta(hours=4)
    report = OracleElixirYearSync(
        engine=engine, settings=settings, clock=FixedClock(UtcInstant(later))
    ).sync_year(
        year=2026,
        policy=FreshnessPolicy(require_fresh=True),
        fixture_path=fixture,
        check_unchanged=True,
    )
    assert report.snapshot_id == first.snapshot_id and report.load_run_id is None
    assert report.freshness.status is FreshnessStatus.FRESH and report.freshness.as_of == later
    health = PostgresAdminRepository(engine, FixedClock(UtcInstant(later))).list_data_sources()[0]
    assert health.last_success_at == later and health.age_seconds == 0
    stale = PostgresAdminRepository(
        engine, FixedClock(UtcInstant(later + timedelta(hours=4)))
    ).list_data_sources()[0]
    assert stale.freshness is FreshnessStatus.STALE
    with Session(engine) as session:
        after = session.get(Snapshot, first.snapshot_id)
        assert (
            after is not None and after.validated_at == validated_at and after.manifest == manifest
        )
        run = session.get(IngestionRun, report.run_id)
        assert run is not None and run.counters["metadataVerified"] is True
        assert len(session.scalars(select(Snapshot)).all()) == 1
    assert verify_snapshot(engine, settings, first.snapshot_id)["snapshotId"] == str(
        first.snapshot_id
    )

    def transports(
        self: OracleElixirYearSync, source: SourceRef, fixture_path: Path | None
    ) -> tuple[LocalFixtureTransport, ...]:
        return (
            LocalFixtureTransport(
                policy=TransportPolicy.from_settings(settings),
                fixtures={source.source_id: fixture},
                data_mode=DataMode.MOCK,
                clock=FixedClock(UtcInstant(later)),
            ),
        )

    monkeypatch.setattr(OracleElixirYearSync, "_transports", transports)
    queue = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(later)))
    for kind in ("oe.sync", "oe.deep"):
        job = queue.enqueue(kind, {"year": 2026}, key=kind, scope="oe:oracles_elixir:2026")
        runner = PostgresJobRunner(
            queue,
            {kind: OracleSyncHandler(engine, settings, deep=kind == "oe.deep")},
            owner="fixture-worker",
        )
        assert runner.run_once() and queue.get(job.job_id).status == "succeeded"
        assert queue.get(job.job_id).result["snapshotId"] == str(first.snapshot_id)
    with Session(engine) as session:
        stored = session.get(Snapshot, first.snapshot_id)
        assert stored is not None
        stored_hash = stored.sha256
    manifest_path = (
        tmp_path / "raw/oracles_elixir" / "year=2026" / f"sha256={stored_hash}" / "manifest.json"
    )
    manifest_path.write_text("{}", encoding="utf-8")
    with pytest.raises(BusinessError, match="manifeste"):
        verify_snapshot(engine, settings, first.snapshot_id)
    engine.dispose()


@pytest.mark.integration
def test_failure_after_snapshot_validation_cannot_report_sync_success(
    postgresql_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    _seed_catalogs(engine, dataset="league_of_legends_match_data", years=range(2026, 2027))
    settings = _settings(postgresql_url, "mock").model_copy(update={"object_store_root": tmp_path})

    def failed_load(*args: object, **kwargs: object) -> None:
        raise RuntimeError("late load failure")

    monkeypatch.setattr(RawTabularLoader, "load", failed_load)
    report = OracleElixirYearSync(
        engine=engine, settings=settings, clock=FixedClock(UtcInstant(NOW))
    ).sync_year(
        year=2026,
        policy=FreshnessPolicy(allow_stale=True),
        fixture_path=Path(__file__).resolve().parents[1] / "fixtures/oracles_elixir/dq_valid.csv",
    )
    with Session(engine) as session:
        run = session.get(IngestionRun, report.run_id)
        assert run is not None and run.status == "failed" and run.error_code == "RUNTIMEERROR"
    assert report.freshness.status is FreshnessStatus.DEGRADED
    engine.dispose()
