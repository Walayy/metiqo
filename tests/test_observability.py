"""Tests de la journalisation JSON corrélée."""

import io
import json
import logging
from typing import cast

from metiquo.foundation.identifiers import CorrelationId, JobId, SnapshotId, TraceId
from metiquo.foundation.metrics import ApiMetrics
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


def test_logs_redact_credentials_and_omit_raw_exception_payloads() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(secrets=("opaque-credential",)))
    logger = logging.getLogger("metiquo.test.redaction")
    logger.handlers, logger.propagate, logger.level = [handler], False, logging.INFO
    logger.info(
        'password="private-password" token=private-token Authorization: Bearer private-bearer'
    )
    logger.info("postgresql+psycopg://user:private-database@host/db?sslmode=require")
    logger.info("https://user:private-http@host/path opaque-credential")
    try:
        raise RuntimeError("unstructured private payload from a driver")
    except RuntimeError:
        logger.exception("operation.failed")
    output = stream.getvalue()
    for secret in (
        "private-password",
        "private-token",
        "private-bearer",
        "private-database",
        "private-http",
        "opaque-credential",
        "unstructured private payload",
    ):
        assert secret not in output
    entries = [json.loads(line) for line in output.splitlines()]
    assert entries[-1]["message"] == "operation.failed"
    assert entries[-1]["exception_type"] == "RuntimeError"


def test_metrics_are_measured_and_extra_log_fields_are_allowlisted() -> None:
    metrics = ApiMetrics()
    assert metrics.snapshot().mean_latency_ms is None
    for status, seconds in ((200, 0.01), (422, 0.02), (503, 0.03)):
        metrics.observe(status, seconds)
    snapshot = metrics.snapshot()
    assert (snapshot.request_count, snapshot.failure_count, snapshot.mean_latency_ms) == (3, 1, 20)
    record = logging.makeLogRecord(
        {
            "msg": "http.completed",
            "duration_ms": 20,
            "status_code": 200,
            "route": "/api/v1/jobs/{job_id}",
            "method": "GET",
            "payload": "private",
        }
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload["duration_ms"] == 20
    assert payload["route"] == "/api/v1/jobs/{job_id}"
    assert "payload" not in payload
