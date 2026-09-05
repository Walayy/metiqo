"""Propriétés analytiques et simulées du pricing de série."""

from __future__ import annotations

from decimal import Decimal
from random import Random

from metiquo.contracts.enums import SelectionType
from metiquo.markets import (
    ProbabilityInterval,
    SeriesPricingEngine,
    SideAdjustedProbabilities,
    SideAssignment,
)


def test_analytical_bo1_bo3_bo5_and_bo2_draw_probabilities() -> None:
    engine = SeriesPricingEngine()
    game = _point("0.60")

    bo1 = engine.price(game, best_of=1, allows_draw=False)
    bo3 = engine.price(game, best_of=3, allows_draw=False)
    bo5 = engine.price(game, best_of=5, allows_draw=False)
    bo2 = engine.price(game, best_of=2, allows_draw=True)

    assert bo1.outcome(SelectionType.TEAM_A).probability == Decimal("0.60000000")
    assert bo3.outcome(SelectionType.TEAM_A).probability == Decimal("0.64800000")
    assert bo5.outcome(SelectionType.TEAM_A).probability == Decimal("0.68256000")
    assert bo2.outcome(SelectionType.TEAM_A).probability == Decimal("0.36000000")
    assert bo2.outcome(SelectionType.TEAM_B).probability == Decimal("0.16000000")
    assert bo2.outcome(SelectionType.DRAW).probability == Decimal("0.48000000")
    assert bo3.internal_game_counts == {
        2: Decimal("0.52000000"),
        3: Decimal("0.48000000"),
    }
    assert not bo3.secondary_markets_enabled


def test_every_supported_format_is_normalized_over_full_probability_domain() -> None:
    engine = SeriesPricingEngine()

    for index in range(101):
        probability = Decimal(index) / Decimal(100)
        for best_of, allows_draw in ((1, False), (2, True), (3, False), (5, False)):
            distribution = engine.price(
                _point(probability),
                best_of=best_of,
                allows_draw=allows_draw,
            )
            assert distribution.enabled
            assert sum(
                (outcome.probability for outcome in distribution.outcomes),
                Decimal(),
            ) == Decimal(1)
            assert all(
                Decimal() <= outcome.p_low <= outcome.probability <= outcome.p_high <= Decimal(1)
                for outcome in distribution.outcomes
            )


def test_unknown_side_is_the_equal_mixture_of_both_starting_assignments() -> None:
    engine = SeriesPricingEngine()
    sides = SideAdjustedProbabilities(
        team_a_blue=_interval("0.70", "0.65", "0.75"),
        team_a_red=_interval("0.45", "0.40", "0.50"),
    )
    blue = engine.price(
        _point("0.55"),
        best_of=3,
        allows_draw=False,
        side_probabilities=sides,
        side_assignment=SideAssignment.BLUE,
    )
    red = engine.price(
        _point("0.55"),
        best_of=3,
        allows_draw=False,
        side_probabilities=sides,
        side_assignment=SideAssignment.RED,
    )
    unknown = engine.price(
        _point("0.55"),
        best_of=3,
        allows_draw=False,
        side_probabilities=sides,
        side_assignment=SideAssignment.UNKNOWN,
    )

    for selection in (SelectionType.TEAM_A, SelectionType.TEAM_B):
        expected = (
            blue.outcome(selection).probability + red.outcome(selection).probability
        ) / Decimal(2)
        assert unknown.outcome(selection).probability == expected
        assert (
            unknown.outcome(selection).p_low
            <= unknown.outcome(selection).probability
            <= unknown.outcome(selection).p_high
        )


def test_analytical_distribution_matches_seeded_simulation() -> None:
    engine = SeriesPricingEngine()
    probability = Decimal("0.63")
    random = Random(20260907)

    for best_of in (1, 3, 5):
        analytical = engine.price(
            _point(probability),
            best_of=best_of,
            allows_draw=False,
        ).outcome(SelectionType.TEAM_A)
        simulated = _simulate_team_a(float(probability), best_of=best_of, random=random)
        assert abs(float(analytical.probability) - simulated) < 0.01


def test_unknown_or_inconsistent_formats_abstain_without_prices() -> None:
    engine = SeriesPricingEngine()

    unknown = engine.price(_point("0.5"), best_of=None, allows_draw=None)
    unsupported = engine.price(_point("0.5"), best_of=7, allows_draw=False)
    inconsistent = engine.price(_point("0.5"), best_of=2, allows_draw=False)

    assert not unknown.enabled and unknown.reason_codes == ("SERIES_FORMAT_UNKNOWN",)
    assert not unsupported.enabled and unsupported.reason_codes == ("SERIES_FORMAT_UNSUPPORTED",)
    assert not inconsistent.enabled and inconsistent.reason_codes == ("SERIES_RULES_INCONSISTENT",)
    assert unknown.outcomes == unsupported.outcomes == inconsistent.outcomes == ()


def _point(value: str | Decimal) -> ProbabilityInterval:
    probability = Decimal(value)
    return ProbabilityInterval(
        p50=probability,
        p_low=probability,
        p_high=probability,
    )


def _interval(p50: str, p_low: str, p_high: str) -> ProbabilityInterval:
    return ProbabilityInterval(
        p50=Decimal(p50),
        p_low=Decimal(p_low),
        p_high=Decimal(p_high),
    )


def _simulate_team_a(probability: float, *, best_of: int, random: Random) -> float:
    wins = 0
    trials = 30_000
    target = best_of // 2 + 1
    for _ in range(trials):
        wins_a = 0
        wins_b = 0
        while wins_a < target and wins_b < target:
            if random.random() < probability:
                wins_a += 1
            else:
                wins_b += 1
        wins += wins_a == target
    return wins / trials
