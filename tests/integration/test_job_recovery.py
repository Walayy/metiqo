"""Reprises bornées, annulation et relance avec conservation du job original."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.worker.contracts import JobContext
from metiquo.worker.queue import PostgresJobQueue
from metiquo.worker.runner import PostgresJobRunner
from tests.integration.test_job_queue import NOW
from tests.integration.test_migrations import alembic_config


class FailingHandler:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def handle(self, context: JobContext) -> None:
        raise self.error


@pytest.mark.integration
def test_retry_exhaustion_permanent_failure_and_explicit_linked_rerun(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    queue = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW)))
    job = queue.enqueue("test.retry", {}, key="retry", scope="test", max_attempts=3)
    handler = FailingHandler(
        BusinessError(ErrorCode.DEPENDENCY_UNAVAILABLE, "offline", retryable=True)
    )
    for attempt in range(1, 4):
        assert PostgresJobRunner(queue, {"test.retry": handler}, owner="worker").run_once()
        state = queue.get(job.job_id)
        assert state.attempt == attempt
        if attempt < 3:
            assert state.status == "queued" and state.scheduled_at > queue.clock.now().value
            assert queue.claim("too-early") is None
            queue = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(state.scheduled_at)))
    assert state.status == "dead" and state.error_code == "DEPENDENCY_UNAVAILABLE"
    assert queue.claim("exhausted") is None
    rerun = queue.rerun(job.job_id, key="after-fix", actor="operator", reason="dependency restored")
    assert rerun.job_id != job.job_id and rerun.rerun_of == job.job_id and rerun.attempt == 0
    assert rerun.reason == "dependency restored" and queue.get(job.job_id) == state
    assert (
        queue.rerun(job.job_id, key="after-fix", actor="operator", reason="dependency restored")
        == rerun
    )
    permanent = FailingHandler(BusinessError(ErrorCode.INVALID_INPUT, "invalid", retryable=True))
    assert PostgresJobRunner(queue, {"test.retry": permanent}, owner="worker").run_once()
    assert queue.get(rerun.job_id).status == "failed"
    with pytest.raises(DBAPIError, match="immutable"), engine.begin() as connection:
        connection.execute(text("UPDATE ops.jobs SET rerun_of = NULL WHERE rerun_of IS NOT NULL"))
    engine.dispose()


@pytest.mark.integration
def test_cancel_before_claim_during_handler_and_after_owner_disappears(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    queue = PostgresJobQueue(engine, lease_duration=timedelta(seconds=0.6))
    queued = queue.enqueue("test.cancel", {}, key="queued", scope="cancel")
    assert queue.request_cancel(queued.job_id).status == "cancelled"
    assert queue.claim("worker") is None
    running = queue.enqueue("test.cancel", {}, key="running", scope="cancel")
    entered, observed = Event(), Event()

    class Handler:
        def handle(self, context: JobContext) -> None:
            entered.set()
            assert context.cancellation.wait(4)
            observed.set()
            context.cancellation.raise_if_cancelled()

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(
            PostgresJobRunner(queue, {"test.cancel": Handler()}, owner="worker").run_once
        )
        assert entered.wait(3)
        assert queue.request_cancel(running.job_id).status == "running"
        assert result.result(timeout=5)
    assert observed.is_set()
    assert queue.get(running.job_id).status == "cancelled"
    assert queue.get(running.job_id).attempt == 1
    fixed = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW)))
    lost = fixed.enqueue("test.cancel", {}, key="lost-owner", scope="cancel")
    owner = fixed.claim("disappeared")
    assert owner is not None
    fixed.request_cancel(lost.job_id)
    later = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW + timedelta(minutes=2))))
    assert later.claim("cleanup") is None
    assert later.get(lost.job_id).status == "cancelled"
    assert later.complete(owner, {}) is False
    racing = later.enqueue("test.cancel", {}, key="commit-race", scope="cancel")
    racing_owner = later.claim("finishing")
    assert racing_owner is not None
    later.request_cancel(racing.job_id)
    assert later.complete(racing_owner, {"alreadyCommitted": True})
    assert later.get(racing.job_id).status == "cancelled"
    assert later.get(racing.job_id).result == {"alreadyCommitted": True}
    engine.dispose()


@pytest.mark.integration
def test_shutdown_is_cooperative_and_expired_attempts_become_dead(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    queue = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW)))
    entered = Event()

    class Handler:
        def handle(self, context: JobContext) -> None:
            entered.set()
            assert context.cancellation.wait(3)
            context.cancellation.raise_if_cancelled()

    job = queue.enqueue("test.stop", {}, key="stop", scope="stop")
    runner = PostgresJobRunner(queue, {"test.stop": Handler()}, owner="worker")
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(runner.run_once)
        assert entered.wait(3)
        runner.request_stop()
        assert result.result(timeout=5)
    assert queue.get(job.job_id).status == "cancelled"
    abandoned = queue.enqueue("test.stop", {}, key="crashed", scope="stop", max_attempts=1)
    assert queue.claim("lost") is not None
    later = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW + timedelta(minutes=2))))
    assert later.claim("cleanup") is None
    assert later.get(abandoned.job_id).status == "dead"
    engine.dispose()
