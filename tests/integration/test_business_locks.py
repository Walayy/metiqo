"""Exclusion par ressource, libération sûre et coexistence de scopes indépendants."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic

import pytest
from alembic import command
from sqlalchemy import create_engine, text

from metiquo.foundation.locks import ResourceBusy, resource_lock, resource_lock_key
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.worker.contracts import JobContext
from metiquo.worker.queue import PostgresJobQueue
from metiquo.worker.runner import PostgresJobRunner
from tests.integration.test_job_queue import NOW
from tests.integration.test_migrations import alembic_config


@pytest.mark.integration
def test_scoped_workers_serialize_same_year_without_blocking_another(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    queue = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW)))
    first = queue.enqueue(
        "oe.sync",
        {"year": 2026},
        key="a",
        scope="oe:oracles_elixir:2026",
        scheduled_at=NOW - timedelta(seconds=2),
    )
    second = queue.enqueue(
        "oe.sync",
        {"year": 2026},
        key="b",
        scope="oe:oracles_elixir:2026",
        scheduled_at=NOW - timedelta(seconds=1),
    )
    other = queue.enqueue("oe.sync", {"year": 2025}, key="c", scope="oe:oracles_elixir:2025")
    started, release = Event(), Event()

    class Handler:
        def handle(self, context: JobContext) -> None:
            if context.job_id.value == first.job_id:
                started.set()
                assert release.wait(5)

    worker_a = PostgresJobRunner(queue, {"oe.sync": Handler()}, owner="worker-a")
    worker_b = PostgresJobRunner(queue, {"oe.sync": Handler()}, owner="worker-b")
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(worker_a.run_once)
        try:
            assert started.wait(5)
            assert worker_b.run_once() is True
            assert queue.get(other.job_id).status == "succeeded"
            assert queue.get(second.job_id).status == "queued"
            assert queue.get(second.job_id).attempt == 0
        finally:
            release.set()
        assert running.result(timeout=5) is True
    assert worker_b.run_once() is True
    assert queue.get(second.job_id).status == "succeeded"
    engine.dispose()


@pytest.mark.integration
def test_resource_lock_times_out_reenters_and_releases_after_session_death(
    postgresql_url: str,
) -> None:
    engine = create_engine(postgresql_url)
    scope = "oe:oracles_elixir:2026"
    owner = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    owner.execute(text("SELECT pg_advisory_lock(:lock)"), {"lock": resource_lock_key(scope)})
    pid = owner.scalar(text("SELECT pg_backend_pid()"))
    started = monotonic()
    with pytest.raises(ResourceBusy), resource_lock(engine, scope, timeout_seconds=0.05):
        pytest.fail("Le verrou détenu ne doit pas être acquis")
    assert monotonic() - started < 2
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
        assert admin.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid}) is True
    owner.invalidate()
    owner.close()
    with (
        pytest.raises(RuntimeError, match="handler failed"),
        resource_lock(engine, scope),
        resource_lock(engine, scope),
    ):
        raise RuntimeError("handler failed")
    with resource_lock(engine, scope):
        pass
    engine.dispose()
