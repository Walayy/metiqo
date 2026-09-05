"""Smoke déterministe du benchmark gradient boosting walk-forward."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid5

import pytest

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.models import (
    BaselineEvaluator,
    BaselineRun,
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

_NAMESPACE = UUID("037cd91c-30e5-4a91-b3e6-7cd3f5c0868b")
_START = datetime(2025, 1, 1, tzinfo=UTC)
_CREATED_AT = datetime(2026, 9, 6, 20, 0, tzinfo=UTC)
_DATASET = uuid5(_NAMESPACE, "dataset")


def test_tabular_candidates_are_deterministic_and_final_test_is_never_read() -> None:
    examples = _examples()
    config = WalkForwardConfig(
        minimum_train_periods=20,
        validation_periods=10,
        final_test_periods=10,
    )
    plan = WalkForwardSplitter(config).split(examples)
    baselines = _baselines(plan)
    runner = TabularBenchmarkRunner(
        code_commit="abcdef1",
        features=TabularFeatureSpec(
            numeric_fields=("economy.team_a.kills_per_minute",),
            categorical_fields=(),
        ),
        parameters=TabularBenchmarkParameters(seed=42, calibration_bins=5),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    )

    result = runner.benchmark(plan, dataset_id=_DATASET, baseline_runs=baselines)
    repeated = runner.benchmark(plan, dataset_id=_DATASET, baseline_runs=baselines)

    assert result == repeated
    assert set(result.candidates) == {"gradient_boosting", "hist_gradient_boosting"}
    assert result.selected_candidate in result.candidates
    assert result.selected.hyperparameters["random_state"] == 42
    assert result.selected.metrics.sample_count == 30
    assert len(result.predictions) == 30
    assert all(Decimal() <= item.probability <= Decimal(1) for item in result.predictions)
    assert all(not candidate.fallback_folds for candidate in result.candidates.values())
    assert len(result.baseline_run_ids) == 3
    assert len(result.run_fingerprint) == 64
    assert result.predictions_fingerprint == result.selected.predictions_fingerprint
    assert result.promotion_gate.promotable is False
    assert result.promotion_gate.failures

    final_ids = {item.example_id for item in plan.final_test}
    assert final_ids.isdisjoint(item.example_id for item in result.predictions)
    altered = tuple(
        replace(
            item,
            feature_values=MappingProxyType(
                {
                    **item.feature_values,
                    "economy.team_a.kills_per_minute": Decimal("999999"),
                }
            ),
        )
        if item.example_id in final_ids
        else item
        for item in examples
    )
    altered_plan = WalkForwardSplitter(config).split(altered)
    assert altered_plan.fingerprint == plan.fingerprint
    assert runner.benchmark(altered_plan, dataset_id=_DATASET, baseline_runs=baselines) == result


def test_tabular_features_reject_bookmaker_inputs() -> None:
    with pytest.raises(ValueError, match="cote/bookmaker"):
        TabularFeatureSpec(numeric_fields=("bookmaker.odds",), categorical_fields=())


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
        features: dict[str, object] = {
            "economy.team_a.kills_per_minute": signal,
            "rating.difference": Decimal(),
        }
        values.append(
            WalkForwardExample(
                example_id=uuid5(_NAMESPACE, f"event-{index}"),
                feature_snapshot_id=uuid5(_NAMESPACE, f"snapshot-{index}"),
                cutoff_at=_START + timedelta(days=index),
                label=label,
                competition_id=uuid5(_NAMESPACE, "competition"),
                patch="14.1" if index < 30 else "14.2",
                international=False,
                feature_values=MappingProxyType(features),
                missingness=MappingProxyType({}),
            )
        )
    return tuple(values)
