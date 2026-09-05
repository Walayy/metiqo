"""Reprise de backfill et exclusion concurrente par année."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.backfill import BackfillOrchestrator, BackfillResult, YearSyncResult

ROOT = Path(__file__).resolve().parents[2]
INSTANT = datetime(2026, 9, 6, 1, 30, tzinfo=UTC)
PROVIDER = "oracles_elixir"


def alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


class SimulatedCrash(BaseException):
    pass


def _seed_catalogs(engine: Engine, *, dataset: str, years: range) -> dict[int, UUID]:
    result: dict[int, UUID] = {}
    with engine.begin() as connection:
        for year in years:
            catalog_id = uuid4()
            result[year] = catalog_id
            connection.execute(
                text(
                    """
                    INSERT INTO raw.source_catalog (
                      id, provider, dataset, season_year, landing_page, drive_file_id,
                      source_name, origin, status, discovered_at
                    ) VALUES (
                      :catalog_id, :provider, :dataset, :year,
                      'https://oracleselixir.com/tools/downloads', :drive_file_id,
                      :source_name, 'discovered', 'active', :instant
                    )
                    """
                ),
                {
                    "catalog_id": catalog_id,
                    "provider": PROVIDER,
                    "dataset": dataset,
                    "year": year,
                    "drive_file_id": f"drive-{dataset}-{year}",
                    "source_name": f"{year}_LoL_esports_match_data.csv",
                    "instant": INSTANT,
                },
            )
    return result


class RecordingYearProcessor:
    def __init__(
        self,
        *,
        engine: Engine,
        catalogs: dict[int, UUID],
        crash_once_year: int | None = None,
        blocking_year: int | None = None,
    ) -> None:
        self.engine = engine
        self.catalogs = catalogs
        self.crash_once_year = crash_once_year
        self.blocking_year = blocking_year
        self.calls: list[tuple[int, int]] = []
        self.entered = Event()
        self.release = Event()
        self._lock = Lock()
        self._crashed = False

    def sync_year(
        self,
        *,
        provider: str,
        dataset: str,
        year: int,
        job_id: UUID,
        attempt: int,
    ) -> YearSyncResult:
        del job_id
        assert provider == PROVIDER
        with self._lock:
            self.calls.append((year, attempt))
            should_crash = self.crash_once_year == year and not self._crashed
            if should_crash:
                self._crashed = True
        if should_crash:
            raise SimulatedCrash()
        if self.blocking_year == year:
            self.entered.set()
            if not self.release.wait(timeout=10):
                raise TimeoutError("test processor release timeout")
        run_id = uuid4()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO raw.ingestion_runs (
                      id, source_catalog_id, run_kind, status, attempt,
                      transport, correlation_id, started_at, finished_at
                    ) VALUES (
                      :run_id, :catalog_id, 'backfill', 'succeeded', :attempt,
                      'local-fixture', :correlation_id, :instant, :instant
                    )
                    """
                ),
                {
                    "run_id": run_id,
                    "catalog_id": self.catalogs[year],
                    "attempt": attempt,
                    "correlation_id": f"backfill-{dataset}-{year}-{run_id.hex}",
                    "instant": INSTANT,
                },
            )
        return YearSyncResult(run_id=run_id)


@pytest.mark.integration
def test_interrupted_backfill_resumes_without_replaying_completed_years(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    dataset = f"resume-{uuid4().hex}"
    catalogs = _seed_catalogs(engine, dataset=dataset, years=range(2024, 2027))
    processor = RecordingYearProcessor(
        engine=engine,
        catalogs=catalogs,
        crash_once_year=2025,
    )
    orchestrator = BackfillOrchestrator(
        engine=engine,
        processor=processor,
        clock=FixedClock(UtcInstant(INSTANT)),
    )

    with pytest.raises(SimulatedCrash):
        orchestrator.run(
            provider=PROVIDER,
            dataset=dataset,
            from_year=2024,
            to_year=2026,
        )

    resumed = orchestrator.run(
        provider=PROVIDER,
        dataset=dataset,
        from_year=2024,
        to_year=2026,
    )
    converged = orchestrator.run(
        provider=PROVIDER,
        dataset=dataset,
        from_year=2024,
        to_year=2026,
    )

    assert resumed.status == "succeeded"
    assert converged == resumed
    assert processor.calls == [(2024, 1), (2025, 1), (2025, 2), (2026, 1)]
    assert [(state.year, state.status, state.attempts) for state in resumed.years] == [
        (2024, "succeeded", 1),
        (2025, "succeeded", 2),
        (2026, "succeeded", 1),
    ]
    assert all(state.last_run_id is not None for state in resumed.years)
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM raw.backfill_jobs WHERE dataset = :dataset"),
                {"dataset": dataset},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    """
                    SELECT count(*) FROM raw.backfill_years AS year_state
                    JOIN raw.backfill_jobs AS job ON job.id = year_state.job_id
                    WHERE job.dataset = :dataset
                    """
                ),
                {"dataset": dataset},
            ).scalar_one()
            == 3
        )
    engine.dispose()


@pytest.mark.integration
def test_concurrent_runs_share_job_and_only_one_processor_holds_year_lock(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, pool_size=5)
    dataset = f"concurrent-{uuid4().hex}"
    catalogs = _seed_catalogs(engine, dataset=dataset, years=range(2026, 2027))
    processor = RecordingYearProcessor(
        engine=engine,
        catalogs=catalogs,
        blocking_year=2026,
    )
    orchestrator = BackfillOrchestrator(
        engine=engine,
        processor=processor,
        clock=FixedClock(UtcInstant(INSTANT)),
    )

    def run_backfill() -> BackfillResult:
        return orchestrator.run(
            provider=PROVIDER,
            dataset=dataset,
            from_year=2026,
            to_year=2026,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(run_backfill)
        assert processor.entered.wait(timeout=10)
        concurrent = executor.submit(run_backfill).result(timeout=10)
        assert concurrent.status == "running"
        assert processor.calls == [(2026, 1)]
        processor.release.set()
        first = first_future.result(timeout=10)

    final = orchestrator.run(
        provider=PROVIDER,
        dataset=dataset,
        from_year=2026,
        to_year=2026,
    )
    assert first.status == "succeeded"
    assert final.status == "succeeded"
    assert first.job_id == concurrent.job_id == final.job_id
    assert processor.calls == [(2026, 1)]
    assert len(final.years) == 1
    assert final.years[0].year == 2026
    assert final.years[0].status == "succeeded"
    assert final.years[0].attempts == 1
    assert final.years[0].last_run_id is not None
    assert final.years[0].error_code is None
    engine.dispose()
