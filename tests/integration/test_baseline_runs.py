"""Persistance append-only des baselines sur un dataset ML réel."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from metiquo.canonical.rosters import CanonicalRosterBuilder
from metiquo.features import FeatureDatasetBuilder
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.models import (
    BaselineEvaluator,
    BaselineRunRepository,
    GameWinnerDatasetBuilder,
    GameWinnerDatasetRequest,
    TrainingExampleRepository,
    WalkForwardConfig,
    WalkForwardSplitter,
    assert_baseline_runs_comparable,
)
from tests.integration.test_canonical_rosters import _seed_rosters
from tests.integration.test_migrations import alembic_config

_KNOWLEDGE_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
_CREATED_AT = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)


@pytest.mark.integration
def test_baseline_runs_roundtrip_are_comparable_and_append_only(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    source_dataset = f"ml_003_{uuid4().hex}"
    _seed_rosters(engine, source_dataset)
    CanonicalRosterBuilder(
        engine=engine,
        clock=FixedClock(UtcInstant(_KNOWLEDGE_AT)),
    ).build(dataset=source_dataset)
    FeatureDatasetBuilder(
        engine=engine,
        code_commit="abcdef1",
        dataset=source_dataset,
    ).rebuild_from(date(2026, 8, 1))
    dataset = GameWinnerDatasetBuilder(
        engine=engine,
        code_commit="abcdef1",
        dataset=source_dataset,
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).build(
        GameWinnerDatasetRequest(
            period_start=datetime(2026, 8, 1, tzinfo=UTC),
            period_end=datetime(2026, 9, 1, tzinfo=UTC),
        )
    )
    examples = TrainingExampleRepository(engine=engine).load(dataset)
    synthetic_final = replace(
        examples[-1],
        example_id=uuid4(),
        feature_snapshot_id=uuid4(),
        cutoff_at=examples[-1].cutoff_at + timedelta(days=1),
    )
    plan = WalkForwardSplitter(
        WalkForwardConfig(
            minimum_train_periods=1,
            validation_periods=1,
            final_test_periods=1,
        )
    ).split((*examples, synthetic_final))
    runs = BaselineEvaluator(
        code_commit="abcdef1",
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).evaluate(plan, dataset_id=dataset.dataset_id)
    repository = BaselineRunRepository(engine=engine)

    stored = tuple(repository.record(run) for run in runs)

    assert_baseline_runs_comparable(stored)
    assert tuple(item.run_id for item in stored) == tuple(item.run_id for item in runs)
    assert tuple(item.predictions for item in stored) == tuple(item.predictions for item in runs)
    assert tuple(repository.record(run) for run in runs) == stored
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE ml.baseline_runs SET code_commit = '1234567' WHERE id = :id"),
            {"id": stored[0].run_id},
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE ml.baseline_predictions SET probability = 0.5 WHERE run_id = :id"),
            {"id": stored[0].run_id},
        )
    engine.dispose()
