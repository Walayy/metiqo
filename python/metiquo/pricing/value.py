"""Cote juste, edge et espérances de value exactes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from metiquo.foundation.finance import DecimalOdds, Probability
from metiquo.pricing.no_vig import NoVigQuote

VALUE_PRICING_POLICY_VERSION = "value-pricing-v1"


class ValuePricingError(ValueError):
    """Les probabilités ou la cote ne permettent pas un calcul cohérent."""


@dataclass(frozen=True, slots=True)
class ValuePricingInput:
    """Prix bookmaker no-vig et intervalle modèle pour une même issue."""

    book_quote: NoVigQuote
    model_probability: Probability
    model_probability_low: Probability

    def __post_init__(self) -> None:
        if not isinstance(self.book_quote, NoVigQuote):
            raise TypeError("book_quote doit être un NoVigQuote")
        if not isinstance(self.model_probability, Probability):
            raise TypeError("model_probability doit être une Probability")
        if not isinstance(self.model_probability_low, Probability):
            raise TypeError("model_probability_low doit être une Probability")
        if self.model_probability_low > self.model_probability:
            raise ValuePricingError("la borne basse ne peut pas dépasser la probabilité centrale")


@dataclass(frozen=True, slots=True)
class ValuePrice:
    """Comparaison numérique sans décision de grade ni de publication."""

    policy_version: str
    input: ValuePricingInput
    fair_odds: DecimalOdds | None
    edge: Decimal
    expected_value: Decimal
    conservative_expected_value: Decimal

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValuePricingError("la version de politique pricing est obligatoire")
        values = (self.edge, self.expected_value, self.conservative_expected_value)
        if any(not value.is_finite() for value in values):
            raise ValuePricingError("les métriques de value doivent être finies")
        if not Decimal(-1) <= self.edge <= Decimal(1):
            raise ValuePricingError("edge doit appartenir à [-1,1]")
        if self.expected_value < Decimal(-1) or self.conservative_expected_value < Decimal(-1):
            raise ValuePricingError("une espérance ne peut pas être inférieure à -1")
        if (self.input.model_probability.value == 0) != (self.fair_odds is None):
            raise ValuePricingError("la cote juste est indéfinie uniquement pour p=0")

    @property
    def fair_odds_unbounded(self) -> bool:
        return self.fair_odds is None


class ValuePricingEngine:
    """Appliquer les formules SFG avec une politique de limites explicite."""

    def calculate(self, request: ValuePricingInput) -> ValuePrice:
        model = request.model_probability.value
        model_low = request.model_probability_low.value
        book_no_vig = request.book_quote.no_vig_probability.value
        offered_odds = request.book_quote.decimal_odds.value
        with localcontext() as context:
            context.prec = 50
            fair_odds = None if model == 0 else DecimalOdds(Decimal(1) / model)
            edge = model - book_no_vig
            expected_value = model * offered_odds - Decimal(1)
            conservative_expected_value = model_low * offered_odds - Decimal(1)
        return ValuePrice(
            policy_version=VALUE_PRICING_POLICY_VERSION,
            input=request,
            fair_odds=fair_odds,
            edge=edge,
            expected_value=expected_value,
            conservative_expected_value=conservative_expected_value,
        )
