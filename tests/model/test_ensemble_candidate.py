"""Comparaison OOF déterministe de l'ensemble rating/tabulaire."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid5

import pytest

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.models import (
    BaselineEvaluator,
    BaselineRun,
    EnsembleCandidateEvaluator,
    EnsembleSearchParameters,
    RatingBaselineTrainer,
    RatingSearchParameters,
    TabularBenchmarkParameters,
    TabularBenchmarkRunner,
    TabularFeatureSpec,
    WalkForwardConfig,
    WalkForwardExample,
    WalkForwardPlan,
    WalkForwardSplitter,
)

_NAMESPACE = UUID("8e762862-f298-4f52-9ca2-7bf673ebc8a1")
_START = datetime(2025, 1, 1, tzinfo=UTC)
_CREATED_AT = datetime(2026, 9, 6, 21, 0, tzinfo=UTC)
_DATASET = uuid5(_NAMESPACE, "dataset")


def test_ensemble_weight_is_oof_deterministic_and_can_be_disabled() -> None:
    plan = WalkForwardSplitter(
        WalkForwardConfig(
            minimum_train_periods=20,
            validation_periods=10,
            final_test_periods=10,
        )
    ).split(_examples())
    baselines = _baselines(plan)
    benchmark = TabularBenchmarkRunner(
        code_commit="abcdef1",
        features=TabularFeatureSpec(
            numeric_fields=("economy.team_a.kills_per_minute",),
            categorical_fields=(),
        ),
        parameters=TabularBenchmarkParameters(seed=42, calibration_bins=5),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).benchmark(plan, dataset_id=_DATASET, baseline_runs=baselines)
    evaluator = EnsembleCandidateEvaluator(
        code_commit="abcdef1",
        search=EnsembleSearchParameters(
            rating_weights=(Decimal("0.25"), Decimal("0.5"), Decimal("0.75")),
            calibration_bins=5,
        ),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    )

    result = evaluator.evaluate(benchmark, baseline_runs=baselines)

    assert evaluator.evaluate(benchmark, baseline_runs=baselines) == result
    assert result.candidate_weights == (
        Decimal("0.2500"),
        Decimal("0.5000"),
        Decimal("0.7500"),
    )
    assert set(result.candidate_evaluations) == {"0.2500", "0.5000", "0.7500"}
    assert result.selected_rating_weight in result.candidate_weights
    assert result.metrics.sample_count == 30
    assert len(result.predictions) == 30
    assert result.enabled is False
    assert result.decision.reasons
    assert len(result.decision.comparisons) == 4
    final_ids = {item.example_id for item in plan.final_test}
    assert final_ids.isdisjoint(item.example_id for item in result.predictions)


def test_ensemble_weights_exclude_standalone_endpoints() -> None:
    with pytest.raises(ValueError, match="strictement"):
        EnsembleSearchParameters(rating_weights=(Decimal(0), Decimal(1)))


def _baselines(plan: WalkForwardPlan) -> tuple[BaselineRun, ...]:
    simple = BaselineEvaluator(
        code_commit="abcdef1",
        calibration_bins=5,
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).evaluate(plan, dataset_id=_DATASET)
    rating = RatingBaselineTrainer(
        code_commit="abcdef1",
        search=RatingSearchParameters(candidate_scales=(Decimal("400"),)),
        calibration_bins=5,
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).train(plan, dataset_id=_DATASET)
    return (*simple, rating.run)


def _examples() -> tuple[WalkForwardExample, ...]:
    values: list[WalkForwardExample] = []
    for index in range(60):
        label = index % 2 == 0
        signal = Decimal("1") if label else Decimal("-1")
        values.append(
            WalkForwardExample(
                example_id=uuid5(_NAMESPACE, f"event-{index}"),
                feature_snapshot_id=uuid5(_NAMESPACE, f"snapshot-{index}"),
                cutoff_at=_START + timedelta(days=index),
                label=label,
                competition_id=uuid5(_NAMESPACE, "competition"),
                patch="14.1" if index < 30 else "14.2",
                international=False,
                feature_values=MappingProxyType(
                    {
                        "economy.team_a.kills_per_minute": signal,
                        "rating.difference": Decimal(),
                    }
                ),
                missingness=MappingProxyType({}),
            )
        )
    return tuple(values)
