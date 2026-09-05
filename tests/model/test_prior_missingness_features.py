"""Priors hiérarchiques, cold start et prétraitement train-only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest

from metiquo.features import (
    CutoffViolationError,
    FeatureCutoff,
    HierarchicalPriorEstimator,
    PreprocessorParameters,
    PriorObservation,
    TrainingFeatureRow,
    TrainOnlyPreprocessor,
    prior_feature_definitions,
)

_CUTOFF = FeatureCutoff(datetime(2026, 9, 10, 12, 0, tzinfo=UTC))


def test_hierarchical_shrinkage_recency_cold_start_and_ood_are_explicit() -> None:
    observations = (
        _observation(90, "L1", "P1", "0.8", 10),
        _observation(2, "L1", "P1", "0.6", 10),
        _observation(1, "L2", "P2", "0.2", 20),
    )
    future = PriorObservation(
        observation_id=uuid4(),
        event_time=_CUTOFF.at + timedelta(days=1),
        known_at=_CUTOFF.at + timedelta(days=1),
        league="L1",
        patch="P1",
        value=Decimal(1),
        sample_size=10000,
    )
    estimator = HierarchicalPriorEstimator()
    model = estimator.fit(observations, cutoff=_CUTOFF)
    with_future = estimator.fit((*observations, future), cutoff=_CUTOFF)

    assert model.fingerprint == with_future.fingerprint
    assert future.observation_id not in model.observation_ids
    assert model.global_prior is not None
    assert set(model.league_priors) == {"L1", "L2"}
    assert set(model.patch_priors) == {("L1", "P1"), ("L2", "P2")}

    small = estimator.shrink(
        model,
        value=Decimal(1),
        sample_size=1,
        league="L1",
        patch="P1",
        last_observed_at=_CUTOFF.at - timedelta(days=1),
        prediction_cutoff=_CUTOFF,
    )
    assert small.prior_level == "patch"
    assert small.prior is not None
    assert small.value is not None
    assert small.prior < small.value < Decimal(1)
    assert small.confidence < Decimal("0.2")
    assert small.raw_available is True
    assert small.cold_start is False
    assert small.ood is False

    stale = estimator.shrink(
        model,
        value=Decimal("0.7"),
        sample_size=10,
        league="L1",
        patch="P1",
        last_observed_at=_CUTOFF.at - timedelta(days=90),
        prediction_cutoff=_CUTOFF,
    )
    assert stale.effective_sample_size == Decimal("5.000000")

    cold = estimator.shrink(
        model,
        value=None,
        sample_size=0,
        league="L1",
        patch="P1",
        last_observed_at=None,
        prediction_cutoff=_CUTOFF,
    )
    assert cold.raw_value is None
    assert cold.value == model.patch_priors[("L1", "P1")]
    assert cold.raw_available is False
    assert cold.cold_start is True
    assert cold.confidence == 0

    ood = estimator.shrink(
        model,
        value=Decimal("0.5"),
        sample_size=4,
        league="NEW",
        patch="NEW",
        last_observed_at=_CUTOFF.at - timedelta(days=1),
        prediction_cutoff=_CUTOFF,
    )
    assert ood.prior_level == "global"
    assert ood.ood is True
    assert ood.confidence > 0

    empty = estimator.fit((), cutoff=_CUTOFF)
    no_signal = estimator.shrink(
        empty,
        value=None,
        sample_size=0,
        league=None,
        patch=None,
        last_observed_at=None,
        prediction_cutoff=_CUTOFF,
    )
    assert no_signal.value is None
    assert no_signal.prior_level == "none"
    assert no_signal.confidence == 0

    later_model = estimator.fit(
        observations,
        cutoff=FeatureCutoff(_CUTOFF.at + timedelta(days=1)),
    )
    with pytest.raises(CutoffViolationError, match="prior ajusté après"):
        estimator.shrink(
            later_model,
            value=Decimal("0.5"),
            sample_size=1,
            league="L1",
            patch="P1",
            last_observed_at=_CUTOFF.at - timedelta(days=1),
            prediction_cutoff=_CUTOFF,
        )

    definitions = prior_feature_definitions(("form.win_rate",))
    assert (
        next(item for item in definitions if item.name.endswith(".value")).availability
        == "optional"
    )
    assert any(item.name.endswith(".available") for item in definitions)
    assert any(item.name.endswith(".cold_start") for item in definitions)


def test_scaler_and_encoder_fit_before_cutoff_and_preserve_missing_values() -> None:
    train = (
        _row(3, Decimal(1), "A"),
        _row(2, Decimal(3), "B"),
        _row(1, None, None),
    )
    future = TrainingFeatureRow(
        row_id=uuid4(),
        event_time=_CUTOFF.at + timedelta(seconds=1),
        numeric=MappingProxyType({"strength": Decimal(1000)}),
        categorical=MappingProxyType({"league": "FUTURE"}),
    )
    preprocessor = TrainOnlyPreprocessor(
        PreprocessorParameters(
            numeric_fields=("strength",),
            categorical_fields=("league",),
        )
    )
    artifact = preprocessor.fit((*train, future), cutoff=_CUTOFF)
    train_only = preprocessor.fit(train, cutoff=_CUTOFF)

    assert artifact.fingerprint == train_only.fingerprint
    assert future.row_id not in artifact.fitted_row_ids
    assert artifact.numeric["strength"].mean == Decimal("2.000000")
    assert artifact.numeric["strength"].standard_deviation == Decimal("1.000000")
    assert artifact.categorical["league"] == {"A": 1, "B": 2}

    missing_and_ood = preprocessor.transform(
        artifact,
        TrainingFeatureRow(
            row_id=uuid4(),
            event_time=_CUTOFF.at,
            numeric=MappingProxyType({"strength": None}),
            categorical=MappingProxyType({"league": "UNSEEN"}),
        ),
    )
    assert missing_and_ood.values["numeric.strength.scaled"] is None
    assert missing_and_ood.values["numeric.strength.available"] is False
    assert missing_and_ood.values["categorical.league.code"] is None
    assert missing_and_ood.values["categorical.league.available"] is True
    assert missing_and_ood.values["categorical.league.ood"] is True


def _observation(
    days_ago: int,
    league: str,
    patch: str,
    value: str,
    sample_size: int,
) -> PriorObservation:
    return PriorObservation(
        observation_id=uuid4(),
        event_time=_CUTOFF.at - timedelta(days=days_ago),
        known_at=_CUTOFF.at - timedelta(hours=1),
        league=league,
        patch=patch,
        value=Decimal(value),
        sample_size=sample_size,
    )


def _row(days_ago: int, value: Decimal | None, category: str | None) -> TrainingFeatureRow:
    return TrainingFeatureRow(
        row_id=UUID(int=days_ago),
        event_time=_CUTOFF.at - timedelta(days=days_ago),
        numeric=MappingProxyType({"strength": value}),
        categorical=MappingProxyType({"league": category}),
    )
