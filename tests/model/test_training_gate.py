"""Gate P4 complet et rejeu de prédiction depuis l'artefact vérifié."""

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
    CalibrationSearchParameters,
    CalibratorTrainer,
    EnsembleCandidateEvaluator,
    RatingBaselineTrainer,
    StoredTrainingDataset,
    TabularBenchmarkParameters,
    TabularBenchmarkRunner,
    TabularFeatureSpec,
    UncertaintyArtifactBuilder,
    WalkForwardConfig,
    WalkForwardExample,
    WalkForwardSplitter,
    build_reproducible_artifact,
    reproduce_prediction,
)

_NAMESPACE = UUID("37b57bd8-ea99-4b66-9ca9-f38c1342e4c3")
_START = datetime(2025, 1, 1, tzinfo=UTC)
_CREATED_AT = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
_DATASET_ID = uuid5(_NAMESPACE, "dataset")


def test_training_gate_beats_baselines_and_reproduces_exact_snapshot() -> None:
    examples = _examples()
    plan = WalkForwardSplitter(
        WalkForwardConfig(
            minimum_train_periods=20,
            validation_periods=10,
            final_test_periods=10,
        )
    ).split(examples)
    clock = FixedClock(UtcInstant(_CREATED_AT))
    simple = BaselineEvaluator(
        code_commit="abcdef1",
        calibration_bins=5,
        clock=clock,
    ).evaluate(plan, dataset_id=_DATASET_ID)
    rating = RatingBaselineTrainer(
        code_commit="abcdef1",
        calibration_bins=5,
        clock=clock,
    ).train(plan, dataset_id=_DATASET_ID)
    baselines = (*simple, rating.run)
    benchmark = TabularBenchmarkRunner(
        code_commit="abcdef1",
        features=TabularFeatureSpec(
            numeric_fields=("economy.team_a.kills_per_minute",),
            categorical_fields=(),
        ),
        parameters=TabularBenchmarkParameters(seed=42, calibration_bins=5),
        clock=clock,
    ).benchmark(plan, dataset_id=_DATASET_ID, baseline_runs=baselines)
    ensemble = EnsembleCandidateEvaluator(
        code_commit="abcdef1",
        clock=clock,
    ).evaluate(benchmark, baseline_runs=baselines)
    calibrator = CalibratorTrainer(
        code_commit="abcdef1",
        search=CalibrationSearchParameters(
            minimum_fit_periods=10,
            validation_periods=5,
            calibration_bins=5,
            segment_min_samples=5,
            seed=42,
        ),
        clock=clock,
    ).train(plan, benchmark=benchmark, ensemble=ensemble)
    uncertainty = UncertaintyArtifactBuilder(
        code_commit="abcdef1",
        clock=clock,
    ).build(calibrator)

    payload, first = build_reproducible_artifact(
        _dataset(),
        plan=plan,
        benchmark=benchmark,
        rating=rating.artifact,
        ensemble=ensemble,
        calibrator=calibrator,
        uncertainty=uncertainty,
    )
    example = min(plan.final_test, key=lambda item: (item.cutoff_at, item.example_id))
    repeated = reproduce_prediction(payload, dataset_id=_DATASET_ID, example=example)

    assert benchmark.promotion_gate.promotable is True
    assert benchmark.promotion_gate.failures == ()
    assert first == repeated
    assert first.feature_snapshot_id == example.feature_snapshot_id
    assert Decimal() <= first.calibrated_probability <= Decimal(1)
    assert b"bookmaker" not in payload.lower()
    with pytest.raises(ValueError, match="feature snapshot"):
        reproduce_prediction(
            payload,
            dataset_id=_DATASET_ID,
            example=replace(example, feature_snapshot_id=uuid5(_NAMESPACE, "wrong-snapshot")),
        )


def _examples() -> tuple[WalkForwardExample, ...]:
    examples: list[WalkForwardExample] = []
    for index in range(70):
        label = index % 4 != 0
        signal = Decimal("4") if label else Decimal("-4")
        examples.append(
            WalkForwardExample(
                example_id=uuid5(_NAMESPACE, f"event-{index}"),
                feature_snapshot_id=uuid5(_NAMESPACE, f"snapshot-{index}"),
                cutoff_at=_START + timedelta(days=index),
                label=label,
                competition_id=uuid5(_NAMESPACE, "competition"),
                patch="14.1" if index < 35 else "14.2",
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
    return tuple(examples)


def _dataset() -> StoredTrainingDataset:
    return StoredTrainingDataset(
        dataset_id=_DATASET_ID,
        market="game_winner",
        provider="oracles_elixir",
        dataset="test",
        dataset_version="game-winner-dataset-v1",
        feature_set_id=uuid5(_NAMESPACE, "feature-set"),
        feature_set_version="full-v1",
        feature_set_hash="a" * 64,
        label_definition="team-a-win-v1",
        quality_filter=MappingProxyType({}),
        period_start=_START,
        period_end=_START + timedelta(days=70),
        cutoff_min=_START,
        cutoff_max=_START + timedelta(days=69),
        competition_ids=(uuid5(_NAMESPACE, "competition"),),
        oe_snapshot_ids=(uuid5(_NAMESPACE, "oe-snapshot"),),
        exclusions=(),
        example_count=70,
        exclusion_count=0,
        examples_fingerprint="b" * 64,
        dataset_hash="c" * 64,
        code_commit="abcdef1",
        created_at=_CREATED_AT,
        examples=(),
    )
