"""Tests numériques de la comparaison modèle/bookmaker."""

from __future__ import annotations

from decimal import Decimal

import pytest

from metiquo.contracts.enums import SelectionType
from metiquo.foundation.finance import DecimalOdds, Probability
from metiquo.pricing import (
    VALUE_PRICING_POLICY_VERSION,
    MarketQuote,
    NoVigMarket,
    NoVigPricingEngine,
    NoVigQuote,
    ValuePricingEngine,
    ValuePricingError,
    ValuePricingInput,
)


def test_sfg_odds_four_example_reproduces_every_value_metric() -> None:
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
            book_quote=no_vig.quote(SelectionType.TEAM_A),
            model_probability=Probability.parse("0.30"),
            model_probability_low=Probability.parse("0.27"),
        )
    )

    assert value.policy_version == VALUE_PRICING_POLICY_VERSION
    assert value.fair_odds is not None
    assert abs(value.fair_odds.value - Decimal("3.333333333333333333333333333")) <= Decimal("1E-27")
    assert abs(value.edge - Decimal("0.0619047619047619047619047619")) <= Decimal("1E-28")
    assert value.expected_value == Decimal("0.20")
    assert value.conservative_expected_value == Decimal("0.08")


def test_zero_probability_has_unbounded_fair_odds_and_minus_one_ev() -> None:
    value = ValuePricingEngine().calculate(
        ValuePricingInput(
            book_quote=_book_quote("2.00"),
            model_probability=Probability.parse("0"),
            model_probability_low=Probability.parse("0"),
        )
    )

    assert value.fair_odds is None
    assert value.fair_odds_unbounded is True
    assert value.edge == Decimal("-0.5")
    assert value.expected_value == Decimal("-1")
    assert value.conservative_expected_value == Decimal("-1")


def test_probability_one_has_fair_odds_one_and_full_upside() -> None:
    value = ValuePricingEngine().calculate(
        ValuePricingInput(
            book_quote=_book_quote("4.00"),
            model_probability=Probability.parse("1"),
            model_probability_low=Probability.parse("1"),
        )
    )

    assert value.fair_odds == DecimalOdds.parse("1")
    assert value.fair_odds_unbounded is False
    assert abs(
        value.edge - (Decimal(1) - value.input.book_quote.no_vig_probability.value)
    ) <= Decimal("1E-27")
    assert value.expected_value == Decimal("3")
    assert value.conservative_expected_value == Decimal("3")


def test_probability_interval_must_be_ordered() -> None:
    with pytest.raises(ValuePricingError, match="borne basse"):
        ValuePricingInput(
            book_quote=_book_quote("2.00"),
            model_probability=Probability.parse("0.40"),
            model_probability_low=Probability.parse("0.41"),
        )


def test_formula_properties_hold_across_probability_domain() -> None:
    quote = _book_quote("3.25")
    engine = ValuePricingEngine()
    previous_fair_odds: Decimal | None = None
    for index in range(101):
        probability = Decimal(index) / Decimal(100)
        low = probability * Decimal("0.8")
        value = engine.calculate(
            ValuePricingInput(
                book_quote=quote,
                model_probability=Probability(probability),
                model_probability_low=Probability(low),
            )
        )
        assert abs(value.edge - (probability - quote.no_vig_probability.value)) <= Decimal("1E-27")
        assert value.expected_value == probability * quote.decimal_odds.value - Decimal(1)
        assert value.conservative_expected_value == low * quote.decimal_odds.value - Decimal(1)
        assert value.conservative_expected_value <= value.expected_value
        if probability == 0:
            assert value.fair_odds is None
        else:
            assert value.fair_odds is not None
            assert abs(value.fair_odds.value * probability - Decimal(1)) <= Decimal("1E-48")
            if previous_fair_odds is not None:
                assert value.fair_odds.value < previous_fair_odds
            previous_fair_odds = value.fair_odds.value


def _book_quote(offered_odds: str) -> NoVigQuote:
    opposing_odds = "2.00" if offered_odds == "2.00" else "1.3333333333333333333333333333"
    result = NoVigPricingEngine().calculate(
        NoVigMarket(
            quotes=(
                MarketQuote(SelectionType.TEAM_A, DecimalOdds.parse(offered_odds)),
                MarketQuote(SelectionType.TEAM_B, DecimalOdds.parse(opposing_odds)),
            ),
            expected_selections=frozenset((SelectionType.TEAM_A, SelectionType.TEAM_B)),
        )
    )
    return result.quote(SelectionType.TEAM_A)
