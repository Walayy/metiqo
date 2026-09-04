"""Tests de la journalisation JSON corrélée."""

import io
import json
import logging
from typing import cast

from metiquo.foundation.identifiers import CorrelationId, JobId, SnapshotId, TraceId
from metiquo.foundation.observability import JsonFormatter, bind_log_context

TRACE_ID = TraceId.parse("103c09e2-01bd-4975-ae8a-f87ee514838a")
CORRELATION_ID = CorrelationId.parse("ca7f4fd9-4d51-4f73-8032-f31a49dd090f")
JOB_ID = JobId.parse("20c5df99-bb91-429b-ae02-42d93ccf259e")
SNAPSHOT_ID = SnapshotId.parse("3a782c66-1405-461f-a5be-8ac386b8efb3")


def test_json_log_contains_safe_context_and_restores_it() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("metiquo.test.observability")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    with bind_log_context(
        trace_id=TRACE_ID,
        correlation_id=CORRELATION_ID,
        job_id=JOB_ID,
        snapshot_id=SNAPSHOT_ID,
    ):
        logger.info("Synchronisation terminée")

    logger.info("Contexte restauré")
    first, second = (json.loads(line) for line in stream.getvalue().splitlines())
    first_payload = cast(dict[str, object], first)
    second_payload = cast(dict[str, object], second)

    timestamp = first_payload["timestamp"]
    assert isinstance(timestamp, str)
    assert timestamp.endswith("Z")
    assert first_payload["trace_id"] == str(TRACE_ID)
    assert first_payload["correlation_id"] == str(CORRELATION_ID)
    assert first_payload["job_id"] == str(JOB_ID)
    assert first_payload["snapshot_id"] == str(SNAPSHOT_ID)
    assert first_payload["message"] == "Synchronisation terminée"
    assert "trace_id" not in second_payload
