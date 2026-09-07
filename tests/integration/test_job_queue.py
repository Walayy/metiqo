"""Prise atomique des jobs, reprise d'un bail et refus d'un ancien worker."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from metiquo.foundation.errors import BusinessError
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.worker.handlers import default_handlers
from metiquo.worker.queue import PostgresJobQueue, StoredJob, job_lock_id
from metiquo.worker.runner import PostgresJobRunner
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _settings

NOW = datetime(2026, 9, 8, 3, tzinfo=UTC)


@pytest.mark.integration
def test_concurrent_claim_and_expired_lease_fence_old_owner(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    queue = PostgresJobQueue(
        engine, clock=FixedClock(UtcInstant(NOW)), lease_duration=timedelta(seconds=30)
    )
    job = queue.enqueue("paper.report", {"currency": "EUR"}, key="report-1", scope="paper:EUR")
    assert (
        queue.enqueue("paper.report", {"currency": "EUR"}, key="report-1", scope="paper:EUR") == job
    )
    with pytest.raises(BusinessError):
        queue.enqueue("paper.report", {"currency": "USD"}, key="report-1", scope="paper:EUR")
    barrier = Barrier(2)

    def claim(worker: str) -> StoredJob | None:
        barrier.wait(timeout=5)
        return queue.claim(worker)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ("worker-a", "worker-b")))
    winners = [c for c in claims if c is not None]
    assert len(winners) == 1
    first = winners[0]
    assert first.job_id == job.job_id and first.attempt == 1
    assert queue.claim("other") is None
    later = PostgresJobQueue(
        engine,
        clock=FixedClock(UtcInstant(NOW + timedelta(seconds=31))),
        lease_duration=timedelta(seconds=30),
    )
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as executing:
        executing.execute(text("SELECT pg_advisory_lock(:lock)"), {"lock": job_lock_id(job.job_id)})
        assert later.claim("cannot-overlap") is None
        assert later.get(job.job_id).attempt == 1
        executing.execute(
            text("SELECT pg_advisory_unlock(:lock)"), {"lock": job_lock_id(job.job_id)}
        )
    recovered = later.claim("recovery-worker")
    assert recovered is not None and recovered.job_id == first.job_id
    assert recovered.attempt == 2 and recovered.lease_token != first.lease_token
    assert later.complete(first, {"unsafe": True}) is False
    assert later.heartbeat(first) is False
    assert later.complete(recovered, {"report": "stored"}) is True
    finished = later.get(job.job_id)
    assert finished.status == "succeeded" and finished.attempt == 2
    assert later.claim("finished-worker") is None
    for sql, error in (
        ("UPDATE ops.jobs SET payload = '{}'::jsonb", "request is immutable"),
        ("DELETE FROM ops.jobs", "history cannot be deleted"),
    ):
        with pytest.raises(DBAPIError, match=error), engine.begin() as connection:
            connection.execute(text(sql))
    engine.dispose()


@pytest.mark.integration
def test_postgres_worker_runs_the_real_report_handler_and_refuses_unknown_types(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    queue = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW)))
    job = queue.enqueue("paper.report", {"currency": "EUR"}, key="report", scope="paper:EUR")
    worker = PostgresJobRunner(
        queue, default_handlers(engine, _settings(postgresql_url, "real")), owner="worker"
    )
    assert worker.run_once() is True
    finished = queue.get(job.job_id)
    assert finished.status == "succeeded" and finished.result["reportId"]
    assert worker.run_once() is False
    unknown = queue.enqueue("missing.handler", {}, key="unknown", scope="unknown")
    assert worker.run_once() is True
    assert queue.get(unknown.job_id).error_code == "UNKNOWN_JOB_TYPE"
    assert queue.get(unknown.job_id).status == "failed"
    engine.dispose()


@pytest.mark.integration
def test_queue_scheduling_and_terminal_failure(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    queue = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW)))
    future = queue.enqueue(
        "paper.report",
        {"currency": "EUR"},
        key="future",
        scope="paper:EUR",
        scheduled_at=NOW + timedelta(hours=1),
    )
    assert queue.claim("early-worker") is None
    later = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW + timedelta(hours=1))))
    claimed = later.claim("ready-worker")
    assert claimed is not None and claimed.job_id == future.job_id
    assert later.fail(claimed, "INVALID_PAYLOAD") is True
    assert later.get(future.job_id).status == "failed"
    assert later.claim("retry-worker") is None
    engine.dispose()
