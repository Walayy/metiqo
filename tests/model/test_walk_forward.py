"""Découpes chronologiques, fit train-only et prédictions OOF."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid5

import pytest

from metiquo.features import (
    PreprocessorParameters,
    TrainingFeatureRow,
    TrainOnlyPreprocessor,
)
from metiquo.models import (
    FoldProbabilities,
    WalkForwardConfig,
    WalkForwardExample,
    WalkForwardSplitter,
    collect_oof_predictions,
    prepare_walk_forward,
)

_NAMESPACE = UUID("5cb59ca9-c104-48d1-8157-6f874fe4c3fd")
_START = datetime(2026, 1, 1, tzinfo=UTC)


def test_walk_forward_keeps_equal_cutoffs_together_and_final_test_untouched() -> None:
    examples = _examples()
    plan = WalkForwardSplitter(
        WalkForwardConfig(
            minimum_train_periods=2,
            validation_periods=2,
            final_test_periods=2,
        )
    ).split(tuple(reversed(examples)))

    assert len(plan.folds) == 2
    assert len(plan.fingerprint) == 64
    assert plan.fingerprint == WalkForwardSplitter(plan.config).split(examples).fingerprint
    assert len(plan.initial_train) == 3
    assert len(plan.oof_validation) == 4
    assert len(plan.final_test) == 2
    assert {item.example_id for item in plan.folds[0].train if item.cutoff_at == _START} == {
        examples[0].example_id,
        examples[1].example_id,
    }
    for fold in plan.folds:
        assert fold.train_cutoff_max < fold.validation_cutoff_min
        assert {item.example_id for item in fold.train}.isdisjoint(
            item.example_id for item in fold.validation
        )
    final_ids = {item.example_id for item in plan.final_test}
    assert final_ids.isdisjoint(
        item.example_id for fold in plan.folds for item in (*fold.train, *fold.validation)
    )
    assert plan.segments.patches["14.1"].initial_train == 3
    assert plan.segments.patches["14.2"].oof_validation == 4
    assert plan.segments.patches["14.3"].final_test == 2
    assert plan.segments.international["domestic"].total == 7
    assert plan.segments.international["international"].final_test == 2

    rows = tuple(
        TrainingFeatureRow(
            row_id=example.example_id,
            event_time=example.cutoff_at,
            numeric={
                "strength": Decimal("1000000")
                if example.example_id in final_ids
                else Decimal(index)
            },
            categorical={
                "patch": "future-only" if example.example_id in final_ids else example.patch
            },
        )
        for index, example in enumerate(examples)
    )
    prepared = prepare_walk_forward(
        plan,
        rows=rows,
        preprocessor=TrainOnlyPreprocessor(
            PreprocessorParameters(
                numeric_fields=("strength",),
                categorical_fields=("patch",),
            )
        ),
    )

    assert prepared.untouched_final_test_ids == tuple(item.example_id for item in plan.final_test)
    assert all(final_ids.isdisjoint(fold.preprocessor.fitted_row_ids) for fold in prepared.folds)
    assert "future-only" not in prepared.folds[-1].preprocessor.categorical["patch"]
    assert set(prepared.folds[0].preprocessor.fitted_row_ids) == {
        item.example_id for item in plan.folds[0].train
    }

    probabilities = collect_oof_predictions(
        plan,
        tuple(
            FoldProbabilities(
                fold_index=fold.fold_index,
                probabilities=MappingProxyType(
                    {item.example_id: Decimal("0.60") for item in fold.validation}
                ),
            )
            for fold in plan.folds
        ),
    )
    assert tuple(item.example_id for item in probabilities.predictions) == tuple(
        item.example_id for item in plan.oof_validation
    )
    assert set(probabilities.final_test_ids) == final_ids
    plan.assert_tuning_scope(tuple(item.example_id for item in plan.oof_validation))
    with pytest.raises(ValueError, match="tuning"):
        plan.assert_tuning_scope((plan.final_test[0].example_id,))


def test_random_primary_split_and_invalid_oof_coverage_are_rejected() -> None:
    with pytest.raises(ValueError, match="aléatoire"):
        WalkForwardConfig(
            minimum_train_periods=2,
            validation_periods=1,
            final_test_periods=1,
            primary_split="random",
        )
    with pytest.raises(ValueError, match="seuils"):
        WalkForwardConfig(
            minimum_train_periods=2,
            validation_periods=1,
            final_test_periods=1,
            threshold_tuning_scope="final_test",
        )

    plan = WalkForwardSplitter(
        WalkForwardConfig(
            minimum_train_periods=2,
            validation_periods=2,
            final_test_periods=2,
        )
    ).split(_examples())
    incomplete = tuple(
        FoldProbabilities(
            fold_index=fold.fold_index,
            probabilities=MappingProxyType(
                {item.example_id: Decimal("0.5") for item in fold.validation[:-1]}
            ),
        )
        for fold in plan.folds
    )
    with pytest.raises(ValueError, match="exactement"):
        collect_oof_predictions(plan, incomplete)


def _examples() -> tuple[WalkForwardExample, ...]:
    values: list[WalkForwardExample] = []
    offsets = (0, 0, 1, 2, 3, 4, 5, 6, 7)
    for index, offset in enumerate(offsets):
        patch = "14.1" if offset <= 1 else "14.2" if offset <= 5 else "14.3"
        values.append(
            WalkForwardExample(
                example_id=uuid5(_NAMESPACE, f"event-{index}"),
                feature_snapshot_id=uuid5(_NAMESPACE, f"snapshot-{index}"),
                cutoff_at=_START + timedelta(days=offset),
                label=index % 2 == 0,
                competition_id=uuid5(_NAMESPACE, "competition"),
                patch=patch,
                international=offset >= 6,
                feature_values=MappingProxyType({"context.patch": patch}),
                missingness=MappingProxyType({"context.patch": False}),
            )
        )
    return tuple(values)
