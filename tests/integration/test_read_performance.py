"""Bound database work and pagination; synthetic load is no financial evidence."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, event, insert, select

from metiquo.canonical.series import CanonicalSeriesBuilder
from metiquo.db.core_models import Series
from metiquo.db.odds_models import OddsProviderRecord
from metiquo.db.pricing_models import SignalRecord
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.repositories.postgres_admin import PostgresAdminRepository
from metiquo.repositories.postgres_canonical import PostgresCanonicalRepository
from metiquo.repositories.postgres_models import PostgresModelRepository
from metiquo.repositories.postgres_opportunities import PostgresOpportunityRepository
from metiquo.services.value_pipeline import PostgresValuePipeline
from tests.integration.test_canonical_series import _seed_series
from tests.integration.test_migrations import alembic_config
from tests.integration.test_value_pipeline import _SLA, _capture, _Context
from tests.integration.test_value_pipeline import context as context


@contextmanager
def count_queries(engine: Engine) -> Iterator[list[str]]:
    queries: list[str] = []

    def capture(*arguments: object) -> None:
        queries.append(str(arguments[2]))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        yield queries
    finally:
        event.remove(engine, "before_cursor_execute", capture)


@pytest.mark.integration
def test_provider_health_query_count_does_not_grow_with_provider_count(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    now = datetime(2026, 9, 7, tzinfo=UTC)
    repository = PostgresAdminRepository(engine, FixedClock(UtcInstant(now)))
    with engine.begin() as connection:
        connection.execute(
            insert(OddsProviderRecord).values(
                id=uuid4(),
                code="performance-0",
                display_name="Synthetic load",
                provider_type="manual_import",
                enabled=False,
                created_at=now,
            )
        )
    with count_queries(engine) as queries:
        assert len(repository.list_data_sources()) == 2
    small_count = len(queries)
    with engine.begin() as connection:
        connection.execute(
            insert(OddsProviderRecord),
            [
                dict(
                    id=uuid4(),
                    code=f"performance-{index}",
                    display_name="Synthetic load",
                    provider_type="manual_import",
                    enabled=False,
                    created_at=now,
                )
                for index in range(1, 50)
            ],
        )
    with count_queries(engine) as queries:
        assert len(repository.list_data_sources()) == 51
    assert len(queries) == small_count
    assert len(queries) <= 10
    engine.dispose()


@pytest.mark.integration
def test_events_paginate_in_sql_and_keep_total_past_the_last_page(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    _seed_series(engine, "performance-events")
    CanonicalSeriesBuilder(engine=engine).build(dataset="performance-events")
    with engine.begin() as connection:
        original = dict(connection.execute(select(Series.__table__)).mappings().first() or {})
        connection.execute(
            insert(Series),
            [
                dict(original, id=uuid4(), source_series_id=f"LOAD-{i}", series_key=f"LOAD-{i}")
                for i in range(1000)
            ],
        )
    repository = PostgresCanonicalRepository(engine)
    with count_queries(engine) as queries:
        page = repository.page(offset=0, limit=20)
    assert len(page.items) == 20 and page.total == 1004
    assert len(queries) == 2
    assert "LIMIT" in queries[-1] and "OFFSET" in queries[-1]
    next_page = repository.page(offset=20, limit=20)
    assert {item.event_id for item in page.items}.isdisjoint(
        item.event_id for item in next_page.items
    )
    assert repository.page(offset=2000, limit=20).total == 1004
    assert repository.page(offset=0, limit=20, team="%_").total == 0
    with count_queries(engine) as queries:
        assert repository.get(page.items[0].event_id) == page.items[0]
    assert len(queries) == 1
    engine.dispose()


@pytest.mark.integration
def test_signal_projection_does_not_query_events_once_per_signal(context: _Context) -> None:
    clock = FixedClock(UtcInstant(context.captured_at + timedelta(seconds=10)))
    result = PostgresValuePipeline(context.engine, source_sla=_SLA, clock=clock).evaluate(
        _capture(context)
    )
    assert result.signal is not None
    repository = PostgresOpportunityRepository(context.engine, clock)
    with count_queries(context.engine) as queries:
        assert len(repository.list()) == 1
    small_count = len(queries)
    with context.engine.begin() as connection:
        original = dict(connection.execute(select(SignalRecord.__table__)).mappings().one())
        # Capacity fixture only: retain all FK evidence, give each read row a unique identity.
        connection.execute(
            insert(SignalRecord),
            [
                dict(
                    original,
                    id=uuid4(),
                    signal_fingerprint=hashlib.sha256(f"load-{i}".encode()).hexdigest(),
                )
                for i in range(50)
            ],
        )
    with count_queries(context.engine) as queries:
        assert len(repository.list()) == 51
    assert len(queries) == small_count
    assert len(queries) <= 2
    page = repository.page(offset=0, limit=20)
    assert len(page.items) == 20 and page.total == 51
    assert repository.page(offset=100, limit=20).total == 51
    assert repository.page(offset=0, limit=20, team="%_").total == 0


@pytest.mark.integration
def test_single_cutoff_fixture_is_not_fabricated_into_a_backtest(context: _Context) -> None:
    # This prediction fixture has one cutoff, so it has no representable time interval.
    repository = PostgresModelRepository(context.engine)
    assert repository.list_models()
    assert repository.list_backtests() == ()
    page = repository.backtests_page(offset=0, limit=20)
    assert page.items == () and page.total == 0
