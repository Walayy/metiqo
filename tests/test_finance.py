"""Tests des primitives financières exactes."""

from collections.abc import Callable
from decimal import Decimal

import pytest

from metiquo.foundation.finance import DecimalOdds, Money, Probability


def test_values_keep_decimal_precision() -> None:
    bankroll = Money.parse("100.10", "eur")
    increment = Money.parse("0.20", "EUR")

    assert (bankroll + increment).amount == Decimal("100.30")
    assert bankroll.scaled_by("0.10").amount == Decimal("10.010")
    assert bankroll.currency == "EUR"


@pytest.mark.parametrize(
    ("factory", "value"),
    [
        (Probability.parse, 0.5),
        (DecimalOdds.parse, 2.25),
        (lambda amount: Money.parse(amount, "EUR"), 10.5),
    ],
)
def test_financial_values_reject_float(factory: Callable[[object], object], value: float) -> None:
    with pytest.raises(TypeError, match="float"):
        factory(value)


@pytest.mark.parametrize("value", ["-0.01", "1.01", "NaN", "Infinity"])
def test_probability_rejects_out_of_range_or_non_finite_value(value: str) -> None:
    with pytest.raises(ValueError):
        Probability.parse(value)


def test_decimal_odds_and_currency_boundaries() -> None:
    with pytest.raises(ValueError, match="supérieure ou égale à 1"):
        DecimalOdds.parse("0.99")
    with pytest.raises(ValueError, match="trois lettres"):
        Money.parse("10", "EURO")
    with pytest.raises(ValueError, match="même devise"):
        Money.parse("10", "EUR") + Money.parse("1", "USD")
