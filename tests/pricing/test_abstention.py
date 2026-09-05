"""Scénarios d'abstention structurée et absence normale de value."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from metiquo.contracts import Quality
from metiquo.contracts.enums import (
    SFG_ABSTENTION_REASONS,
    AbstentionReason,
    FreshnessStatus,
    ModelStatus,
    SelectionType,
    order_abstention_reasons,
)
from metiquo.foundation.finance import DecimalOdds, Probability
from metiquo.pricing import (
    AdmissionCheck,
    AdmissionCheckCode,
    MarketQuote,
    NoVigMarket,
    NoVigPricingEngine,
    ValueAdmissionDecision,
    ValueDecisionEngine,
    ValuePrice,
    ValuePricingEngine,
    ValuePricingInput,
)


def test_sfg_abstention_vocabulary_is_complete_and_stable() -> None:
    assert SFG_ABSTENTION_REASONS == (
        AbstentionReason.ODDS_STALE,
        AbstentionReason.MARKET_SUSPENDED,
        AbstentionReason.EVENT_MAPPING_AMBIGUOUS,
        AbstentionReason.INSUFFICIENT_HISTORY,
        AbstentionReason.ROSTER_UNCERTAIN,
        AbstentionReason.SOURCE_STALE,
        AbstentionReason.MODEL_STALE,
        AbstentionReason.OUT_OF_DISTRIBUTION,
        AbstentionReason.CALIBRATION_FAILED,
        AbstentionReason.EDGE_TOO_SMALL,
        AbstentionReason.CONSERVATIVE_EV_NEGATIVE,
        AbstentionReason.MARKET_RULES_UNKNOWN,
        AbstentionReason.PATCH_CONTEXT_UNKNOWN,
        AbstentionReason.EVENT_ALREADY_STARTED,
        AbstentionReason.CAPABILITY_DISABLED,
    )


def test_absence_of_computed_value_is_a_normal_structured_abstention() -> None:
    decision = ValueDecisionEngine().abstain_without_value(
        "policy-v1",
        reasons=(AbstentionReason.ROSTER_UNCERTAIN,),
        model_reason_codes=(
            "LOW_DATA_COVERAGE",
            "OUT_OF_DISTRIBUTION",
            "ABSTENTION_REQUIRED",
        ),
    )

    assert decision.is_opportunity is False
    assert decision.evaluated_value is None
    assert decision.reasons == (
        AbstentionReason.INSUFFICIENT_HISTORY,
        AbstentionReason.ROSTER_UNCERTAIN,
        AbstentionReason.OUT_OF_DISTRIBUTION,
    )
    assert decision.abstention is not None
    assert decision.abstention.primary_reason is AbstentionReason.INSUFFICIENT_HISTORY


def test_admission_and_model_reasons_are_deduplicated_in_public_order() -> None:
    admission = _admission(
        AbstentionReason.CAPABILITY_DISABLED,
        AbstentionReason.SOURCE_STALE,
        AbstentionReason.EDGE_TOO_SMALL,
    )

    decision = ValueDecisionEngine().from_admission(
        admission,
        _value(),
        upstream_reasons=(AbstentionReason.OUT_OF_DISTRIBUTION,),
        model_reason_codes=("OUT_OF_DISTRIBUTION", "ABSTENTION_REQUIRED"),
    )

    assert decision.is_opportunity is False
    assert decision.evaluated_value is not None
    assert decision.reasons == (
        AbstentionReason.SOURCE_STALE,
        AbstentionReason.OUT_OF_DISTRIBUTION,
        AbstentionReason.EDGE_TOO_SMALL,
        AbstentionReason.CAPABILITY_DISABLED,
    )


def test_successful_admission_keeps_the_evaluated_value() -> None:
    value = _value()

    decision = ValueDecisionEngine().from_admission(_admission(), value)

    assert decision.is_opportunity is True
    assert decision.evaluated_value is value
    assert decision.abstention is None
    assert decision.reasons == ()


def test_unknown_blocking_model_reason_cannot_escape_the_structured_vocabulary() -> None:
    with pytest.raises(ValueError, match="raison modèle non structurée"):
        ValueDecisionEngine().abstain_without_value(
            "policy-v1",
            model_reason_codes=("UNVERSIONED_MODEL_REASON",),
        )


def test_non_publishable_quality_requires_unique_publicly_ordered_reasons() -> None:
    quality = _quality(
        (
            AbstentionReason.ODDS_STALE,
            AbstentionReason.SOURCE_STALE,
        )
    )

    assert quality.abstention_reasons == (
        AbstentionReason.ODDS_STALE,
        AbstentionReason.SOURCE_STALE,
    )
    with pytest.raises(ValidationError, match="inversement"):
        _quality(())
    with pytest.raises(ValidationError, match="uniques et dans l'ordre"):
        _quality(
            (
                AbstentionReason.SOURCE_STALE,
                AbstentionReason.ODDS_STALE,
            )
        )
    with pytest.raises(ValidationError, match="uniques et dans l'ordre"):
        _quality(
            (
                AbstentionReason.ODDS_STALE,
                AbstentionReason.ODDS_STALE,
            )
        )


def _admission(*reasons: AbstentionReason) -> ValueAdmissionDecision:
    reason_by_check = {
        AdmissionCheckCode.CAPABILITY_ENABLED: AbstentionReason.CAPABILITY_DISABLED,
        AdmissionCheckCode.SOURCE_QUALITY: AbstentionReason.SOURCE_STALE,
        AdmissionCheckCode.MIN_EDGE: AbstentionReason.EDGE_TOO_SMALL,
    }
    reason_set = set(reasons)
    checks = tuple(
        AdmissionCheck(
            code=code,
            passed=reason_by_check.get(code) not in reason_set,
            failure_reason=(
                reason_by_check.get(code) if reason_by_check.get(code) in reason_set else None
            ),
        )
        for code in AdmissionCheckCode
    )
    return ValueAdmissionDecision(
        admitted=not reasons,
        policy_version="policy-v1",
        checks=checks,
        reasons=order_abstention_reasons(reasons),
    )


def _quality(reasons: tuple[AbstentionReason, ...]) -> Quality:
    return Quality(
        mapping_confidence=Decimal("0.99"),
        source_freshness=FreshnessStatus.STALE,
        data_coverage=Decimal("0.70"),
        model_status=ModelStatus.CHAMPION,
        abstention_reasons=reasons,
        publishable=False,
    )


def _value() -> ValuePrice:
    no_vig = NoVigPricingEngine().calculate(
        NoVigMarket(
            quotes=(
                MarketQuote(SelectionType.TEAM_A, DecimalOdds.parse("4.00")),
                MarketQuote(SelectionType.TEAM_B, DecimalOdds.parse("1.25")),
            ),
            expected_selections=frozenset((SelectionType.TEAM_A, SelectionType.TEAM_B)),
        )
    )
    return ValuePricingEngine().calculate(
        ValuePricingInput(
            no_vig.quote(SelectionType.TEAM_A),
            Probability(Decimal("0.30")),
            Probability(Decimal("0.27")),
        )
    )
