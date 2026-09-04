"""Tests du contrat de job et du cycle de vie worker."""

import io
import json
import logging
from threading import Thread

from metiquo.foundation.identifiers import CorrelationId, JobId, TraceId
from metiquo.foundation.observability import JsonFormatter
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.worker.contracts import CancellationToken, JobContext, JobHandler
from metiquo.worker.runtime import WorkerRuntime


class RecordingHandler:
    """Handler minimal prouvant la compatibilité structurelle du protocole."""

    def __init__(self) -> None:
        self.context: JobContext | None = None

    def handle(self, context: JobContext) -> None:
        self.context = context


def execute(handler: JobHandler, context: JobContext) -> None:
    handler.handle(context)


def test_job_handler_receives_deterministic_context_and_cancellation() -> None:
    started_at = UtcInstant.parse("2026-09-04T19:00:00Z")
    cancellation = CancellationToken()
    context = JobContext(
        job_id=JobId.parse("c89bf6e5-b957-4ba1-b179-48f3beccfb70"),
        trace_id=TraceId.parse("0ab102de-484a-43ca-a27a-aa71f29e87a4"),
        correlation_id=CorrelationId.parse("8a011b86-d828-4697-923c-ae2fc99eff1e"),
        started_at=started_at,
        clock=FixedClock(started_at),
        cancellation=cancellation,
    )
    handler = RecordingHandler()

    execute(handler, context)
    cancellation.cancel()

    assert handler.context is context
    assert context.clock.now() is started_at
    assert context.cancellation.is_cancelled is True


def test_worker_starts_and_stops_cleanly_without_job() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("metiquo.test.worker")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    runtime = WorkerRuntime(logger=logger)
    thread = Thread(target=runtime.run)

    thread.start()
    assert runtime.wait_until_started(timeout_seconds=1)
    runtime.request_stop()
    thread.join(timeout=1)

    assert thread.is_alive() is False
    messages = [json.loads(line)["message"] for line in stream.getvalue().splitlines()]
    assert messages == ["worker.started", "worker.stopped"]
