"""Preuves de calibration OOS et de détection des dérives par segment."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid5

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.models import (
    BaselineEvaluator,
    BaselinePrediction,
    BaselineRun,
    CalibrationSearchParameters,
    CalibratorTrainer,
    EnsembleCandidateEvaluator,
    EnsembleCandidateRun,
    EnsembleSearchParameters,
    RatingBaselineTrainer,
    RatingSearchParameters,
    TabularBenchmarkParameters,
    TabularBenchmarkRun,
    TabularBenchmarkRunner,
    TabularFeatureSpec,
    WalkForwardConfig,
    WalkForwardExample,
    WalkForwardPlan,
    WalkForwardSplitter,
    evaluate_calibration_segments,
)

_NAMESPACE = UUID("946a4b0a-0ce4-481c-b129-1d4aa1fb5e75")
_START = datetime(2025, 1, 1, tzinfo=UTC)
_CREATED_AT = datetime(2026, 9, 6, 22, 0, tzinfo=UTC)
_DATASET = uuid5(_NAMESPACE, "dataset")


def test_calibrators_use_distinct_future_oos_blocks_and_ignore_final_test() -> None:
    examples = _examples()
    config = WalkForwardConfig(
        minimum_train_periods=20,
        validation_periods=10,
        final_test_periods=10,
    )
    plan = WalkForwardSplitter(config).split(examples)
    baselines, benchmark, ensemble = _sources(plan)
    trainer = CalibratorTrainer(
        code_commit="abcdef1",
        search=CalibrationSearchParameters(
            minimum_fit_periods=10,
            validation_periods=5,
            calibration_bins=5,
            segment_min_samples=5,
            seed=42,
        ),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    )

    artifact = trainer.train(plan, benchmark=benchmark, ensemble=ensemble)

    assert trainer.train(plan, benchmark=benchmark, ensemble=ensemble) == artifact
    assert artifact.source_kind == "tabular"
    assert artifact.ensemble_run_id is None
    assert set(artifact.candidate_evaluations) == {"platt", "isotonic"}
    assert artifact.method in artifact.candidate_evaluations
    assert artifact.metrics.sample_count == 20
    assert len(artifact.oos_predictions) == 20
    assert artifact.calibration_slope.is_finite()
    assert artifact.calibration_intercept.is_finite()
    assert Decimal() <= artifact.calibrate(Decimal("0.4")) <= Decimal(1)
    final_ids = {item.example_id for item in plan.final_test}
    assert final_ids.isdisjoint(item.example_id for item in artifact.oos_predictions)

    altered = tuple(
        replace(
            item,
            feature_values=MappingProxyType(
                {**item.feature_values, "economy.team_a.kills_per_minute": Decimal("999999")}
            ),
        )
        if item.example_id in final_ids
        else item
        for item in examples
    )
    altered_plan = WalkForwardSplitter(config).split(altered)
    assert altered_plan.fingerprint == plan.fingerprint
    assert trainer.train(altered_plan, benchmark=benchmark, ensemble=ensemble) == artifact
    assert len(baselines) == 3


def test_segment_calibration_marks_material_drift() -> None:
    plan = WalkForwardSplitter(
        WalkForwardConfig(
            minimum_train_periods=20,
            validation_periods=10,
            final_test_periods=10,
        )
    ).split(_examples())
    wrong = tuple(
        BaselinePrediction(
            example_id=item.example_id,
            fold_index=0,
            cutoff_at=item.cutoff_at,
            label=item.label,
            probability=Decimal("0.01") if item.label else Decimal("0.99"),
        )
        for item in plan.oof_validation
    )

    reports = evaluate_calibration_segments(
        wrong,
        plan=plan,
        bin_count=5,
        minimum_sample=5,
        drift_ece_threshold=Decimal("0.10"),
    )

    assert reports
    assert all(not item.low_sample for item in reports)
    assert all(item.drift_detected for item in reports)


def _sources(
    plan: WalkForwardPlan,
) -> tuple[tuple[BaselineRun, ...], TabularBenchmarkRun, EnsembleCandidateRun]:
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
    baselines = (*simple, rating.run)
    benchmark = TabularBenchmarkRunner(
        code_commit="abcdef1",
        features=TabularFeatureSpec(
            numeric_fields=("economy.team_a.kills_per_minute",),
            categorical_fields=(),
        ),
        parameters=TabularBenchmarkParameters(seed=42, calibration_bins=5),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).benchmark(plan, dataset_id=_DATASET, baseline_runs=baselines)
    ensemble = EnsembleCandidateEvaluator(
        code_commit="abcdef1",
        search=EnsembleSearchParameters(
            rating_weights=(Decimal("0.25"), Decimal("0.5"), Decimal("0.75")),
            calibration_bins=5,
        ),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).evaluate(benchmark, baseline_runs=baselines)
    return baselines, benchmark, ensemble


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
