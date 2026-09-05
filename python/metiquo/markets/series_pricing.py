"""Distribution de série dérivée de probabilités GAME_WINNER indépendantes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from itertools import product
from types import MappingProxyType
from typing import TYPE_CHECKING

from metiquo.contracts.enums import SelectionType

if TYPE_CHECKING:
    from metiquo.models.predictions import StoredPrematchPrediction

_QUANTUM = Decimal("0.00000001")
_SUPPORTED_ODD_FORMATS = frozenset({1, 3, 5})


class SideAssignment(StrEnum):
    BLUE = "blue"
    RED = "red"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProbabilityInterval:
    p50: Decimal
    p_low: Decimal
    p_high: Decimal

    def __post_init__(self) -> None:
        if not all(value.is_finite() for value in (self.p50, self.p_low, self.p_high)):
            raise ValueError("les probabilités doivent être finies")
        if not Decimal() <= self.p_low <= self.p50 <= self.p_high <= Decimal(1):
            raise ValueError("l'intervalle doit respecter p_low <= p50 <= p_high")

    @classmethod
    def from_prediction(cls, prediction: StoredPrematchPrediction) -> ProbabilityInterval:
        return cls(
            p50=prediction.team_a_probability,
            p_low=prediction.team_a_low,
            p_high=prediction.team_a_high,
        )


@dataclass(frozen=True, slots=True)
class SideAdjustedProbabilities:
    team_a_blue: ProbabilityInterval
    team_a_red: ProbabilityInterval


@dataclass(frozen=True, slots=True)
class SeriesOutcome:
    selection: SelectionType
    probability: Decimal
    p_low: Decimal
    p_high: Decimal

    def __post_init__(self) -> None:
        if not Decimal() <= self.p_low <= self.probability <= self.p_high <= Decimal(1):
            raise ValueError("l'issue de série doit rester ordonnée dans [0,1]")


@dataclass(frozen=True, slots=True)
class SeriesTerminalScore:
    team_a_wins: int
    team_b_wins: int
    probability: Decimal


@dataclass(frozen=True, slots=True)
class SeriesDistribution:
    best_of: int | None
    allows_draw: bool | None
    enabled: bool
    reason_codes: tuple[str, ...]
    outcomes: tuple[SeriesOutcome, ...]
    internal_terminal_scores: tuple[SeriesTerminalScore, ...]
    internal_game_counts: Mapping[int, Decimal]
    secondary_markets_enabled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "internal_game_counts",
            MappingProxyType(dict(self.internal_game_counts)),
        )
        if self.enabled:
            if self.reason_codes or not self.outcomes:
                raise ValueError("une distribution active doit exposer ses issues sans blocage")
            if sum((item.probability for item in self.outcomes), Decimal()) != Decimal(1):
                raise ValueError("les issues de série doivent sommer exactement à 1")
            if sum(self.internal_game_counts.values(), Decimal()) != Decimal(1):
                raise ValueError("les nombres de games internes doivent sommer à 1")
        elif self.outcomes or not self.reason_codes:
            raise ValueError("une distribution désactivée ne doit publier aucune issue")
        if self.secondary_markets_enabled:
            raise ValueError("les marchés score exact et nombre de games ne sont pas activés")

    def outcome(self, selection: SelectionType) -> SeriesOutcome:
        return next(item for item in self.outcomes if item.selection is selection)


class SeriesPricingEngine:
    """Calculer les issues de série et garder les marchés secondaires internes."""

    def price(
        self,
        game_probability: ProbabilityInterval,
        *,
        best_of: int | None,
        allows_draw: bool | None,
        side_assignment: SideAssignment = SideAssignment.UNKNOWN,
        side_probabilities: SideAdjustedProbabilities | None = None,
    ) -> SeriesDistribution:
        disabled_reason = _format_reason(best_of, allows_draw)
        if disabled_reason is not None:
            return SeriesDistribution(
                best_of=best_of,
                allows_draw=allows_draw,
                enabled=False,
                reason_codes=(disabled_reason,),
                outcomes=(),
                internal_terminal_scores=(),
                internal_game_counts=MappingProxyType({}),
            )
        assert best_of is not None
        scenarios = _probability_scenarios(
            game_probability,
            best_of=best_of,
            side_assignment=side_assignment,
            side_probabilities=side_probabilities,
        )
        central_distributions = tuple(
            _terminal_distribution(tuple(item.p50 for item in scenario), best_of=best_of)
            for scenario in scenarios
        )
        central = _average_terminal_distributions(central_distributions)
        selections = (
            (SelectionType.TEAM_A, SelectionType.TEAM_B, SelectionType.DRAW)
            if best_of == 2
            else (SelectionType.TEAM_A, SelectionType.TEAM_B)
        )
        central_outcomes = _outcome_probabilities(central)
        bounds = tuple(_outcome_bounds(scenario, best_of=best_of) for scenario in scenarios)
        probabilities = _quantized_distribution(
            tuple(central_outcomes[selection] for selection in selections)
        )
        outcomes = tuple(
            SeriesOutcome(
                selection=selection,
                probability=probabilities[index],
                p_low=_round_bound(
                    sum((item[selection][0] for item in bounds), Decimal()) / Decimal(len(bounds)),
                    lower=True,
                ),
                p_high=_round_bound(
                    sum((item[selection][1] for item in bounds), Decimal()) / Decimal(len(bounds)),
                    lower=False,
                ),
            )
            for index, selection in enumerate(selections)
        )
        scores = _terminal_scores(central)
        counts = _game_counts(scores)
        return SeriesDistribution(
            best_of=best_of,
            allows_draw=allows_draw,
            enabled=True,
            reason_codes=(),
            outcomes=outcomes,
            internal_terminal_scores=scores,
            internal_game_counts=counts,
        )


def _format_reason(best_of: int | None, allows_draw: bool | None) -> str | None:
    if best_of is None or allows_draw is None:
        return "SERIES_FORMAT_UNKNOWN"
    if best_of in _SUPPORTED_ODD_FORMATS:
        return "SERIES_RULES_INCONSISTENT" if allows_draw else None
    if best_of == 2:
        return None if allows_draw else "SERIES_RULES_INCONSISTENT"
    return "SERIES_FORMAT_UNSUPPORTED"


def _probability_scenarios(
    base: ProbabilityInterval,
    *,
    best_of: int,
    side_assignment: SideAssignment,
    side_probabilities: SideAdjustedProbabilities | None,
) -> tuple[tuple[ProbabilityInterval, ...], ...]:
    if side_probabilities is None:
        return ((base,) * best_of,)

    def alternating(
        first: ProbabilityInterval, second: ProbabilityInterval
    ) -> tuple[ProbabilityInterval, ...]:
        return tuple(first if index % 2 == 0 else second for index in range(best_of))

    blue_first = alternating(
        side_probabilities.team_a_blue,
        side_probabilities.team_a_red,
    )
    red_first = alternating(
        side_probabilities.team_a_red,
        side_probabilities.team_a_blue,
    )
    if side_assignment is SideAssignment.BLUE:
        return (blue_first,)
    if side_assignment is SideAssignment.RED:
        return (red_first,)
    return (blue_first, red_first)


def _terminal_distribution(
    probabilities: Sequence[Decimal],
    *,
    best_of: int,
) -> Mapping[tuple[int, int], Decimal]:
    target = best_of // 2 + 1 if best_of % 2 else best_of
    terminal: dict[tuple[int, int], Decimal] = {}

    def visit(game_index: int, wins_a: int, wins_b: int, mass: Decimal) -> None:
        finished = game_index == best_of or (
            best_of % 2 == 1 and (wins_a == target or wins_b == target)
        )
        if finished:
            terminal[(wins_a, wins_b)] = terminal.get((wins_a, wins_b), Decimal()) + mass
            return
        probability = probabilities[game_index]
        visit(game_index + 1, wins_a + 1, wins_b, mass * probability)
        visit(game_index + 1, wins_a, wins_b + 1, mass * (Decimal(1) - probability))

    visit(0, 0, 0, Decimal(1))
    return MappingProxyType(terminal)


def _average_terminal_distributions(
    distributions: Sequence[Mapping[tuple[int, int], Decimal]],
) -> Mapping[tuple[int, int], Decimal]:
    scores = sorted({score for distribution in distributions for score in distribution})
    divisor = Decimal(len(distributions))
    return MappingProxyType(
        {
            score: sum(distribution.get(score, Decimal()) for distribution in distributions)
            / divisor
            for score in scores
        }
    )


def _outcome_probabilities(
    terminal: Mapping[tuple[int, int], Decimal],
) -> Mapping[SelectionType, Decimal]:
    return MappingProxyType(
        {
            SelectionType.TEAM_A: sum(
                (mass for (wins_a, wins_b), mass in terminal.items() if wins_a > wins_b),
                Decimal(),
            ),
            SelectionType.TEAM_B: sum(
                (mass for (wins_a, wins_b), mass in terminal.items() if wins_b > wins_a),
                Decimal(),
            ),
            SelectionType.DRAW: sum(
                (mass for (wins_a, wins_b), mass in terminal.items() if wins_a == wins_b),
                Decimal(),
            ),
        }
    )


def _outcome_bounds(
    scenario: Sequence[ProbabilityInterval],
    *,
    best_of: int,
) -> Mapping[SelectionType, tuple[Decimal, Decimal]]:
    observed: dict[SelectionType, list[Decimal]] = {
        SelectionType.TEAM_A: [],
        SelectionType.TEAM_B: [],
        SelectionType.DRAW: [],
    }
    corners = product(*((item.p_low, item.p_high) for item in scenario))
    for corner in corners:
        outcomes = _outcome_probabilities(_terminal_distribution(corner, best_of=best_of))
        for selection, values in observed.items():
            values.append(outcomes[selection])
    return MappingProxyType(
        {selection: (min(values), max(values)) for selection, values in observed.items()}
    )


def _terminal_scores(
    distribution: Mapping[tuple[int, int], Decimal],
) -> tuple[SeriesTerminalScore, ...]:
    ordered = sorted(distribution.items())
    probabilities = _quantized_distribution(tuple(mass for _score, mass in ordered))
    return tuple(
        SeriesTerminalScore(
            team_a_wins=score[0],
            team_b_wins=score[1],
            probability=probabilities[index],
        )
        for index, (score, _mass) in enumerate(ordered)
    )


def _game_counts(scores: Sequence[SeriesTerminalScore]) -> Mapping[int, Decimal]:
    raw: dict[int, Decimal] = {}
    for score in scores:
        count = score.team_a_wins + score.team_b_wins
        raw[count] = raw.get(count, Decimal()) + score.probability
    ordered = sorted(raw.items())
    probabilities = _quantized_distribution(tuple(mass for _count, mass in ordered))
    return MappingProxyType(
        {count: probabilities[index] for index, (count, _mass) in enumerate(ordered)}
    )


def _quantized_distribution(values: Sequence[Decimal]) -> tuple[Decimal, ...]:
    if not values:
        return ()
    quantized = [value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN) for value in values[:-1]]
    quantized.append(Decimal(1) - sum(quantized, Decimal()))
    return tuple(quantized)


def _round_bound(value: Decimal, *, lower: bool) -> Decimal:
    return value.quantize(
        _QUANTUM,
        rounding=ROUND_FLOOR if lower else ROUND_CEILING,
    )
