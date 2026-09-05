"""Persistance append-only des baselines sur un dataset ML réel."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
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
    EnsembleCandidateEvaluator,
    EnsembleCandidateRepository,
    EnsembleSearchParameters,
    GameWinnerDatasetBuilder,
    GameWinnerDatasetRequest,
    RatingArtifactRepository,
    RatingBaselineTrainer,
    RatingSearchParameters,
    TabularBenchmarkParameters,
    TabularBenchmarkRepository,
    TabularBenchmarkRunner,
    TabularFeatureSpec,
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
    rating_result = RatingBaselineTrainer(
        code_commit="abcdef1",
        search=RatingSearchParameters(
            candidate_scales=(Decimal("200"), Decimal("400"), Decimal("800"))
        ),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).train(plan, dataset_id=dataset.dataset_id)
    artifact_repository = RatingArtifactRepository(engine=engine)
    stored_artifact = artifact_repository.record(rating_result.artifact)
    stored_rating_run = repository.record(rating_result.run)

    comparison = assert_baseline_runs_comparable((*stored, stored_rating_run))
    assert comparison.sample_count == 1
    assert stored_artifact == rating_result.artifact
    assert stored_rating_run.artifact_id == stored_artifact.artifact_id
    assert artifact_repository.record(rating_result.artifact) == stored_artifact
    benchmark = TabularBenchmarkRunner(
        code_commit="abcdef1",
        features=TabularFeatureSpec(
            numeric_fields=("rating.difference",),
            categorical_fields=(),
        ),
        parameters=TabularBenchmarkParameters(seed=42, calibration_bins=5),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).benchmark(
        plan,
        dataset_id=dataset.dataset_id,
        baseline_runs=(*stored, stored_rating_run),
    )
    benchmark_repository = TabularBenchmarkRepository(engine=engine)
    stored_benchmark = benchmark_repository.record(benchmark)

    assert stored_benchmark == benchmark
    assert benchmark_repository.record(benchmark) == stored_benchmark
    assert len(stored_benchmark.candidates) == 2
    assert all(len(candidate.predictions) == 1 for candidate in benchmark.candidates.values())
    ensemble = EnsembleCandidateEvaluator(
        code_commit="abcdef1",
        search=EnsembleSearchParameters(
            rating_weights=(Decimal("0.25"), Decimal("0.5"), Decimal("0.75")),
            calibration_bins=5,
        ),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).evaluate(stored_benchmark, baseline_runs=(*stored, stored_rating_run))
    ensemble_repository = EnsembleCandidateRepository(engine=engine)
    stored_ensemble = ensemble_repository.record(ensemble)

    assert stored_ensemble == ensemble
    assert ensemble_repository.record(ensemble) == stored_ensemble
    assert stored_ensemble.enabled is False
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE ml.baseline_runs SET code_commit = '1234567' WHERE id = :id"),
            {"id": stored[0].run_id},
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE ml.rating_artifacts SET selected_scale = 100 WHERE id = :id"),
            {"id": stored_artifact.artifact_id},
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE ml.baseline_predictions SET probability = 0.5 WHERE run_id = :id"),
            {"id": stored[0].run_id},
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE ml.tabular_benchmark_runs SET seed = 7 WHERE id = :id"),
            {"id": stored_benchmark.run_id},
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE ml.ensemble_candidate_runs SET enabled = true WHERE id = :id"),
            {"id": stored_ensemble.run_id},
        )
    engine.dispose()
