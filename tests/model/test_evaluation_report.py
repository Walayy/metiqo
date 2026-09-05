"""Métriques complètes, segments, dérive et politique de promotion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid5

import pytest

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.models import (
    BaselinePrediction,
    CalibrationCandidateEvaluation,
    CalibrationSearchParameters,
    CalibratorArtifact,
    EvaluationContext,
    EvaluationReportBuilder,
    EvaluationReportParameters,
    UncertaintyArtifact,
    UncertaintyArtifactBuilder,
    WalkForwardConfig,
    WalkForwardExample,
    WalkForwardPlan,
    WalkForwardSplitter,
    evaluate_binary_probabilities,
)

_NAMESPACE = UUID("f1cb9f57-8bb8-43aa-884c-1a13c8387698")
_START = datetime(2025, 1, 1, tzinfo=UTC)
_CREATED_AT = datetime(2026, 9, 7, tzinfo=UTC)


def test_report_calculates_probabilistic_metrics_and_observed_odds_segments() -> None:
    plan, calibrator, uncertainty = _artifacts(wrong_second_patch=False)
    contexts = {
        item.example_id: EvaluationContext(
            observed_market_probability=(Decimal("0.35") if index < 4 else Decimal("0.65"))
        )
        for index, item in enumerate(calibrator.oos_predictions)
    }
    builder = EvaluationReportBuilder(
        code_commit="abcdef1",
        parameters=EvaluationReportParameters(
            calibration_bins=5,
            minimum_segment_samples=3,
        ),
    )

    report = builder.build(
        plan,
        calibrator=calibrator,
        uncertainty=uncertainty,
        contexts=contexts,
    )

    assert (
        builder.build(
            plan,
            calibrator=calibrator,
            uncertainty=uncertainty,
            contexts=contexts,
        )
        == report
    )
    assert report.overall.sample_count == 8
    assert report.overall.positive_count == report.overall.negative_count == 4
    assert report.overall.log_loss == Decimal("0.223144")
    assert report.overall.brier_score == Decimal("0.040000")
    assert report.overall.roc_auc == Decimal("1.000000")
    assert report.overall.calibration_ece == Decimal("0.200000")
    assert report.overall.sharpness == Decimal("0.400000")
    assert report.overall.interval_coverage == Decimal("1.000000")
    assert report.overall.interval_evaluated_count == 8
    assert report.overall.abstention_count == 0
    assert report.observed_odds_count == 8
    assert {item.dimension for item in report.segments} == {
        "format",
        "league",
        "odds_bucket",
        "patch",
        "stage",
    }
    odds_segments = [item for item in report.segments if item.dimension == "odds_bucket"]
    assert [(item.value, item.sample_count) for item in odds_segments] == [
        ("over_60_pct", 4),
        ("under_40_pct", 4),
    ]
    assert report.outsider_robustness is not None
    assert report.outsider_robustness.outsider_sample_count == 4
    assert report.outsider_robustness.reference_sample_count == 4
    assert report.outsider_robustness.degraded is False
    assert all(item.metrics.sample_count == item.sample_count for item in report.segments)
    assert report.document()["odds_policy"] == "observed_only"

    with pytest.raises(ValueError, match="accuracy ou ROC-AUC seules"):
        report.promotion_policy.assert_valid_basis(("accuracy",))
    report.promotion_policy.assert_valid_basis(("log_loss", "accuracy"))


def test_report_marks_low_samples_drift_and_abstention_without_fabricating_odds() -> None:
    plan, calibrator, uncertainty = _artifacts(wrong_second_patch=True)
    last_id = calibrator.oos_predictions[-1].example_id
    contexts = {
        item.example_id: EvaluationContext(
            training_domain_distance=Decimal(5) if item.example_id == last_id else Decimal()
        )
        for item in calibrator.oos_predictions
    }
    builder = EvaluationReportBuilder(
        code_commit="abcdef1",
        parameters=EvaluationReportParameters(
            calibration_bins=5,
            minimum_segment_samples=3,
            log_loss_drift_threshold=Decimal("0.05"),
            calibration_drift_threshold=Decimal("0.05"),
            interval_coverage_drift_threshold=Decimal("0.05"),
            abstention_drift_threshold=Decimal("0.05"),
        ),
    )

    report = builder.build(
        plan,
        calibrator=calibrator,
        uncertainty=uncertainty,
        contexts=contexts,
    )

    bad_patch = next(
        item for item in report.segments if item.dimension == "patch" and item.value == "14.2"
    )
    rare_stage = next(
        item for item in report.segments if item.dimension == "stage" and item.value == "rare"
    )
    assert bad_patch.drift_detected
    assert "LOG_LOSS_DRIFT" in bad_patch.drift_reasons
    assert not bad_patch.low_sample
    assert rare_stage.sample_count == 1
    assert rare_stage.low_sample
    assert not rare_stage.drift_detected
    assert report.drifted_segment_count >= 1
    assert report.overall.abstention_count == 1
    assert report.overall.interval_evaluated_count == 7
    assert report.observed_odds_count == 0
    assert report.outsider_robustness is None
    assert all(item.dimension != "odds_bucket" for item in report.segments)


def _artifacts(
    *,
    wrong_second_patch: bool,
) -> tuple[WalkForwardPlan, CalibratorArtifact, UncertaintyArtifact]:
    plan = WalkForwardSplitter(
        WalkForwardConfig(
            minimum_train_periods=2,
            validation_periods=2,
            final_test_periods=2,
        )
    ).split(_examples())
    predictions = tuple(
        BaselinePrediction(
            example_id=item.example_id,
            fold_index=index // 2,
            cutoff_at=item.cutoff_at,
            label=item.label,
            probability=(
                Decimal("0.2")
                if wrong_second_patch and item.patch == "14.2" and item.label
                else Decimal("0.8")
                if wrong_second_patch and item.patch == "14.2"
                else Decimal("0.8")
                if item.label
                else Decimal("0.2")
            ),
        )
        for index, item in enumerate(plan.oof_validation)
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
    calibrator = CalibratorArtifact(
        artifact_id=uuid5(_NAMESPACE, f"calibrator-{wrong_second_patch}"),
        dataset_id=uuid5(_NAMESPACE, "dataset"),
        benchmark_run_id=uuid5(_NAMESPACE, "benchmark"),
        ensemble_run_id=None,
        market="game_winner",
        source_kind="tabular",
        calibrator_version="test-calibrator-v1",
        walk_forward_fingerprint=plan.fingerprint,
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
    uncertainty = UncertaintyArtifactBuilder(
        code_commit="abcdef1",
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).build(calibrator)
    return plan, calibrator, uncertainty


def _examples() -> tuple[WalkForwardExample, ...]:
    values: list[WalkForwardExample] = []
    for index in range(12):
        values.append(
            WalkForwardExample(
                example_id=uuid5(_NAMESPACE, f"event-{index}"),
                feature_snapshot_id=uuid5(_NAMESPACE, f"snapshot-{index}"),
                cutoff_at=_START + timedelta(days=index),
                label=index % 2 == 0,
                competition_id=uuid5(_NAMESPACE, "competition"),
                patch="14.1" if index < 6 else "14.2",
                international=False,
                feature_values=MappingProxyType(
                    {
                        "context.best_of": 3,
                        "context.league": "LCS" if index < 6 else "LEC",
                        "context.stage": "rare" if index == 2 else "regular",
                    }
                ),
                missingness=MappingProxyType({}),
            )
        )
    return tuple(values)
