"""Règlement série : score terminal, nul explicite et ambiguïtés fermées."""

from dataclasses import replace

import pytest
from tests.paper.test_game_settlement import NOW, RULES, SOURCE

from metiquo.contracts.enums import PaperBetStatus as Status
from metiquo.contracts.enums import SelectionType as Selection
from metiquo.paper.series_settlement import SeriesResult, SeriesWinnerSettlementEngine

SERIES_RULES = replace(RULES, period="SERIES")
RESULT = SeriesResult(SOURCE, 3, 3, False, 2, 1, Selection.TEAM_A, True)


@pytest.mark.parametrize("best_of,score_a,score_b", [(1, 1, 0), (3, 2, 1), (5, 3, 2)])
def test_series_terminal_scores_settle_both_teams(best_of: int, score_a: int, score_b: int) -> None:
    result = replace(
        RESULT, expected_best_of=best_of, observed_best_of=best_of, score_a=score_a, score_b=score_b
    )
    engine = SeriesWinnerSettlementEngine()
    won = engine.settle(Selection.TEAM_A, result, SERIES_RULES, evaluated_at=NOW)
    assert won.status is Status.WON
    assert (
        engine.settle(Selection.TEAM_B, result, SERIES_RULES, evaluated_at=NOW).status
        is Status.LOST
    )
    assert won == engine.settle(Selection.TEAM_A, result, SERIES_RULES, evaluated_at=NOW)


def test_draw_requires_an_explicit_exhaustive_market() -> None:
    result = replace(
        RESULT,
        expected_best_of=2,
        observed_best_of=2,
        allows_draw=True,
        score_a=1,
        score_b=1,
        winner=Selection.DRAW,
    )
    rules = replace(
        SERIES_RULES, selections=frozenset({Selection.TEAM_A, Selection.DRAW, Selection.TEAM_B})
    )
    engine = SeriesWinnerSettlementEngine()
    assert engine.settle(Selection.DRAW, result, rules, evaluated_at=NOW).status is Status.WON
    assert engine.settle(Selection.TEAM_A, result, rules, evaluated_at=NOW).status is Status.LOST
    assert (
        engine.settle(Selection.TEAM_A, result, SERIES_RULES, evaluated_at=NOW).status
        is Status.PENDING_REVIEW
    )


@pytest.mark.parametrize(
    "case",
    [
        "unfinished",
        "overlong",
        "wrong_winner",
        "format_change",
        "shortened",
        "unresolved",
        "cancelled",
        "unvalidated",
    ],
)
def test_ambiguous_series_stays_pending(case: str) -> None:
    result = RESULT
    if case == "unfinished":
        result = replace(result, score_a=1, score_b=1)
    elif case == "overlong":
        result = replace(result, score_a=3, score_b=1)
    elif case == "wrong_winner":
        result = replace(result, winner=Selection.TEAM_B)
    elif case == "format_change":
        result = replace(result, observed_best_of=5)
    elif case == "shortened":
        result = replace(result, shortened=True)
    elif case == "unresolved":
        result = replace(result, winner=None)
    elif case == "cancelled":
        result = replace(result, cancelled=True)
    else:
        result = replace(result, source=replace(SOURCE, status="quarantined", validated_at=None))
    assert (
        SeriesWinnerSettlementEngine()
        .settle(Selection.TEAM_A, result, SERIES_RULES, evaluated_at=NOW)
        .status
        is Status.PENDING_REVIEW
    )


def test_cancelled_series_can_void_only_by_referenced_policy() -> None:
    result = replace(
        RESULT, cancelled=True, complete=False, winner=None, score_a=None, score_b=None
    )
    rules = replace(SERIES_RULES, cancelled_policy="void")
    assert (
        SeriesWinnerSettlementEngine()
        .settle(Selection.TEAM_A, result, rules, evaluated_at=NOW)
        .status
        is Status.VOID
    )
