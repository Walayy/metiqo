"""Métriques et baselines probabilistes sur validations OOF communes."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid5

import pytest

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.models import (
    COMPETITION_PRIOR,
    RECENT_FORM,
    BaselineEvaluator,
    BaselinePrediction,
    WalkForwardConfig,
    WalkForwardExample,
    WalkForwardSplitter,
    assert_baseline_runs_comparable,
    evaluate_binary_probabilities,
)

_NAMESPACE = UUID("976413a2-6eb0-45c7-87a8-726e878e67ef")
_START = datetime(2026, 1, 1, tzinfo=UTC)
_CREATED_AT = datetime(2026, 9, 6, 18, 0, tzinfo=UTC)


def test_binary_metrics_report_log_loss_brier_and_reliability() -> None:
    predictions = (
        _prediction("metric-win", True, Decimal("0.8")),
        _prediction("metric-loss", False, Decimal("0.2")),
    )

    report = evaluate_binary_probabilities(predictions, bin_count=5)

    assert report.sample_count == 2
    assert report.log_loss == Decimal("0.223144")
    assert report.brier_score == Decimal("0.040000")
    assert report.calibration_ece == Decimal("0.200000")
    assert tuple(item.count for item in report.calibration_bins) == (1, 1)
    assert report.document()["calibration"] == {
        "bin_count": 5,
        "ece": "0.200000",
        "reliability": [item.document() for item in report.calibration_bins],
    }

    with pytest.raises(ValueError, match="identifiants uniques"):
        evaluate_binary_probabilities((predictions[0], predictions[0]))


def test_baselines_share_exact_oof_scope_and_leave_final_test_untouched() -> None:
    examples = _examples()
    plan = WalkForwardSplitter(
        WalkForwardConfig(
            minimum_train_periods=2,
            validation_periods=2,
            final_test_periods=2,
        )
    ).split(examples)

    runs = BaselineEvaluator(
        code_commit="abcdef1",
        calibration_bins=5,
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    ).evaluate(plan, dataset_id=uuid5(_NAMESPACE, "dataset"))
    comparison = assert_baseline_runs_comparable(runs)

    assert tuple(run.baseline_name for run in runs) == (COMPETITION_PRIOR, RECENT_FORM)
    assert comparison.sample_count == 4
    assert all(run.evaluation_split == "oof_validation" for run in runs)
    assert all(run.walk_forward_fingerprint == plan.fingerprint for run in runs)
    assert all(run.metrics.sample_count == 4 for run in runs)
    assert all(len(run.run_fingerprint) == 64 for run in runs)
    assert all(run.created_at == _CREATED_AT for run in runs)
    final_ids = {item.example_id for item in plan.final_test}
    assert all(final_ids.isdisjoint(item.example_id for item in run.predictions) for run in runs)

    prior = runs[0]
    assert tuple(item.probability for item in prior.predictions) == (
        Decimal("0.5"),
        Decimal("0.5"),
        Decimal("0.625"),
        Decimal("0.25"),
    )
    form = runs[1]
    assert tuple(item.probability for item in form.predictions) == (
        Decimal("0.7"),
        Decimal("0.5"),
        Decimal("0.9"),
        Decimal("0.8"),
    )
    assert tuple(item.example_id for item in prior.predictions) == tuple(
        item.example_id for item in form.predictions
    )

    incompatible = replace(runs[1], dataset_id=uuid5(_NAMESPACE, "other-dataset"))
    with pytest.raises(ValueError, match="même dataset"):
        assert_baseline_runs_comparable((runs[0], incompatible))


def _prediction(label: str, outcome: bool, probability: Decimal) -> BaselinePrediction:
    return BaselinePrediction(
        example_id=uuid5(_NAMESPACE, label),
        fold_index=0,
        cutoff_at=_START,
        label=outcome,
        probability=probability,
    )


def _examples() -> tuple[WalkForwardExample, ...]:
    competition_a = uuid5(_NAMESPACE, "competition-a")
    competition_b = uuid5(_NAMESPACE, "competition-b")
    labels = (True, False, True, False, True, False, True, False)
    competitions = (
        competition_a,
        competition_a,
        competition_a,
        competition_b,
        competition_a,
        competition_b,
        competition_a,
        competition_b,
    )
    form: tuple[dict[str, object], ...] = (
        {},
        {},
        {"form.team_a.ewm_win_rate": Decimal("0.8"), "form.team_b.ewm_win_rate": "0.4"},
        {},
        {"form.team_a.ewm_win_rate": Decimal("0.9")},
        {"form.team_b.ewm_win_rate": Decimal("0.2")},
        {"form.team_a.ewm_win_rate": Decimal("1")},
        {"form.team_b.ewm_win_rate": Decimal("1")},
    )
    return tuple(
        WalkForwardExample(
            example_id=uuid5(_NAMESPACE, f"event-{index}"),
            feature_snapshot_id=uuid5(_NAMESPACE, f"snapshot-{index}"),
            cutoff_at=_START + timedelta(days=index),
            label=labels[index],
            competition_id=competitions[index],
            patch="14.1",
            international=False,
            feature_values=MappingProxyType(form[index]),
            missingness=MappingProxyType({}),
        )
        for index in range(len(labels))
    )
