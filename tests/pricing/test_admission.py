"""Matrice des garde-fous ordonnés avant opportunité."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from metiquo.contracts.enums import (
    AbstentionReason,
    FreshnessStatus,
    MarketStatus,
    ModelStatus,
    SelectionType,
)
from metiquo.foundation.finance import DecimalOdds, Probability
from metiquo.pricing import (
    AdmissionCheckCode,
    MarketQuote,
    NoVigMarket,
    NoVigPricingEngine,
    ResolvedValuePolicy,
    ValueAdmissionGate,
    ValueAdmissionInput,
    ValuePricingEngine,
    ValuePricingInput,
    ValueThresholds,
)

_NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)
_START = _NOW + timedelta(hours=4)


def test_all_guards_pass_in_the_normative_order() -> None:
    decision = ValueAdmissionGate().evaluate(_valid_request())

    assert decision.admitted is True
    assert decision.reasons == ()
    assert tuple(check.code for check in decision.checks) == tuple(AdmissionCheckCode)
    assert all(check.passed for check in decision.checks)
    assert decision.policy_version == "admission-test-v1"


@pytest.mark.parametrize(
    ("check", "reason"),
    (
        (AdmissionCheckCode.CAPABILITY_ENABLED, AbstentionReason.CAPABILITY_DISABLED),
        (AdmissionCheckCode.SOURCE_QUALITY, AbstentionReason.SOURCE_STALE),
        (AdmissionCheckCode.CHAMPION_MODEL, AbstentionReason.MODEL_STALE),
        (AdmissionCheckCode.EVENT_MAPPING, AbstentionReason.EVENT_MAPPING_AMBIGUOUS),
        (AdmissionCheckCode.MARKET_RULES, AbstentionReason.MARKET_RULES_UNKNOWN),
        (AdmissionCheckCode.MARKET_OPEN, AbstentionReason.MARKET_SUSPENDED),
        (AdmissionCheckCode.EVENT_NOT_STARTED, AbstentionReason.EVENT_ALREADY_STARTED),
        (
            AdmissionCheckCode.PREDICTION_CUTOFF,
            AbstentionReason.EVENT_ALREADY_STARTED,
        ),
        (AdmissionCheckCode.ODDS_AGE, AbstentionReason.ODDS_STALE),
        (
            AdmissionCheckCode.MAPPING_CONFIDENCE,
            AbstentionReason.EVENT_MAPPING_AMBIGUOUS,
        ),
    ),
)
def test_each_structural_guard_blocks_opportunity(
    check: AdmissionCheckCode,
    reason: AbstentionReason,
) -> None:
    request = _request_failing(check)

    decision = ValueAdmissionGate().evaluate(request)

    assert decision.admitted is False
    assert decision.reasons == (reason,)


@pytest.mark.parametrize(
    ("thresholds", "reason"),
    (
        (
            ValueThresholds(Decimal("0.07"), Decimal("0.05"), Decimal("0"), 90, Decimal("0.8")),
            AbstentionReason.EDGE_TOO_SMALL,
        ),
        (
            ValueThresholds(Decimal("0.03"), Decimal("0.21"), Decimal("0"), 90, Decimal("0.8")),
            AbstentionReason.EXPECTED_VALUE_TOO_SMALL,
        ),
        (
            ValueThresholds(Decimal("0.03"), Decimal("0.05"), Decimal("0.09"), 90, Decimal("0.8")),
            AbstentionReason.CONSERVATIVE_EV_TOO_SMALL,
        ),
    ),
)
def test_each_value_threshold_blocks_independently(
    thresholds: ValueThresholds,
    reason: AbstentionReason,
) -> None:
    request = _valid_request()
    request = replace(
        request,
        policy=ResolvedValuePolicy(request.policy.policy_version, thresholds, ()),
    )

    decision = ValueAdmissionGate().evaluate(request)

    assert decision.admitted is False
    assert decision.reasons == (reason,)


def test_negative_conservative_ev_has_the_specific_sfg_reason() -> None:
    request = _valid_request(model_probability="0.30", model_probability_low="0.20")

    decision = ValueAdmissionGate().evaluate(request)

    assert decision.admitted is False
    assert decision.reasons == (AbstentionReason.CONSERVATIVE_EV_NEGATIVE,)


def test_multiple_failures_are_complete_deduplicated_and_ordered() -> None:
    request = replace(
        _valid_request(model_probability="0.20", model_probability_low="0.10"),
        capability_enabled=False,
        source_freshness=FreshnessStatus.QUARANTINED,
        model_status=ModelStatus.BLOCKED,
        event_mapping_resolved=False,
        market_rules_known=False,
        market_status=MarketStatus.SETTLED,
        evaluated_at=_START,
        prediction_cutoff=_START,
        odds_age_seconds=999,
        mapping_confidence=Probability(Decimal("0.1")),
    )

    decision = ValueAdmissionGate().evaluate(request)

    assert decision.admitted is False
    assert decision.reasons == (
        AbstentionReason.CAPABILITY_DISABLED,
        AbstentionReason.SOURCE_STALE,
        AbstentionReason.MODEL_STALE,
        AbstentionReason.EVENT_MAPPING_AMBIGUOUS,
        AbstentionReason.MARKET_RULES_UNKNOWN,
        AbstentionReason.MARKET_SUSPENDED,
        AbstentionReason.EVENT_ALREADY_STARTED,
        AbstentionReason.ODDS_STALE,
        AbstentionReason.EDGE_TOO_SMALL,
        AbstentionReason.EXPECTED_VALUE_TOO_SMALL,
        AbstentionReason.CONSERVATIVE_EV_NEGATIVE,
    )


def _request_failing(check: AdmissionCheckCode) -> ValueAdmissionInput:
    request = _valid_request()
    match check:
        case AdmissionCheckCode.CAPABILITY_ENABLED:
            return replace(request, capability_enabled=False)
        case AdmissionCheckCode.SOURCE_QUALITY:
            return replace(request, source_freshness=FreshnessStatus.STALE)
        case AdmissionCheckCode.CHAMPION_MODEL:
            return replace(request, model_status=ModelStatus.CANDIDATE)
        case AdmissionCheckCode.EVENT_MAPPING:
            return replace(request, event_mapping_resolved=False)
        case AdmissionCheckCode.MARKET_RULES:
            return replace(request, market_rules_known=False)
        case AdmissionCheckCode.MARKET_OPEN:
            return replace(request, market_status=MarketStatus.SUSPENDED)
        case AdmissionCheckCode.EVENT_NOT_STARTED:
            return replace(request, evaluated_at=_START)
        case AdmissionCheckCode.PREDICTION_CUTOFF:
            return replace(
                request,
                prediction_cutoff=_START,
                evaluated_at=_START + timedelta(seconds=1),
            )
        case AdmissionCheckCode.ODDS_AGE:
            return replace(request, odds_age_seconds=91)
        case AdmissionCheckCode.MAPPING_CONFIDENCE:
            return replace(request, mapping_confidence=Probability(Decimal("0.79")))
        case _:
            raise AssertionError(f"contrôle structurel non pris en charge : {check}")


def _valid_request(
    *,
    model_probability: str = "0.30",
    model_probability_low: str = "0.27",
) -> ValueAdmissionInput:
    no_vig = NoVigPricingEngine().calculate(
        NoVigMarket(
            quotes=(
                MarketQuote(SelectionType.TEAM_A, DecimalOdds.parse("4.00")),
                MarketQuote(SelectionType.TEAM_B, DecimalOdds.parse("1.25")),
            ),
            expected_selections=frozenset((SelectionType.TEAM_A, SelectionType.TEAM_B)),
        )
    )
    value = ValuePricingEngine().calculate(
        ValuePricingInput(
            no_vig.quote(SelectionType.TEAM_A),
            Probability.parse(model_probability),
            Probability.parse(model_probability_low),
        )
    )
    return ValueAdmissionInput(
        value_price=value,
        policy=ResolvedValuePolicy(
            "admission-test-v1",
            ValueThresholds(
                min_edge=Decimal("0.03"),
                min_ev=Decimal("0.05"),
                min_conservative_ev=Decimal("0"),
                max_odds_age_seconds=90,
                min_mapping_confidence=Decimal("0.80"),
            ),
            (),
        ),
        mapping_confidence=Probability(Decimal("0.99")),
        odds_age_seconds=20,
        model_status=ModelStatus.CHAMPION,
        source_freshness=FreshnessStatus.FRESH,
        market_status=MarketStatus.OPEN,
        prediction_cutoff=_NOW - timedelta(minutes=1),
        event_starts_at=_START,
        evaluated_at=_NOW,
        capability_enabled=True,
        event_mapping_resolved=True,
        market_rules_known=True,
    )
