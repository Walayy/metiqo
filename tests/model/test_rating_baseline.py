"""Conversion probabiliste et sélection OOF de la baseline rating."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid5

import pytest

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.models import (
    RATING,
    RatingBaselineTrainer,
    RatingSearchParameters,
    WalkForwardConfig,
    WalkForwardExample,
    WalkForwardSplitter,
    rating_win_probability,
)

_NAMESPACE = UUID("f4ea0d5a-08e2-461c-8d51-66b1df6e8118")
_START = datetime(2026, 1, 1, tzinfo=UTC)
_CREATED_AT = datetime(2026, 9, 6, 19, 0, tzinfo=UTC)


def test_rating_probability_is_bounded_monotone_and_symmetric() -> None:
    differences = tuple(
        Decimal(value) for value in ("-1000000", "-800", "-200", "0", "200", "800", "1000000")
    )
    for scale in (Decimal("200"), Decimal("400"), Decimal("800")):
        probabilities = tuple(
            rating_win_probability(difference, scale=scale) for difference in differences
        )
        assert all(Decimal() <= probability <= Decimal(1) for probability in probabilities)
        assert probabilities == tuple(sorted(probabilities))
        for difference in differences:
            direct = rating_win_probability(difference, scale=scale)
            inverse = rating_win_probability(-difference, scale=scale)
            assert abs(direct + inverse - Decimal(1)) <= Decimal("0.00000001")
    assert rating_win_probability(Decimal(), scale=Decimal("400")) == Decimal("0.50000000")
    with pytest.raises(ValueError, match="positive"):
        rating_win_probability(Decimal(), scale=Decimal())
    with pytest.raises(ValueError, match="finie"):
        rating_win_probability(Decimal(), scale=Decimal("Infinity"))
    with pytest.raises(ValueError, match="fini"):
        rating_win_probability(Decimal("Infinity"), scale=Decimal("400"))


def test_rating_tuning_uses_only_oof_and_produces_reproducible_artifact() -> None:
    examples = _examples()
    config = WalkForwardConfig(
        minimum_train_periods=2,
        validation_periods=2,
        final_test_periods=2,
    )
    plan = WalkForwardSplitter(config).split(examples)
    trainer = RatingBaselineTrainer(
        code_commit="abcdef1",
        search=RatingSearchParameters(
            candidate_scales=(Decimal("200"), Decimal("400"), Decimal("800"))
        ),
        calibration_bins=5,
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    )

    result = trainer.train(plan, dataset_id=uuid5(_NAMESPACE, "dataset"))
    repeated = trainer.train(plan, dataset_id=uuid5(_NAMESPACE, "dataset"))

    assert result == repeated
    assert result.artifact.selected_scale == Decimal("200.0000")
    assert result.artifact.selection_scope == "oof_validation"
    assert result.artifact.selection_metric == "log_loss"
    assert set(result.artifact.candidate_metrics) == {"200.0000", "400.0000", "800.0000"}
    assert result.run.baseline_name == RATING
    assert result.run.artifact_id == result.artifact.artifact_id
    assert result.run.metrics == result.artifact.candidate_metrics["200.0000"]
    assert len(result.run.predictions) == 4
    assert all(Decimal() <= item.probability <= Decimal(1) for item in result.run.predictions)
    final_ids = {item.example_id for item in plan.final_test}
    assert final_ids.isdisjoint(item.example_id for item in result.run.predictions)

    altered_final = tuple(
        replace(
            item,
            feature_values=MappingProxyType({"rating.difference": Decimal("-999999")}),
        )
        if item.example_id in final_ids
        else item
        for item in examples
    )
    altered_plan = WalkForwardSplitter(config).split(altered_final)
    assert altered_plan.fingerprint == plan.fingerprint
    assert trainer.train(altered_plan, dataset_id=uuid5(_NAMESPACE, "dataset")) == result

    missing = list(examples)
    missing[2] = replace(missing[2], feature_values=MappingProxyType({}))
    with pytest.raises(ValueError, match="requise absente"):
        trainer.train(
            WalkForwardSplitter(config).split(missing),
            dataset_id=uuid5(_NAMESPACE, "dataset"),
        )


def _examples() -> tuple[WalkForwardExample, ...]:
    labels = (False, True, True, False, True, False, False, True)
    differences = (
        Decimal(),
        Decimal(),
        Decimal("400"),
        Decimal("-400"),
        Decimal("200"),
        Decimal("-200"),
        Decimal("999999"),
        Decimal("-999999"),
    )
    return tuple(
        WalkForwardExample(
            example_id=uuid5(_NAMESPACE, f"event-{index}"),
            feature_snapshot_id=uuid5(_NAMESPACE, f"snapshot-{index}"),
            cutoff_at=_START + timedelta(days=index),
            label=labels[index],
            competition_id=uuid5(_NAMESPACE, "competition"),
            patch="14.1",
            international=False,
            feature_values=MappingProxyType({"rating.difference": differences[index]}),
            missingness=MappingProxyType({"rating.difference": False}),
        )
        for index in range(len(labels))
    )
