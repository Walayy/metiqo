"""Deux planificateurs partagent les créneaux et respectent les jobs actifs."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import create_engine, func, select

from metiquo.db.ops_models import JobRecord
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.worker.queue import PostgresJobQueue
from metiquo.worker.scheduler import PostgresScheduler, SchedulePolicy
from tests.integration.test_backfill import _seed_catalogs
from tests.integration.test_job_queue import NOW
from tests.integration.test_migrations import alembic_config


@pytest.mark.integration
def test_two_schedulers_create_one_active_job_per_year_and_coalesce_missed_slots(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    _seed_catalogs(engine, dataset="league_of_legends_match_data", years=range(2025, 2027))
    queue = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW)))
    scheduler = PostgresScheduler(queue, SchedulePolicy(current_year=2026))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: scheduler.tick(), range(2)))
    with engine.connect() as connection:
        rows = connection.execute(select(JobRecord.job_type, JobRecord.scope)).all()
    assert len(rows) == 6
    assert len([row for row in rows if row.scope == "oe:oracles_elixir:2026"]) == 1
    later = PostgresJobQueue(engine, clock=FixedClock(UtcInstant(NOW + timedelta(days=8))))
    PostgresScheduler(later, SchedulePolicy(current_year=2026)).tick()
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(JobRecord)) == 6
    for _ in range(6):
        claimed = later.claim("cleanup")
        assert claimed is not None
        later.complete(claimed, {})
    PostgresScheduler(later, SchedulePolicy(current_year=2026)).tick()
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(JobRecord)) == 10
    engine.dispose()
