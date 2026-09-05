"""Probabilités implicites et retrait de marge versionné."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Protocol

from metiquo.contracts.enums import SelectionType
from metiquo.foundation.finance import DecimalOdds, Probability

PROPORTIONAL_NO_VIG_VERSION = "proportional-v1"
NO_VIG_SUM_TOLERANCE = Decimal("1E-24")
_EXCLUSIVE_EXHAUSTIVE_DOMAINS = frozenset(
    (
        frozenset((SelectionType.TEAM_A, SelectionType.TEAM_B)),
        frozenset((SelectionType.TEAM_A, SelectionType.TEAM_B, SelectionType.DRAW)),
        frozenset((SelectionType.OVER, SelectionType.UNDER)),
    )
)


class NoVigCalculationError(ValueError):
    """Le marché ne permet pas un retrait de marge sûr."""


class IncompleteMarketError(NoVigCalculationError):
    """Au moins une issue attendue manque au marché."""


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """Cote décimale validée pour une issue canonique unique."""

    selection: SelectionType
    decimal_odds: DecimalOdds

    def __post_init__(self) -> None:
        if not isinstance(self.selection, SelectionType):
            raise TypeError("selection doit être un SelectionType")
        if not isinstance(self.decimal_odds, DecimalOdds):
            raise TypeError("decimal_odds doit être un DecimalOdds")


@dataclass(frozen=True, slots=True)
class NoVigMarket:
    """Issues observées et domaine exhaustif attendu pour un marché."""

    quotes: tuple[MarketQuote, ...]
    expected_selections: frozenset[SelectionType]

    def __post_init__(self) -> None:
        if len(self.expected_selections) < 2:
            raise NoVigCalculationError("un marché no-vig exige au moins deux issues attendues")
        if self.expected_selections not in _EXCLUSIVE_EXHAUSTIVE_DOMAINS:
            raise NoVigCalculationError(
                "le domaine doit être reconnu comme mutuellement exclusif et exhaustif"
            )
        if not self.quotes:
            raise IncompleteMarketError("le marché ne contient aucune cote")
        observed = tuple(quote.selection for quote in self.quotes)
        if len(set(observed)) != len(observed):
            raise NoVigCalculationError("chaque issue doit avoir exactement une cote")
        unexpected = set(observed).difference(self.expected_selections)
        if unexpected:
            names = ",".join(sorted(selection.value for selection in unexpected))
            raise NoVigCalculationError(f"issues absentes du domaine attendu : {names}")

    @property
    def complete(self) -> bool:
        return {quote.selection for quote in self.quotes} == self.expected_selections


@dataclass(frozen=True, slots=True)
class NoVigQuote:
    """Prix bookmaker brut et normalisé pour une issue."""

    selection: SelectionType
    decimal_odds: DecimalOdds
    raw_implied_probability: Probability
    no_vig_probability: Probability


@dataclass(frozen=True, slots=True)
class NoVigMarketResult:
    """Résultat traçable avec la version exacte de la stratégie."""

    strategy_version: str
    overround: Decimal
    quotes: tuple[NoVigQuote, ...]

    def __post_init__(self) -> None:
        if not self.strategy_version.strip():
            raise NoVigCalculationError("la version de stratégie no-vig est obligatoire")
        if not self.overround.is_finite() or self.overround <= 0:
            raise NoVigCalculationError("l'overround doit être fini et strictement positif")
        if not self.quotes:
            raise NoVigCalculationError("un résultat no-vig ne peut pas être vide")
        probability_sum = _decimal_sum(quote.no_vig_probability.value for quote in self.quotes)
        if abs(probability_sum - Decimal(1)) > NO_VIG_SUM_TOLERANCE:
            raise NoVigCalculationError("les probabilités no-vig doivent sommer à 1")

    @property
    def probability_sum(self) -> Decimal:
        return _decimal_sum(quote.no_vig_probability.value for quote in self.quotes)

    def quote(self, selection: SelectionType) -> NoVigQuote:
        for quote in self.quotes:
            if quote.selection is selection:
                return quote
        raise KeyError(selection)


class NoVigStrategy(Protocol):
    """Extension versionnée ; la compatibilité partielle doit être explicite."""

    @property
    def version(self) -> str: ...

    @property
    def supports_incomplete_markets(self) -> bool: ...

    def normalize(self, raw_probabilities: tuple[Probability, ...]) -> tuple[Probability, ...]:
        """Retirer la marge des probabilités observées."""
        ...


@dataclass(frozen=True, slots=True)
class ProportionalNoVigStrategy:
    """Normalisation proportionnelle MVP pour un domaine complet."""

    @property
    def version(self) -> str:
        return PROPORTIONAL_NO_VIG_VERSION

    @property
    def supports_incomplete_markets(self) -> bool:
        return False

    def normalize(self, raw_probabilities: tuple[Probability, ...]) -> tuple[Probability, ...]:
        if not raw_probabilities:
            raise NoVigCalculationError("aucune probabilité implicite à normaliser")
        with localcontext() as context:
            context.prec = 50
            overround = sum(
                (probability.value for probability in raw_probabilities),
                Decimal(),
            )
            if overround <= 0:
                raise NoVigCalculationError("l'overround doit être strictement positif")
            return tuple(
                Probability(probability.value / overround) for probability in raw_probabilities
            )


class NoVigPricingEngine:
    """Calculer les probabilités bookmaker sans accepter un marché ambigu."""

    def calculate(
        self,
        market: NoVigMarket,
        strategy: NoVigStrategy | None = None,
    ) -> NoVigMarketResult:
        selected_strategy = strategy or ProportionalNoVigStrategy()
        if not selected_strategy.version.strip():
            raise NoVigCalculationError("la version de stratégie no-vig est obligatoire")
        if not market.complete and not selected_strategy.supports_incomplete_markets:
            missing = market.expected_selections.difference(
                quote.selection for quote in market.quotes
            )
            names = ",".join(sorted(selection.value for selection in missing))
            raise IncompleteMarketError(f"issues attendues manquantes : {names}")

        raw_probabilities = tuple(
            implied_probability(quote.decimal_odds) for quote in market.quotes
        )
        normalized = selected_strategy.normalize(raw_probabilities)
        if len(normalized) != len(market.quotes):
            raise NoVigCalculationError("la stratégie doit retourner une probabilité par cote")
        overround = _decimal_sum(probability.value for probability in raw_probabilities)
        return NoVigMarketResult(
            strategy_version=selected_strategy.version,
            overround=overround,
            quotes=tuple(
                NoVigQuote(
                    selection=quote.selection,
                    decimal_odds=quote.decimal_odds,
                    raw_implied_probability=raw_probability,
                    no_vig_probability=no_vig_probability,
                )
                for quote, raw_probability, no_vig_probability in zip(
                    market.quotes,
                    raw_probabilities,
                    normalized,
                    strict=True,
                )
            ),
        )


def implied_probability(decimal_odds: DecimalOdds) -> Probability:
    """Appliquer exactement q=1/O à une cote décimale validée."""

    if not isinstance(decimal_odds, DecimalOdds):
        raise TypeError("decimal_odds doit être un DecimalOdds")
    with localcontext() as context:
        context.prec = 50
        return Probability(Decimal(1) / decimal_odds.value)


def _decimal_sum(values: Iterable[Decimal]) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return sum(values, Decimal())
