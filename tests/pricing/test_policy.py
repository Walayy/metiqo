"""Résolution déterministe et validation des politiques de value."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from metiquo.contracts.enums import MarketType
from metiquo.pricing import (
    ValuePolicy,
    ValuePolicyError,
    ValueThresholdOverride,
    ValueThresholds,
)

_COMPETITION_ID = UUID("11111111-1111-4111-8111-111111111111")
_TUNED_THROUGH = datetime(2026, 7, 31, 23, 59, tzinfo=UTC)
_FINAL_TEST_START = datetime(2026, 8, 1, tzinfo=UTC)


def test_overrides_apply_in_market_competition_bucket_order() -> None:
    policy = ValuePolicy(
        version="value-thresholds-v1",
        thresholds=_thresholds(),
        tuned_through=_TUNED_THROUGH,
        final_test_starts_at=_FINAL_TEST_START,
        market_overrides={
            MarketType.MATCH_WINNER: ValueThresholdOverride(
                min_edge=Decimal("0.04"),
                min_ev=Decimal("0.06"),
            )
        },
        competition_overrides={
            _COMPETITION_ID: ValueThresholdOverride(
                min_edge=Decimal("0.05"),
                min_mapping_confidence=Decimal("0.90"),
            )
        },
        bucket_overrides={
            "longshot": ValueThresholdOverride(
                min_edge=Decimal("0.08"),
                max_odds_age_seconds=45,
            )
        },
    )

    resolved = policy.resolve(
        MarketType.MATCH_WINNER,
        competition_id=_COMPETITION_ID,
        bucket=" longshot ",
    )

    assert resolved.policy_version == "value-thresholds-v1"
    assert resolved.thresholds == ValueThresholds(
        min_edge=Decimal("0.08"),
        min_ev=Decimal("0.06"),
        min_conservative_ev=Decimal("0.00"),
        max_odds_age_seconds=45,
        min_mapping_confidence=Decimal("0.90"),
    )
    assert resolved.applied_scopes == (
        "market:MATCH_WINNER",
        f"competition:{_COMPETITION_ID}",
        "bucket:longshot",
    )


def test_unmatched_context_keeps_global_thresholds_and_version() -> None:
    policy = ValuePolicy(
        version="global-v1",
        thresholds=_thresholds(),
        tuned_through=_TUNED_THROUGH,
        final_test_starts_at=_FINAL_TEST_START,
    )

    resolved = policy.resolve(MarketType.MATCH_WINNER)

    assert resolved.thresholds == _thresholds()
    assert resolved.applied_scopes == ()


def test_tuning_cannot_touch_final_test_period() -> None:
    with pytest.raises(ValuePolicyError, match="précéder strictement"):
        ValuePolicy(
            version="leaking-policy-v1",
            thresholds=_thresholds(),
            tuned_through=_FINAL_TEST_START,
            final_test_starts_at=_FINAL_TEST_START,
        )


def test_threshold_values_and_empty_overrides_are_closed() -> None:
    with pytest.raises(ValuePolicyError, match=r"\[0,1\]"):
        ValueThresholds(
            min_edge=Decimal("1.01"),
            min_ev=Decimal("0.05"),
            min_conservative_ev=Decimal("0"),
            max_odds_age_seconds=90,
            min_mapping_confidence=Decimal("0.8"),
        )
    with pytest.raises(ValuePolicyError, match="au moins un seuil"):
        ValueThresholdOverride()


def _thresholds() -> ValueThresholds:
    return ValueThresholds(
        min_edge=Decimal("0.03"),
        min_ev=Decimal("0.05"),
        min_conservative_ev=Decimal("0.00"),
        max_odds_age_seconds=90,
        min_mapping_confidence=Decimal("0.80"),
    )
