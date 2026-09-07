"""Public API receipt -> durable job -> worker-owned files and observable run."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy import create_engine, func, select

from metiquo.api.app import create_app
from metiquo.contracts.enums import DataMode
from metiquo.db.raw_models import IngestionRun
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.local_transports import LocalFixtureTransport
from metiquo.ingestion.source_errors import SourceUnavailable
from metiquo.ingestion.sync import OracleElixirYearSync
from metiquo.ingestion.transport import SourceRef, TransportPolicy
from metiquo.worker.handlers import OracleSyncHandler
from metiquo.worker.queue import PostgresJobQueue
from metiquo.worker.runner import PostgresJobRunner
from tests.integration.test_backfill import _seed_catalogs
from tests.integration.test_migrations import alembic_config
from tests.integration.test_real_admin_api import ReadyProbe, _request, _settings


@pytest.mark.integration
def test_automatic_sync_retry_preserves_failed_attempt_and_finishes_next_run(
    postgresql_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    _seed_catalogs(engine, dataset="league_of_legends_match_data", years=range(2026, 2027))
    settings = _settings(postgresql_url, "real").model_copy(update={"object_store_root": tmp_path})
    queue = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(datetime.now(UTC))))
    job = queue.enqueue(
        "oe.sync", {"year": 2026}, key="retry-real-io", scope="oe:oracles_elixir:2026"
    )
    handler = OracleSyncHandler(engine, settings)
    original_download = OracleElixirYearSync._download

    def unavailable(*args: object, **kwargs: object) -> None:
        raise SourceUnavailable(
            "Fixture source unavailable", transport="fixture", source_id="fixture"
        )

    monkeypatch.setattr(OracleElixirYearSync, "_download", unavailable)
    assert PostgresJobRunner(queue, {"oe.sync": handler}, owner="before-outage").run_once()
    failed = queue.get(job.job_id)
    assert failed.status == "queued" and failed.attempt == 1
    monkeypatch.setattr(OracleElixirYearSync, "_download", original_download)
    fixture = Path(__file__).resolve().parents[1] / "fixtures/oracles_elixir/dq_valid.csv"

    def transports(
        self: OracleElixirYearSync,
        source: SourceRef,
        fixture_path: Path | None,
    ) -> tuple[LocalFixtureTransport, ...]:
        return (
            LocalFixtureTransport(
                policy=TransportPolicy.from_settings(settings),
                fixtures={source.source_id: fixture},
                data_mode=DataMode.MOCK,
            ),
        )

    monkeypatch.setattr(OracleElixirYearSync, "_transports", transports)
    later = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(failed.scheduled_at)))
    assert PostgresJobRunner(later, {"oe.sync": handler}, owner="after-outage").run_once()
    assert later.get(job.job_id).status == "succeeded"
    with engine.connect() as connection:
        attempts = connection.execute(
            select(IngestionRun.status, IngestionRun.request_key_hash).where(
                IngestionRun.run_kind == "sync"
            )
        ).all()
    assert {row.status for row in attempts} == {"failed", "succeeded"}
    assert len({row.request_key_hash for row in attempts}) == 2
    engine.dispose()


@pytest.mark.integration
def test_manual_sync_is_queued_without_api_writes_and_completed_by_worker(
    postgresql_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    _seed_catalogs(engine, dataset="league_of_legends_match_data", years=range(2026, 2027))
    settings = _settings(postgresql_url, "real").model_copy(update={"object_store_root": tmp_path})
    app = create_app(settings=settings, readiness_probe=ReadyProbe())
    original_sync = OracleElixirYearSync.sync_year

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("The API must only persist a job, never download or write raw files")

    monkeypatch.setattr(OracleElixirYearSync, "sync_year", forbidden)
    path = "/api/v1/admin/oracles-elixir/sync?year=2026"
    headers = {"Idempotency-Key": "ops-gate-manual-sync"}
    first = _request(app, "POST", path, headers=headers)
    assert first.status_code == 202, first.text
    job_id = UUID(first.json()["data"]["jobId"])
    assert first.json()["data"]["status"] == "queued"
    second = _request(app, "POST", path, headers=headers)
    assert second.status_code == 202 and second.json()["data"]["jobId"] == str(job_id)
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(IngestionRun)) == 0
    assert not (tmp_path / "raw").exists()
    monkeypatch.setattr(OracleElixirYearSync, "sync_year", original_sync)
    fixture = Path(__file__).resolve().parents[1] / "fixtures/oracles_elixir/dq_valid.csv"

    def transports(
        self: OracleElixirYearSync,
        source: SourceRef,
        fixture_path: Path | None,
    ) -> tuple[LocalFixtureTransport, ...]:
        return (
            LocalFixtureTransport(
                policy=TransportPolicy.from_settings(settings),
                fixtures={source.source_id: fixture},
                data_mode=DataMode.MOCK,
            ),
        )

    monkeypatch.setattr(OracleElixirYearSync, "_transports", transports)
    queue = PostgresJobQueue(engine)
    runner = PostgresJobRunner(
        queue, {"oe.sync": OracleSyncHandler(engine, settings)}, owner="gate-worker"
    )
    assert runner.run_once()
    completed = queue.get(job_id)
    assert completed.status == "succeeded" and completed.result["runId"]
    assert list((tmp_path / "raw").glob("**/source.csv"))
    assert (tmp_path / "work").is_dir()
    assert not list((tmp_path / "work").iterdir()), "Temporary downloads must be cleaned"
    jobs = _request(app, "GET", "/api/v1/admin/jobs?limit=100").json()["data"]
    assert next(job for job in jobs if job["jobId"] == str(job_id))["status"] == "succeeded"
    replay = _request(app, "POST", path, headers=headers)
    assert replay.status_code in {200, 202}
    assert not runner.run_once(), "An HTTP retry must not enqueue another execution"
    app.state.real_admin_engine.dispose()
    engine.dispose()
