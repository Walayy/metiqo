"""Déduplication persistée, rappel borné et retour à la normale entre workers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, func, insert, select

from metiquo.db.ops_models import AuditEventRecord
from metiquo.db.raw_models import IngestionRun, QualityIssue, SourceCatalog
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.repositories.postgres_operations import PostgresOperationsRepository
from metiquo.worker.alerts import PostgresAlertMonitor
from metiquo.worker.handlers import default_handlers
from metiquo.worker.queue import PostgresJobQueue
from metiquo.worker.runner import PostgresJobRunner
from tests.integration.test_job_queue import NOW
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _settings
from tests.integration.test_real_admin_api import _seed_real_health


@pytest.mark.integration
def test_alerts_survive_restart_deduplicate_and_resolve(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = _settings(postgresql_url, "real")

    def monitor(seconds: int = 0) -> PostgresAlertMonitor:
        return PostgresAlertMonitor(
            engine, settings, FixedClock(UtcInstant(NOW + timedelta(seconds=seconds)))
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: monitor().check(), range(2)))
    assert sum(len(result) for result in results) == 3
    assert monitor(1).check() == ()
    assert len(monitor(settings.alert_cooldown_seconds).check()) == 3
    assert len(monitor(settings.alert_cooldown_seconds + 1).publish(())) == 3
    assert monitor(settings.alert_cooldown_seconds + 2).publish(()) == ()
    # Une horloge antérieure ne peut pas réouvrir des états observés plus tard.
    assert monitor(0).check() == ()
    with engine.connect() as connection:
        actions = connection.execute(
            select(AuditEventRecord.action, func.count())
            .where(AuditEventRecord.target_type == "ops.alerts")
            .group_by(AuditEventRecord.action)
        ).all()
    assert {action: count for action, count in actions} == {
        "alert.opened": 3,
        "alert.reminder": 3,
        "alert.resolved": 3,
    }
    engine.dispose()


@pytest.mark.integration
def test_real_alert_job_audits_trace_and_resolves_quality_after_verified_content(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    snapshot_id = _seed_real_health(postgresql_url, "alert-fixture")
    engine = create_engine(postgresql_url)
    settings = _settings(postgresql_url, "real")
    queue = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW)))
    job = queue.enqueue("ops.alerts", {}, key="alerts", scope="ops:alerts", actor="scheduler")
    assert PostgresJobRunner(
        queue, default_handlers(engine, settings), owner="alerts-worker"
    ).run_once()
    result = queue.get(job.job_id)
    events = result.result["alertEvents"]
    assert result.status == "succeeded" and isinstance(events, list) and len(events) == 4
    entries = PostgresOperationsRepository(engine).audits(limit=100).items
    quality = next(item for item in entries if item.resource_id == "DQ_BLOCKING")
    assert quality.action == "alert.opened" and quality.actor == "scheduler"
    assert quality.impact is not None and quality.impact["traceId"] == str(job.trace_id)
    later = NOW + timedelta(seconds=1)
    with engine.begin() as connection:
        catalog_id = connection.scalar(
            select(SourceCatalog.id).where(SourceCatalog.current_snapshot_id == snapshot_id)
        )
        connection.execute(
            insert(IngestionRun).values(
                id=uuid4(),
                source_catalog_id=catalog_id,
                snapshot_id=snapshot_id,
                run_kind="sync",
                status="succeeded",
                attempt=1,
                correlation_id="verified-fixture",
                counters={"contentVerified": True},
                started_at=later,
                finished_at=later,
                created_at=later,
            )
        )
    notices = PostgresAlertMonitor(engine, settings, FixedClock(UtcInstant(later))).check()
    assert len(notices) == 1
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(QualityIssue)) == 1
        assert (
            connection.scalar(
                select(AuditEventRecord.action).where(AuditEventRecord.id == notices[0])
            )
            == "alert.resolved"
        )
    engine.dispose()
