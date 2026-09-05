"""Propriétés des intervalles et scénarios couverture/OOD."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid5

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.models import (
    BaselinePrediction,
    CalibrationCandidateEvaluation,
    CalibrationSearchParameters,
    CalibratorArtifact,
    UncertaintyArtifactBuilder,
    UncertaintySearchParameters,
    evaluate_binary_probabilities,
)

_NAMESPACE = UUID("ccab4a21-ee39-4c34-81e4-790e614577c1")
_CREATED_AT = datetime(2026, 9, 6, 23, 0, tzinfo=UTC)


def test_uncertainty_interval_properties_hold_for_every_probability() -> None:
    artifact = UncertaintyArtifactBuilder(
        code_commit="abcdef1",
        search=UncertaintySearchParameters(target_coverage=Decimal("0.90")),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).build(_calibrator())

    repeated = UncertaintyArtifactBuilder(
        code_commit="abcdef1",
        search=UncertaintySearchParameters(target_coverage=Decimal("0.90")),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).build(_calibrator())

    assert artifact == repeated
    assert set(artifact.candidates) == {
        "absolute_conformal",
        "temporal_fold_conformal",
    }
    assert artifact.candidates[artifact.method].empirical_coverage >= Decimal("0.90")
    for index in range(101):
        estimate = artifact.estimate(
            Decimal(index) / Decimal(100),
            data_coverage=Decimal(1),
            training_domain_distance=Decimal(),
        )
        assert Decimal() <= estimate.p_low <= estimate.p50 <= estimate.p_high <= Decimal(1)
        assert Decimal() <= estimate.confidence <= Decimal(1)


def test_low_coverage_and_ood_widen_interval_and_reduce_confidence() -> None:
    artifact = UncertaintyArtifactBuilder(
        code_commit="abcdef1",
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).build(_calibrator())

    clean = artifact.estimate(
        Decimal("0.7"),
        data_coverage=Decimal(1),
        training_domain_distance=Decimal(),
    )
    sparse = artifact.estimate(
        Decimal("0.7"),
        data_coverage=Decimal("0.5"),
        training_domain_distance=Decimal(),
    )
    ood = artifact.estimate(
        Decimal("0.7"),
        data_coverage=Decimal(1),
        training_domain_distance=Decimal(4),
    )
    abstained = artifact.estimate(
        Decimal("0.7"),
        data_coverage=Decimal("0.5"),
        training_domain_distance=Decimal(5),
    )

    assert sparse.p_high - sparse.p_low > clean.p_high - clean.p_low
    assert ood.p_high - ood.p_low > clean.p_high - clean.p_low
    assert sparse.confidence < clean.confidence
    assert ood.confidence < clean.confidence
    assert "LOW_DATA_COVERAGE" in sparse.reasons
    assert "OUT_OF_DISTRIBUTION" in ood.reasons
    assert abstained.p_low == Decimal() and abstained.p_high == Decimal(1)
    assert abstained.confidence == Decimal()
    assert "ABSTENTION_REQUIRED" in abstained.reasons


def _calibrator() -> CalibratorArtifact:
    predictions = tuple(
        BaselinePrediction(
            example_id=uuid5(_NAMESPACE, f"example-{index}"),
            fold_index=index // 10,
            cutoff_at=_CREATED_AT + timedelta(days=index),
            label=index % 2 == 0,
            probability=Decimal("0.8") if index % 2 == 0 else Decimal("0.2"),
        )
        for index in range(20)
    )
    metrics = evaluate_binary_probabilities(predictions, bin_count=5)
    evaluations = MappingProxyType(
        {
            method: CalibrationCandidateEvaluation(
                method=method,
                metrics=metrics,
                calibration_slope=Decimal(1),
                calibration_intercept=Decimal(),
                oos_predictions_fingerprint="b" * 64,
            )
            for method in ("platt", "isotonic")
        }
    )
    return CalibratorArtifact(
        artifact_id=uuid5(_NAMESPACE, "calibrator"),
        dataset_id=uuid5(_NAMESPACE, "dataset"),
        benchmark_run_id=uuid5(_NAMESPACE, "benchmark"),
        ensemble_run_id=None,
        market="game_winner",
        source_kind="tabular",
        calibrator_version="test-calibrator-v1",
        walk_forward_fingerprint="a" * 64,
        method="isotonic",
        parameters=MappingProxyType(
            {"x_thresholds": ["0.00000000", "1.00000000"], "y_thresholds": ["0", "1"]}
        ),
        search=CalibrationSearchParameters(),
        candidate_evaluations=evaluations,
        metrics=metrics,
        calibration_slope=Decimal(1),
        calibration_intercept=Decimal(),
        segment_reports=(),
        oos_predictions_fingerprint="b" * 64,
        artifact_fingerprint="c" * 64,
        code_commit="abcdef1",
        created_at=_CREATED_AT,
        oos_predictions=predictions,
    )
