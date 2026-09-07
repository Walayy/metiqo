"""Règlement SERIES_WINNER depuis un score canonique complet et non ambigu."""

from dataclasses import dataclass
from datetime import datetime

from metiquo.contracts.enums import PaperBetStatus as Status
from metiquo.contracts.enums import SelectionType as Selection
from metiquo.paper.settlement_rules import (
    ResultProvenance,
    SettlementOutcome,
    SettlementRules,
    exception_outcome,
)

SERIES_SETTLEMENT_VERSION = "series-settlement-v1"


@dataclass(frozen=True, slots=True)
class SeriesResult:
    source: ResultProvenance
    expected_best_of: int | None
    observed_best_of: int | None
    allows_draw: bool | None
    score_a: int | None
    score_b: int | None
    winner: Selection | None
    complete: bool
    shortened: bool = False
    remake: bool = False
    forfeit: bool = False
    cancelled: bool = False


class SeriesWinnerSettlementEngine:
    def settle(
        self,
        selection: Selection,
        result: SeriesResult,
        rules: SettlementRules | None,
        *,
        evaluated_at: datetime,
    ) -> SettlementOutcome:
        if selection not in {Selection.TEAM_A, Selection.TEAM_B, Selection.DRAW}:
            raise ValueError("SERIES_WINNER exige une sélection équipe ou nul")
        flags = tuple(name for name in ("remake", "forfeit", "cancelled") if getattr(result, name))
        evidence: dict[str, object] = {
            **result.source.document(),
            "engineVersion": SERIES_SETTLEMENT_VERSION,
            "selection": selection.value,
            "expectedBestOf": result.expected_best_of,
            "observedBestOf": result.observed_best_of,
            "allowsDraw": result.allows_draw,
            "scoreA": result.score_a,
            "scoreB": result.score_b,
            "winner": result.winner.value if result.winner else None,
            "complete": result.complete,
            "shortened": result.shortened,
            "flags": list(flags),
            "rulesReference": rules.reference if rules else None,
            "rulesFingerprint": rules.fingerprint if rules else None,
        }

        def pending(reason: str) -> SettlementOutcome:
            return SettlementOutcome(Status.PENDING_REVIEW, reason, evidence)

        if (
            rules is None
            or not rules.active
            or rules.period != "SERIES"
            or selection not in rules.selections
        ):
            return pending("MARKET_RULES_UNKNOWN")
        if not result.source.known_validated_at(evaluated_at):
            return pending("RESULT_SOURCE_UNVALIDATED")
        if result.expected_best_of != result.observed_best_of:
            return pending("SERIES_FORMAT_CHANGED")
        if result.shortened:
            return pending("SERIES_SHORTENED")
        best_of = result.observed_best_of
        if best_of not in {1, 2, 3, 4, 5} or result.allows_draw is None:
            return pending("SERIES_FORMAT_UNKNOWN")
        assert best_of is not None
        if result.allows_draw != (best_of % 2 == 0):
            return pending("SERIES_FORMAT_AMBIGUOUS")
        expected = {Selection.TEAM_A, Selection.TEAM_B}
        if result.allows_draw:
            expected.add(Selection.DRAW)
        if rules.selections != frozenset(expected):
            return pending("DRAW_RULES_UNKNOWN")
        exceptional = exception_outcome(flags, rules, evidence)
        if exceptional is not None:
            return exceptional
        if not result.complete or result.score_a is None or result.score_b is None:
            return pending("RESULT_INCOMPLETE")
        a, b = result.score_a, result.score_b
        if min(a, b) < 0 or a + b > best_of:
            return pending("SERIES_SCORE_INVALID")
        if result.allows_draw:
            if a + b != best_of:
                return pending("SERIES_SCORE_NONTERMINAL")
        else:
            target = best_of // 2 + 1
            if max(a, b) != target or min(a, b) >= target:
                return pending("SERIES_SCORE_NONTERMINAL")
        winner = Selection.TEAM_A if a > b else Selection.TEAM_B if b > a else Selection.DRAW
        if result.winner is not winner:
            return pending("SERIES_RESULT_AMBIGUOUS")
        return SettlementOutcome(
            Status.WON if selection is winner else Status.LOST, "VALIDATED_SERIES_RESULT", evidence
        )
