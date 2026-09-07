"""Exécuter un handler sous bail, renouveler sa propriété et refuser un résultat tardif."""

import logging
from collections.abc import Mapping
from threading import Event, Thread

from sqlalchemy import text

from metiquo.foundation.errors import BusinessError
from metiquo.foundation.identifiers import CorrelationId, JobId, TraceId
from metiquo.foundation.locks import ResourceBusy, resource_lock
from metiquo.foundation.observability import bind_log_context
from metiquo.foundation.time import UtcInstant
from metiquo.worker.contracts import CancellationToken, JobContext, JobHandler
from metiquo.worker.queue import PostgresJobQueue, StoredJob, job_lock_id


class PostgresJobRunner:
    def __init__(
        self, queue: PostgresJobQueue, handlers: Mapping[str, JobHandler], *, owner: str
    ) -> None:
        self.queue, self.handlers, self.owner = queue, dict(handlers), owner
        self.logger = logging.getLogger("metiquo.worker")
        self.active_cancellation: CancellationToken | None = None

    def request_stop(self) -> None:
        if self.active_cancellation is not None:
            self.active_cancellation.cancel()

    def run_once(self) -> bool:
        job = self.queue.claim(self.owner)
        if job is None:
            return False
        with self.queue.engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as execution:
            lock = job_lock_id(job.job_id)
            if not execution.scalar(text("SELECT pg_try_advisory_lock(:lock)"), {"lock": lock}):
                return False
            try:
                if not self.queue.heartbeat(job):
                    return False
                try:
                    with resource_lock(self.queue.engine, job.scope):
                        return self._execute(job)
                except ResourceBusy:
                    self.queue.release_unstarted(job)
                    return False
            finally:
                try:
                    execution.execute(text("SELECT pg_advisory_unlock(:lock)"), {"lock": lock})
                except Exception:
                    execution.invalidate()

    def _execute(self, job: StoredJob) -> bool:
        handler = self.handlers.get(job.job_type)
        if handler is None:
            self.queue.fail(job, "UNKNOWN_JOB_TYPE")
            return True
        assert job.started_at is not None
        token = CancellationToken()
        self.active_cancellation = token
        stop_heartbeat = Event()

        def renew() -> None:
            while not stop_heartbeat.wait(max(0.01, self.queue.lease_duration.total_seconds() / 3)):
                try:
                    if not self.queue.heartbeat(job):
                        token.cancel()
                        return
                except Exception:
                    token.cancel()
                    self.logger.error("worker.heartbeat_failed")
                    return

        heartbeat = Thread(target=renew, name="job-heartbeat", daemon=True)
        context = JobContext(
            JobId(job.job_id),
            TraceId(job.trace_id),
            CorrelationId(job.job_id),
            UtcInstant(job.started_at),
            self.queue.clock,
            token,
            job.payload,
        )
        with bind_log_context(
            job_id=context.job_id, trace_id=context.trace_id, correlation_id=context.correlation_id
        ):
            heartbeat.start()
            try:
                self.logger.info("worker.job_started")
                result = handler.handle(context)
                if self.queue.complete(job, result or {}):
                    self.logger.info("worker.job_succeeded")
                else:
                    self.logger.warning("worker.job_ownership_lost")
            except BusinessError as error:
                self.queue.fail(job, error.code.value)
                self.logger.warning("worker.job_failed")
            except Exception:
                self.queue.fail(job, "UNEXPECTED_ERROR")
                self.logger.error("worker.job_failed")
            finally:
                stop_heartbeat.set()
                heartbeat.join(timeout=5)
                self.active_cancellation = None
        return True
