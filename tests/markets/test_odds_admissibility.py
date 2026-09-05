"""Fraîcheur et blocages de marché avant génération d'un signal."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from metiquo.config import Settings
from metiquo.contracts import OddsSnapshot
from metiquo.contracts.enums import (
    AbstentionReason,
    MarketStatus,
    MarketType,
    OddsPhase,
    ProviderStatus,
    SelectionType,
)
from metiquo.markets import (
    MarketAdmissibilityGate,
    MarketAdmissibilityInput,
    OddsFreshnessPolicy,
)

_CAPTURED_AT = datetime(2026, 9, 7, 16, 0, tzinfo=UTC)
_STARTS_AT = _CAPTURED_AT + timedelta(hours=1)
_EVENT_ID = UUID("11111111-1111-4111-8111-111111111111")
_MARKET_ID = UUID("22222222-2222-4222-8222-222222222222")


def test_snapshot_is_fresh_at_exact_sla_then_becomes_stale() -> None:
    gate = MarketAdmissibilityGate(OddsFreshnessPolicy(90))
    request = _request(evaluated_at=_CAPTURED_AT + timedelta(seconds=90))

    fresh = gate.evaluate(request)
    stale = gate.evaluate(replace(request, evaluated_at=_CAPTURED_AT + timedelta(seconds=91)))

    assert fresh.admissible is True
    assert fresh.reasons == ()
    assert fresh.age_seconds == fresh.max_age_seconds == 90
    assert stale.admissible is False
    assert stale.reasons == (AbstentionReason.ODDS_STALE,)


def test_provider_market_and_phase_age_overrides_have_deterministic_precedence() -> None:
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "real",
            "database_url": "postgresql+psycopg://metiqo@postgres:5432/metiqo",
            "odds_provider": "disabled",
            "odds_max_age_seconds": 90,
            "odds_provider_max_age_seconds": {"licensed-a": 15},
            "odds_market_max_age_seconds": {"MATCH_WINNER": 30},
            "odds_phase_max_age_seconds": {"prematch": 45},
        }
    )
    policy = OddsFreshnessPolicy.from_settings(settings)

    assert policy.max_age_seconds("licensed-a", MarketType.MATCH_WINNER, OddsPhase.PREMATCH) == 15
    assert policy.max_age_seconds("licensed-b", MarketType.MATCH_WINNER, OddsPhase.PREMATCH) == 30
    assert policy.max_age_seconds("licensed-b", MarketType.MATCH_WINNER, OddsPhase.LIVE) == 30


def test_prematch_market_is_blocked_at_event_start_and_for_post_start_capture() -> None:
    gate = MarketAdmissibilityGate(OddsFreshnessPolicy(7200))

    evaluated_after_start = gate.evaluate(_request(evaluated_at=_STARTS_AT))
    captured_after_start = gate.evaluate(
        _request(
            evaluated_at=_STARTS_AT + timedelta(seconds=1),
            captured_at=_STARTS_AT,
        )
    )

    assert evaluated_after_start.reasons == (AbstentionReason.EVENT_ALREADY_STARTED,)
    assert captured_after_start.reasons == (AbstentionReason.EVENT_ALREADY_STARTED,)


@pytest.mark.parametrize(
    "status",
    [MarketStatus.SUSPENDED, MarketStatus.SETTLED, MarketStatus.VOID],
)
def test_only_open_market_status_is_admissible(status: MarketStatus) -> None:
    decision = MarketAdmissibilityGate(OddsFreshnessPolicy(90)).evaluate(_request(status=status))

    assert decision.admissible is False
    assert decision.reasons == (AbstentionReason.MARKET_SUSPENDED,)


def test_missing_target_and_incomplete_outcomes_are_distinct_blockers() -> None:
    only_team_a = (_snapshot(SelectionType.TEAM_A),)
    gate = MarketAdmissibilityGate(OddsFreshnessPolicy(90))

    missing_target = gate.evaluate(
        _request(
            required_selection=SelectionType.TEAM_B,
            snapshots=only_team_a,
        )
    )
    incomplete = gate.evaluate(_request(snapshots=only_team_a))

    assert missing_target.reasons == (
        AbstentionReason.SELECTION_MISSING,
        AbstentionReason.MARKET_OUTCOMES_INCOMPLETE,
    )
    assert incomplete.reasons == (AbstentionReason.MARKET_OUTCOMES_INCOMPLETE,)


def test_explicit_non_no_vig_strategy_can_accept_a_partial_market() -> None:
    decision = MarketAdmissibilityGate(OddsFreshnessPolicy(90)).evaluate(
        _request(
            snapshots=(_snapshot(SelectionType.TEAM_A),),
            requires_complete_market=False,
        )
    )

    assert decision.admissible is True


def test_future_or_mixed_capture_scope_is_temporally_invalid() -> None:
    future = _snapshot(
        SelectionType.TEAM_A,
        captured_at=_CAPTURED_AT + timedelta(seconds=1),
    )
    another_market = _snapshot(SelectionType.TEAM_B).model_copy(
        update={"market_id": UUID("33333333-3333-4333-8333-333333333333")}
    )
    request = _request(
        evaluated_at=_CAPTURED_AT,
        snapshots=(future, another_market),
    )

    decision = MarketAdmissibilityGate(OddsFreshnessPolicy(90)).evaluate(request)

    assert decision.admissible is False
    assert decision.reasons == (AbstentionReason.ODDS_TEMPORAL_ORDER_INVALID,)
    assert decision.age_seconds == 0


def test_informational_snapshot_and_live_phase_are_never_signalable() -> None:
    informational = tuple(
        snapshot.model_copy(update={"informational_only": True}) for snapshot in _snapshots()
    )
    gate = MarketAdmissibilityGate(OddsFreshnessPolicy(90))

    info_decision = gate.evaluate(_request(snapshots=informational))
    live_decision = gate.evaluate(_request(phase=OddsPhase.LIVE))

    assert info_decision.reasons == (AbstentionReason.ODDS_INFORMATIONAL_ONLY,)
    assert live_decision.reasons == (AbstentionReason.LIVE_BETTING_OUT_OF_SCOPE,)


def _request(
    *,
    evaluated_at: datetime = _CAPTURED_AT + timedelta(seconds=30),
    captured_at: datetime = _CAPTURED_AT,
    status: MarketStatus = MarketStatus.OPEN,
    phase: OddsPhase = OddsPhase.PREMATCH,
    required_selection: SelectionType = SelectionType.TEAM_A,
    snapshots: tuple[OddsSnapshot, ...] | None = None,
    requires_complete_market: bool = True,
) -> MarketAdmissibilityInput:
    return MarketAdmissibilityInput(
        provider_code="licensed-a",
        event_starts_at=_STARTS_AT,
        market_type=MarketType.MATCH_WINNER,
        phase=phase,
        evaluated_at=evaluated_at,
        required_selection=required_selection,
        expected_selections=frozenset({SelectionType.TEAM_A, SelectionType.TEAM_B}),
        snapshots=(
            _snapshots(captured_at=captured_at, status=status) if snapshots is None else snapshots
        ),
        requires_complete_market=requires_complete_market,
    )


def _snapshots(
    *,
    captured_at: datetime = _CAPTURED_AT,
    status: MarketStatus = MarketStatus.OPEN,
) -> tuple[OddsSnapshot, ...]:
    return (
        _snapshot(SelectionType.TEAM_A, captured_at=captured_at, status=status),
        _snapshot(SelectionType.TEAM_B, captured_at=captured_at, status=status),
    )


def _snapshot(
    selection: SelectionType,
    *,
    captured_at: datetime = _CAPTURED_AT,
    status: MarketStatus = MarketStatus.OPEN,
) -> OddsSnapshot:
    is_team_a = selection is SelectionType.TEAM_A
    return OddsSnapshot(
        odds_snapshot_id=UUID(
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
            if is_team_a
            else "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        ),
        event_id=_EVENT_ID,
        market_id=_MARKET_ID,
        selection=selection,
        provider="licensed-a",
        provider_status=ProviderStatus.OPERATIONAL,
        market_status=status,
        decimal_odds=Decimal("1.80") if is_team_a else Decimal("2.10"),
        captured_at=captured_at,
        age_seconds=0,
        raw_implied_probability=Decimal("0.55555556") if is_team_a else Decimal("0.47619048"),
        no_vig_probability=Decimal("0.53846154") if is_team_a else Decimal("0.46153846"),
        provenance_reference=f"licensed-fixture:{selection.value}",
    )
