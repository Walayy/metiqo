"""Preuves numériques du retrait de marge bookmaker."""

from __future__ import annotations

from decimal import Decimal

import pytest

from metiquo.contracts.enums import SelectionType
from metiquo.foundation.finance import DecimalOdds, Probability
from metiquo.pricing import (
    NO_VIG_SUM_TOLERANCE,
    PROPORTIONAL_NO_VIG_VERSION,
    IncompleteMarketError,
    MarketQuote,
    NoVigCalculationError,
    NoVigMarket,
    NoVigPricingEngine,
    implied_probability,
)


def test_hand_calculated_two_way_market_removes_overround() -> None:
    result = NoVigPricingEngine().calculate(
        _market(
            (SelectionType.TEAM_A, "4.00"),
            (SelectionType.TEAM_B, "1.25"),
        )
    )

    team_a = result.quote(SelectionType.TEAM_A)
    team_b = result.quote(SelectionType.TEAM_B)
    assert team_a.raw_implied_probability.value == Decimal("0.25")
    assert team_b.raw_implied_probability.value == Decimal("0.8")
    assert result.overround == Decimal("1.05")
    assert abs(
        team_a.no_vig_probability.value - Decimal("0.2380952380952380952380952381")
    ) <= Decimal("1E-28")
    assert abs(
        team_b.no_vig_probability.value - Decimal("0.7619047619047619047619047619")
    ) <= Decimal("1E-28")
    assert result.probability_sum == Decimal(1)
    assert result.strategy_version == PROPORTIONAL_NO_VIG_VERSION


def test_three_way_draw_market_is_normalized_over_every_expected_outcome() -> None:
    result = NoVigPricingEngine().calculate(
        _market(
            (SelectionType.TEAM_A, "2.40"),
            (SelectionType.DRAW, "3.20"),
            (SelectionType.TEAM_B, "3.00"),
        )
    )

    assert set(quote.selection for quote in result.quotes) == {
        SelectionType.TEAM_A,
        SelectionType.DRAW,
        SelectionType.TEAM_B,
    }
    assert abs(result.probability_sum - Decimal(1)) <= NO_VIG_SUM_TOLERANCE


def test_incomplete_market_is_closed_by_the_mvp_strategy() -> None:
    market = NoVigMarket(
        quotes=(MarketQuote(SelectionType.TEAM_A, DecimalOdds.parse("1.80")),),
        expected_selections=frozenset((SelectionType.TEAM_A, SelectionType.TEAM_B)),
    )

    with pytest.raises(IncompleteMarketError, match="TEAM_B"):
        NoVigPricingEngine().calculate(market)


@pytest.mark.parametrize("value", ("0", "0.99", "NaN", "Infinity", "-Infinity"))
def test_invalid_decimal_odds_are_rejected_before_pricing(value: str) -> None:
    with pytest.raises(ValueError):
        implied_probability(DecimalOdds.parse(value))


def test_no_vig_property_holds_for_representative_two_and_three_way_prices() -> None:
    engine = NoVigPricingEngine()
    prices = tuple(Decimal(index) / Decimal(100) for index in range(101, 1001, 37))
    for first in prices:
        for second in prices:
            result = engine.calculate(
                _market(
                    (SelectionType.TEAM_A, first),
                    (SelectionType.TEAM_B, second),
                )
            )
            assert abs(result.probability_sum - Decimal(1)) <= NO_VIG_SUM_TOLERANCE
            assert all(
                Decimal() <= quote.no_vig_probability.value <= Decimal(1) for quote in result.quotes
            )
            assert all(
                abs(quote.raw_implied_probability.value - Decimal(1) / quote.decimal_odds.value)
                <= Decimal("1E-27")
                for quote in result.quotes
            )

    for first, second, third in zip(prices[::3], prices[1::3], prices[2::3], strict=False):
        result = engine.calculate(
            _market(
                (SelectionType.TEAM_A, first),
                (SelectionType.DRAW, second),
                (SelectionType.TEAM_B, third),
            )
        )
        assert abs(result.probability_sum - Decimal(1)) <= NO_VIG_SUM_TOLERANCE


def test_duplicate_and_unexpected_selections_are_rejected() -> None:
    quote = MarketQuote(SelectionType.TEAM_A, DecimalOdds.parse("2.00"))
    with pytest.raises(NoVigCalculationError, match="exactement une cote"):
        NoVigMarket(
            quotes=(quote, quote),
            expected_selections=frozenset((SelectionType.TEAM_A, SelectionType.TEAM_B)),
        )
    with pytest.raises(NoVigCalculationError, match="domaine attendu"):
        NoVigMarket(
            quotes=(quote, MarketQuote(SelectionType.DRAW, DecimalOdds.parse("3.00"))),
            expected_selections=frozenset((SelectionType.TEAM_A, SelectionType.TEAM_B)),
        )
    with pytest.raises(NoVigCalculationError, match="mutuellement exclusif"):
        NoVigMarket(
            quotes=(quote, MarketQuote(SelectionType.OVER, DecimalOdds.parse("2.00"))),
            expected_selections=frozenset((SelectionType.TEAM_A, SelectionType.OVER)),
        )


def test_strategy_output_is_validated_at_the_boundary() -> None:
    class InvalidStrategy:
        version = "invalid-test-v1"
        supports_incomplete_markets = True

        def normalize(
            self,
            raw_probabilities: tuple[Probability, ...],
        ) -> tuple[Probability, ...]:
            return (Probability(Decimal("0.25")),) * len(raw_probabilities)

    with pytest.raises(NoVigCalculationError, match="sommer à 1"):
        NoVigPricingEngine().calculate(
            _market(
                (SelectionType.TEAM_A, "2.00"),
                (SelectionType.TEAM_B, "2.00"),
            ),
            InvalidStrategy(),
        )


def test_incomplete_market_requires_an_explicitly_compatible_strategy() -> None:
    class ExplicitPartialStrategy:
        version = "partial-observed-normalization-test-v1"
        supports_incomplete_markets = True

        def normalize(
            self,
            raw_probabilities: tuple[Probability, ...],
        ) -> tuple[Probability, ...]:
            assert len(raw_probabilities) == 1
            return (Probability(Decimal(1)),)

    market = NoVigMarket(
        quotes=(MarketQuote(SelectionType.TEAM_A, DecimalOdds.parse("1.80")),),
        expected_selections=frozenset((SelectionType.TEAM_A, SelectionType.TEAM_B)),
    )

    result = NoVigPricingEngine().calculate(market, ExplicitPartialStrategy())

    assert result.strategy_version == "partial-observed-normalization-test-v1"
    assert result.probability_sum == Decimal(1)


def _market(
    *values: tuple[SelectionType, str | Decimal],
) -> NoVigMarket:
    quotes = tuple(
        MarketQuote(selection, DecimalOdds.parse(decimal_odds))
        for selection, decimal_odds in values
    )
    return NoVigMarket(
        quotes=quotes,
        expected_selections=frozenset(selection for selection, _decimal_odds in values),
    )
