"""Audit transactionnel des jobs et providers, contexte sûr et immutabilité SQL."""

from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError

from metiquo.db.odds_models import OddsProviderRecord
from metiquo.db.ops_models import AuditEventRecord
from metiquo.foundation.audit import audit_context
from metiquo.services.operational_audit import record_runtime_configuration
from metiquo.worker.queue import PostgresJobQueue
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _settings


@pytest.mark.integration
def test_critical_changes_are_audited_in_same_transaction_without_private_payload(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    trace, provider_id = uuid4(), uuid4()
    with audit_context(actor="operator", trace_id=trace), engine.begin() as connection:
        connection.execute(
            insert(OddsProviderRecord).values(
                id=provider_id,
                code="audit-fixture",
                display_name="PRIVATE VALUE NEVER COPIED",
                provider_type="manual_import",
                enabled=False,
                created_at=func.now(),
            )
        )
    with audit_context(actor="reviewer", trace_id=trace), engine.begin() as connection:
        connection.execute(
            update(OddsProviderRecord)
            .where(OddsProviderRecord.id == provider_id)
            .values(enabled=True)
        )
    with engine.connect() as connection:
        rows = (
            connection.execute(
                select(AuditEventRecord).order_by(AuditEventRecord.occurred_at, AuditEventRecord.id)
            )
            .mappings()
            .all()
        )
    assert len(rows) == 2 and {row["actor"] for row in rows} == {"operator", "reviewer"}
    assert {row["trace_id"] for row in rows} == {trace}
    assert "PRIVATE VALUE" not in str(rows)
    change = next(row for row in rows if row["actor"] == "reviewer")
    assert change["before_refs"]["enabled"] is False and change["after_refs"]["enabled"] is True
    with (
        pytest.raises(RuntimeError),
        audit_context(actor="rollback", trace_id=trace),
        engine.begin() as connection,
    ):
        connection.execute(
            update(OddsProviderRecord)
            .where(OddsProviderRecord.id == provider_id)
            .values(enabled=False)
        )
        raise RuntimeError("rollback mutation and its audit")
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(AuditEventRecord)) == 2
    for sql in (
        "UPDATE ops.audit_events SET actor = 'forged'",
        "DELETE FROM ops.audit_events",
        "TRUNCATE ops.audit_events",
    ):
        with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
            connection.execute(text(sql))
    engine.dispose()


@pytest.mark.integration
def test_configuration_audit_records_only_modes_and_preserves_previous_state(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = _settings(postgresql_url, "real")
    first = record_runtime_configuration(engine, settings, service="api")
    assert record_runtime_configuration(engine, settings, service="api") == first
    changed = record_runtime_configuration(engine, _settings(postgresql_url, "mock"), service="api")
    assert changed != first
    with engine.connect() as connection:
        rows = connection.execute(select(AuditEventRecord)).mappings().all()
    assert len(rows) == 2
    assert postgresql_url not in str(rows) and "password" not in str(rows).lower()
    last = next(row for row in rows if row["id"] == changed)
    assert (
        last["before_refs"]["appDataMode"] == "real" and last["after_refs"]["appDataMode"] == "mock"
    )
    assert last["after_refs"]["authMode"] == "disabled"
    engine.dispose()


@pytest.mark.integration
def test_job_state_changes_keep_request_trace_without_auditing_each_heartbeat(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    queue = PostgresJobQueue(engine)
    trace = uuid4()
    job = queue.enqueue(
        "paper.report",
        {"private": "PRIVATE PAYLOAD"},
        key="audited",
        scope="paper:EUR",
        actor="operator",
        trace_id=trace,
    )
    owner = queue.claim("worker")
    assert owner is not None
    with engine.connect() as connection:
        count = connection.scalar(select(func.count()).select_from(AuditEventRecord))
    assert queue.heartbeat(owner)
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(AuditEventRecord)) == count
    queue.request_cancel(job.job_id)
    queue.acknowledge_cancel(owner)
    with engine.connect() as connection:
        rows = (
            connection.execute(
                select(AuditEventRecord).where(AuditEventRecord.target_id == str(job.job_id))
            )
            .mappings()
            .all()
        )
    assert len(rows) == 4
    assert {row["trace_id"] for row in rows} == {trace}
    assert "PRIVATE PAYLOAD" not in str(rows)
    assert any(row["after_refs"]["status"] == "cancelled" for row in rows)
    engine.dispose()
