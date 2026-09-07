"""Règlement GAME_WINNER d'après une preuve OE et les règles versionnées."""

from dataclasses import dataclass
from datetime import datetime

from metiquo.contracts.enums import PaperBetStatus as Status
from metiquo.contracts.enums import SelectionType
from metiquo.markets.game_winner import GameWinnerMarketPlugin
from metiquo.paper.settlement_rules import (
    ResultProvenance,
    SettlementOutcome,
    SettlementRules,
    exception_outcome,
)

GAME_SETTLEMENT_VERSION = "game-settlement-v1"


@dataclass(frozen=True, slots=True)
class GameResult:
    source: ResultProvenance
    game_number: int | None
    best_of: int | None
    complete: bool
    team_a_won: bool | None
    team_b_won: bool | None
    remake: bool = False
    forfeit: bool = False
    cancelled: bool = False


class GameWinnerSettlementEngine:
    def settle(
        self,
        selection: SelectionType,
        result: GameResult,
        rules: SettlementRules | None,
        *,
        evaluated_at: datetime,
    ) -> SettlementOutcome:
        if selection not in {SelectionType.TEAM_A, SelectionType.TEAM_B}:
            raise ValueError("GAME_WINNER exige une sélection équipe")
        flags = tuple(name for name in ("remake", "forfeit", "cancelled") if getattr(result, name))
        evidence: dict[str, object] = {
            **result.source.document(),
            "engineVersion": GAME_SETTLEMENT_VERSION,
            "selection": selection.value,
            "gameNumber": result.game_number,
            "bestOf": result.best_of,
            "complete": result.complete,
            "teamAWon": result.team_a_won,
            "teamBWon": result.team_b_won,
            "flags": list(flags),
            "rulesReference": rules.reference if rules else None,
            "rulesFingerprint": rules.fingerprint if rules else None,
        }
        if (
            rules is None
            or not rules.active
            or rules.selections != frozenset({SelectionType.TEAM_A, SelectionType.TEAM_B})
        ):
            return SettlementOutcome(Status.PENDING_REVIEW, "MARKET_RULES_UNKNOWN", evidence)
        if not result.source.known_validated_at(evaluated_at):
            return SettlementOutcome(Status.PENDING_REVIEW, "RESULT_SOURCE_UNVALIDATED", evidence)
        if not (
            (rules.period == "SERIES" and result.best_of == 1)
            or (result.game_number is not None and rules.period == f"GAME_{result.game_number}")
        ):
            return SettlementOutcome(Status.PENDING_REVIEW, "RESULT_PERIOD_MISMATCH", evidence)
        exceptional = exception_outcome(flags, rules, evidence)
        if exceptional is not None:
            return exceptional
        if not result.complete:
            return SettlementOutcome(Status.PENDING_REVIEW, "RESULT_INCOMPLETE", evidence)
        if (
            result.team_a_won is None
            or result.team_b_won is None
            or result.team_a_won == result.team_b_won
        ):
            return SettlementOutcome(Status.PENDING_REVIEW, "RESULT_AMBIGUOUS", evidence)
        winner = SelectionType.TEAM_A if result.team_a_won else SelectionType.TEAM_B
        settled = GameWinnerMarketPlugin().settle(selection, winning_selection=winner)
        return SettlementOutcome(Status(settled.value), "VALIDATED_GAME_RESULT", evidence)
