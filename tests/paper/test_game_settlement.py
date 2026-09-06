"""Issues game winner et exceptions de règlement définies par la règle référencée."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from metiquo.contracts.enums import PaperBetStatus as Status
from metiquo.contracts.enums import SelectionType as Selection
from metiquo.paper.game_settlement import GameResult, GameWinnerSettlementEngine
from metiquo.paper.settlement_rules import ResultProvenance, SettlementRules

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)
SOURCE = ResultProvenance(
    UUID(int=1), "validated", NOW - timedelta(minutes=5), NOW - timedelta(minutes=4), "a" * 64
)
RESULT = GameResult(SOURCE, 1, 3, True, True, False)
RULES = SettlementRules(
    "game-rules-v1", "b" * 64, "GAME_1", frozenset({Selection.TEAM_A, Selection.TEAM_B})
)


@pytest.mark.parametrize(
    "selection,status", [(Selection.TEAM_A, Status.WON), (Selection.TEAM_B, Status.LOST)]
)
def test_game_result_is_deterministic_and_team_oriented(
    selection: Selection, status: Status
) -> None:
    engine = GameWinnerSettlementEngine()
    outcome = engine.settle(selection, RESULT, RULES, evaluated_at=NOW)
    assert outcome.status is status
    assert outcome == engine.settle(selection, RESULT, RULES, evaluated_at=NOW)
    assert (
        outcome.fingerprint == engine.settle(selection, RESULT, RULES, evaluated_at=NOW).fingerprint
    )
    assert outcome.evidence["rulesFingerprint"] == "b" * 64


@pytest.mark.parametrize("flag", ["remake", "forfeit", "cancelled"])
@pytest.mark.parametrize(
    "policy,status",
    [("review", Status.PENDING_REVIEW), ("void", Status.VOID), ("settle", Status.WON)],
)
def test_exception_obeys_the_recorded_policy(flag: str, policy: str, status: Status) -> None:
    result = replace(
        RESULT, remake=flag == "remake", forfeit=flag == "forfeit", cancelled=flag == "cancelled"
    )
    rules = replace(
        RULES,
        remake_policy=policy if flag == "remake" else "review",
        forfeit_policy=policy if flag == "forfeit" else "review",
        cancelled_policy=policy if flag == "cancelled" else "review",
    )
    assert (
        GameWinnerSettlementEngine()
        .settle(Selection.TEAM_A, result, rules, evaluated_at=NOW)
        .status
        is status
    )


@pytest.mark.parametrize(
    "case",
    [
        "unvalidated",
        "future",
        "incomplete",
        "ambiguous",
        "wrong_game",
        "unknown_rules",
        "missing_result",
    ],
)
def test_ambiguous_or_unproven_result_stays_pending(case: str) -> None:
    result = RESULT
    rules: SettlementRules | None = RULES
    if case == "unvalidated":
        result = replace(result, source=replace(SOURCE, status="quarantined", validated_at=None))
    elif case == "future":
        result = replace(result, source=replace(SOURCE, processed_at=NOW + timedelta(seconds=1)))
    elif case == "incomplete":
        result = replace(result, complete=False)
    elif case == "ambiguous":
        result = replace(result, team_b_won=True)
    elif case == "wrong_game":
        result = replace(result, game_number=2)
    elif case == "unknown_rules":
        rules = None
    else:
        result = replace(result, team_a_won=None, team_b_won=None)
    assert (
        GameWinnerSettlementEngine()
        .settle(Selection.TEAM_A, result, rules, evaluated_at=NOW)
        .status
        is Status.PENDING_REVIEW
    )
