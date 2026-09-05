"""Fixtures structurelles du mapping canonique des marchés."""

from dataclasses import replace
from decimal import Decimal

import pytest

from metiquo.contracts.enums import MarketPeriod, MarketType, SelectionType
from metiquo.mapping import (
    MarketMappingEngine,
    MarketMappingReason,
    MarketMappingStatus,
    MarketRulesReference,
    RawProviderMarket,
    UnresolvedMarketMappingError,
)


def test_complete_structure_maps_regardless_of_the_label() -> None:
    engine = MarketMappingEngine((_binary_rules(),))

    english = engine.evaluate(_raw(raw_label="Match winner"))
    unrelated_label = engine.evaluate(_raw(raw_label="Qui remportera la rencontre ?"))

    assert english.status is MarketMappingStatus.MAPPED
    assert unrelated_label.status is MarketMappingStatus.MAPPED
    assert english.require_mapped() == unrelated_label.require_mapped()
    assert english.require_mapped().rules_reference == "lol-match-winner-series-v1"


def test_a_label_alone_never_resolves_an_unknown_market() -> None:
    decision = MarketMappingEngine((_binary_rules(),)).evaluate(
        _raw(raw_label="Match winner", declared_type="TOTAL_KILLS")
    )

    assert decision.status is MarketMappingStatus.UNKNOWN
    assert decision.reason is MarketMappingReason.MARKET_TYPE_MISMATCH
    with pytest.raises(UnresolvedMarketMappingError, match="aucune prédiction"):
        decision.require_mapped()


@pytest.mark.parametrize(
    ("changes", "reason"),
    (
        ({"settlement_rules_reference": None}, MarketMappingReason.RULES_REFERENCE_MISSING),
        (
            {"settlement_rules_reference": "unknown-rules-v9"},
            MarketMappingReason.RULES_REFERENCE_UNKNOWN,
        ),
        ({"period": "GAME_1"}, MarketMappingReason.PERIOD_MISMATCH),
        ({"line": Decimal("1.5")}, MarketMappingReason.LINE_STRUCTURE_MISMATCH),
        ({"unit": "maps"}, MarketMappingReason.UNIT_MISMATCH),
        (
            {"selection_types": ("TEAM_A", "TEAM_B", "DRAW")},
            MarketMappingReason.OUTCOME_STRUCTURE_MISMATCH,
        ),
        ({"remake_policy": "settle"}, MarketMappingReason.SETTLEMENT_POLICY_MISMATCH),
        ({"forfeit_policy": "void"}, MarketMappingReason.SETTLEMENT_POLICY_MISMATCH),
        ({"cancelled_policy": "settle"}, MarketMappingReason.SETTLEMENT_POLICY_MISMATCH),
    ),
)
def test_every_structural_dimension_is_required(
    changes: dict[str, object],
    reason: MarketMappingReason,
) -> None:
    decision = MarketMappingEngine((_binary_rules(),)).evaluate(
        replace(_raw(), **changes)  # type: ignore[arg-type]
    )

    assert decision.status is MarketMappingStatus.UNKNOWN
    assert decision.reason is reason


def test_inactive_rules_never_activate_and_three_way_draw_requires_its_own_rules() -> None:
    inactive = replace(_binary_rules(), active=False)
    inactive_decision = MarketMappingEngine((inactive,)).evaluate(_raw())
    draw_rules = replace(
        _binary_rules(),
        reference="lol-match-winner-series-draw-v1",
        selection_types=(SelectionType.TEAM_A, SelectionType.TEAM_B, SelectionType.DRAW),
    )
    draw_raw = replace(
        _raw(),
        settlement_rules_reference=draw_rules.reference,
        selection_types=("TEAM_A", "TEAM_B", "DRAW"),
    )
    draw_decision = MarketMappingEngine((draw_rules,)).evaluate(draw_raw)

    assert inactive_decision.reason is MarketMappingReason.RULES_REFERENCE_INACTIVE
    assert draw_decision.status is MarketMappingStatus.MAPPED
    assert draw_decision.require_mapped().selection_types[-1] is SelectionType.DRAW


def _binary_rules() -> MarketRulesReference:
    return MarketRulesReference(
        reference="lol-match-winner-series-v1",
        market_type=MarketType.MATCH_WINNER,
        period=MarketPeriod.SERIES,
        line_required=False,
        unit="winner",
        selection_types=(SelectionType.TEAM_A, SelectionType.TEAM_B),
        remake_policy="void",
        forfeit_policy="settle",
        cancelled_policy="void",
    )


def _raw(**changes: object) -> RawProviderMarket:
    values: dict[str, object] = {
        "provider_market_id": "provider-match-winner",
        "raw_label": "Vainqueur",
        "declared_type": "MATCH_WINNER",
        "period": "SERIES",
        "line": None,
        "unit": "winner",
        "selection_types": ("TEAM_A", "TEAM_B"),
        "settlement_rules_reference": "lol-match-winner-series-v1",
        "remake_policy": "void",
        "forfeit_policy": "settle",
        "cancelled_policy": "void",
    }
    values.update(changes)
    return RawProviderMarket(**values)  # type: ignore[arg-type]
