"""Lecture admin paginée de la file et du journal central avec leurs preuves."""

from uuid import UUID

import pytest
from alembic import command
from sqlalchemy import create_engine

from metiquo.api.app import create_app
from metiquo.worker.queue import PostgresJobQueue
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _ReadyProbe, _request, _settings


@pytest.mark.integration
def test_admin_lists_queue_states_and_central_audit_with_database_pagination(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    queue = PostgresJobQueue(engine)
    job = queue.enqueue(
        "paper.report",
        {"currency": "EUR", "private": "PRIVATE PAYLOAD"},
        key="operational",
        scope="paper:EUR",
        actor="operator",
    )
    app = create_app(settings=_settings(postgresql_url, "real"), readiness_probe=_ReadyProbe())
    response = _request(app, "/api/v1/admin/jobs?status=queued&limit=1").json()
    assert response["page"]["total"] == 1
    item = response["data"][0]
    assert item["jobId"] == str(job.job_id) and item["status"] == "queued"
    assert item["attempt"] == 0 and item["maxAttempts"] == 3
    assert UUID(item["traceId"]) == job.trace_id and "PRIVATE PAYLOAD" not in str(response)
    audit = _request(app, "/api/v1/admin/audit-log?limit=1").json()
    assert audit["page"]["total"] == 1 and audit["data"][0]["actor"] == "operator"
    assert audit["data"][0]["impact"]["traceId"] == str(job.trace_id)
    empty = _request(app, "/api/v1/admin/audit-log?offset=1&limit=1").json()
    assert empty["page"]["total"] == 1 and empty["data"] == []
    owner = queue.claim("worker")
    assert owner is not None
    queue.fail(owner, "INVALID_INPUT")
    failed = _request(app, "/api/v1/admin/jobs?status=failed").json()["data"][0]
    assert failed["attempt"] == 1 and failed["errorCode"] == "INVALID_INPUT"
    engine.dispose()
