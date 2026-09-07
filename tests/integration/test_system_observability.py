"""Une panne distante dégrade la source sans rendre le snapshot validé illisible."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update

from metiquo.api.app import create_app
from metiquo.db.raw_models import IngestionRun, SourceCatalog
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.worker.queue import PostgresJobQueue
from tests.integration.test_paper_ledger import bet_values
from tests.integration.test_postgres_canonical_api import _ReadyProbe, _request, _settings
from tests.integration.test_value_pipeline import _Context
from tests.integration.test_value_pipeline import context as context


@pytest.mark.integration
def test_status_distinguishes_source_failure_reads_and_measured_job_metrics(
    context: _Context, postgresql_url: str
) -> None:
    bet_values(context)
    now = context.captured_at + timedelta(seconds=25)
    queue = PostgresJobQueue(context.engine, clock=FixedClock(UtcInstant(now)))
    queue.enqueue("paper.report", {}, key="metrics", scope="paper:EUR")
    owner = queue.claim("worker")
    assert owner is not None
    later = now + timedelta(seconds=2)
    completed = PostgresJobQueue(context.engine, clock=FixedClock(UtcInstant(later)))
    completed.fail(owner, "DEPENDENCY_UNAVAILABLE")
    with context.engine.begin() as connection:
        catalog = connection.execute(
            select(SourceCatalog.id, SourceCatalog.season_year)
            .where(SourceCatalog.current_snapshot_id.is_not(None))
            .limit(1)
        ).one()
        connection.execute(
            update(SourceCatalog)
            .where(SourceCatalog.id == catalog.id)
            .values(dataset="league_of_legends_match_data")
        )
        connection.execute(
            insert(IngestionRun).values(
                id=uuid4(),
                source_catalog_id=catalog.id,
                run_kind="sync",
                status="failed",
                attempt=1,
                correlation_id="source-outage",
                started_at=now,
                finished_at=later,
                error_code="SOURCE_TIMEOUT",
                counters={},
                created_at=now,
            )
        )
    settings = _settings(postgresql_url, "real").model_copy(
        update={"oe_current_year": catalog.season_year, "oe_freshness_sla_seconds": 14 * 86400}
    )
    app = create_app(
        settings=settings, readiness_probe=_ReadyProbe(), clock=FixedClock(UtcInstant(later))
    )
    assert _request(app, "/health").status_code == 200
    assert _request(app, "/ready").status_code == 200
    response = _request(app, "/api/v1/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    operations = body["operations"]
    assert operations["readsAvailable"] is True
    assert operations["source"]["status"] == "degraded"
    assert operations["source"]["reasonCode"] == "SOURCE_TIMEOUT"
    assert operations["source"]["snapshotId"]
    assert operations["jobCounts"]["failed"] == 1
    assert operations["metrics"]["meanJobDurationSeconds"] == 2
    assert operations["metrics"]["measuredJobCount"] == 1
    assert operations["metrics"]["signals"]["VALUE"] >= 1
    assert operations["metrics"]["api"]["requestCount"] >= 2
    assert operations["backups"]["status"] == "not_configured"
    assert postgresql_url not in response.text
    future_app = create_app(
        settings=settings,
        readiness_probe=_ReadyProbe(),
        clock=FixedClock(UtcInstant(context.captured_at - timedelta(days=365))),
    )
    future_status = _request(future_app, "/api/v1/system/status").json()["operations"]
    assert future_status["readsAvailable"] is False
    assert future_status["source"]["reasonCode"] == "SOURCE_TIMESTAMP_INVALID"
    future_app.state.real_admin_engine.dispose()
    app.state.real_admin_engine.dispose()
