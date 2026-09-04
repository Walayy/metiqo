"""Tests des douze scénarios mock normatifs."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from metiquo.contracts.enums import (
    AbstentionReason,
    DataMode,
    EventStatus,
    FreshnessStatus,
    MarketStatus,
    PaperBetStatus,
    ProviderStatus,
    ValueGrade,
)
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.mock import (
    MockResultState,
    MockScenarioCatalog,
    MockScenarioKey,
    build_mock_scenario_catalog,
)

REFERENCE_TIME = datetime(2026, 9, 4, 12, tzinfo=UTC)
SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "mock_scenarios_v1.sha256"


def build_catalog(
    seed: str = "metiquo-demo-v1", reference_time: datetime = REFERENCE_TIME
) -> MockScenarioCatalog:
    return build_mock_scenario_catalog(seed, FixedClock(UtcInstant(reference_time)))


def test_catalog_contains_and_addresses_each_normative_scenario() -> None:
    catalog = build_catalog()

    assert len(catalog.scenarios) == 12
    assert tuple(scenario.scenario_key for scenario in catalog.scenarios) == tuple(MockScenarioKey)
    for key in MockScenarioKey:
        assert catalog[key].scenario_key is key
        assert catalog[key].opportunity.meta.data_mode is DataMode.MOCK


def test_decision_scenarios_expose_expected_grades_and_abstentions() -> None:
    catalog = build_catalog()

    low_value = catalog[MockScenarioKey.LOW_VALUE]
    assert low_value.opportunity.value.grade is ValueGrade.NO_EDGE
    assert low_value.opportunity.quality.abstention_reasons == (AbstentionReason.EDGE_TOO_SMALL,)

    outsider = catalog[MockScenarioKey.OUTSIDER_VALUE]
    assert outsider.opportunity.book.decimal_odds == Decimal("4.50")
    assert outsider.opportunity.value.grade is ValueGrade.STRONG_VALUE
    assert outsider.opportunity.quality.publishable is True

    stale_odds = catalog[MockScenarioKey.STALE_ODDS]
    assert stale_odds.opportunity.book.age_seconds == 600
    assert stale_odds.opportunity.meta.freshness is FreshnessStatus.STALE
    assert stale_odds.opportunity.quality.abstention_reasons == (AbstentionReason.ODDS_STALE,)

    suspended = catalog[MockScenarioKey.SUSPENDED_MARKET]
    assert suspended.current_market.status is MarketStatus.SUSPENDED
    assert suspended.opportunity.book.market_status is MarketStatus.SUSPENDED
    assert suspended.opportunity.quality.abstention_reasons == (AbstentionReason.MARKET_SUSPENDED,)


def test_mock_values_are_numerically_coherent() -> None:
    catalog = build_catalog()
    precision = Decimal("0.000001")

    for scenario in catalog.scenarios:
        opportunity = scenario.opportunity
        no_vig_probability = opportunity.book.no_vig_probability
        assert no_vig_probability is not None
        assert opportunity.book.informational_only is False
        assert opportunity.value.edge == opportunity.model.probability - no_vig_probability
        assert opportunity.value.expected_value == (
            opportunity.model.probability * opportunity.book.decimal_odds - Decimal(1)
        )
        assert opportunity.value.conservative_expected_value == (
            opportunity.model.probability_low * opportunity.book.decimal_odds - Decimal(1)
        )
        assert opportunity.value.fair_odds == (Decimal(1) / opportunity.model.probability).quantize(
            precision
        )


def test_data_mapping_and_model_failure_scenarios_are_explicit() -> None:
    catalog = build_catalog()

    mapping = catalog[MockScenarioKey.AMBIGUOUS_MAPPING]
    assert mapping.mapping_review is not None
    assert len(mapping.mapping_review.candidates) == 2
    assert mapping.opportunity.quality.mapping_confidence == Decimal("0.620000")
    assert mapping.opportunity.quality.abstention_reasons == (
        AbstentionReason.EVENT_MAPPING_AMBIGUOUS,
    )

    incomplete = catalog[MockScenarioKey.INCOMPLETE_ORACLE_DATA]
    assert incomplete.opportunity.model.data_coverage == Decimal("0.420000")
    assert incomplete.opportunity.quality.abstention_reasons == (
        AbstentionReason.INSUFFICIENT_HISTORY,
    )

    stale_model = catalog[MockScenarioKey.STALE_MODEL]
    assert stale_model.opportunity.quality.abstention_reasons == (AbstentionReason.MODEL_STALE,)
    assert (
        stale_model.opportunity.book.captured_at - stale_model.model_summary.created_at
        == timedelta(days=240)
    )

    uncertain = catalog[MockScenarioKey.HIGH_UNCERTAINTY]
    assert uncertain.opportunity.model.confidence == Decimal("0.310000")
    assert uncertain.opportunity.model.probability_low == Decimal("0.200000")
    assert uncertain.opportunity.model.probability_high == Decimal("0.720000")
    assert uncertain.opportunity.quality.abstention_reasons == (
        AbstentionReason.OUT_OF_DISTRIBUTION,
    )


def test_operational_and_result_scenarios_preserve_history() -> None:
    catalog = build_catalog()

    failed_sync = catalog[MockScenarioKey.FAILED_SYNC_WITH_VALID_SNAPSHOT]
    assert failed_sync.source_sync_failed is True
    assert failed_sync.last_valid_snapshot_id == failed_sync.opportunity.book.odds_snapshot_id
    assert failed_sync.opportunity.book.provider_status is ProviderStatus.OPERATIONAL
    assert failed_sync.opportunity.quality.abstention_reasons == (AbstentionReason.SOURCE_STALE,)

    changed = catalog[MockScenarioKey.ODDS_CHANGE_WHILE_OPEN]
    assert changed.odds_changed_while_open is True
    assert len(changed.odds_history) == 2
    assert changed.opportunity.book == changed.odds_history[0]
    assert changed.odds_history[0].decimal_odds == Decimal("4.20")
    assert changed.odds_history[1].decimal_odds == Decimal("3.60")
    assert changed.odds_history[0].captured_at < changed.odds_history[1].captured_at

    void = catalog[MockScenarioKey.VOID_RESULT]
    assert void.opportunity.event.status is EventStatus.SCHEDULED
    assert void.opportunity.market.status is MarketStatus.OPEN
    assert void.current_event.status is EventStatus.CANCELLED
    assert void.current_market.status is MarketStatus.VOID
    assert void.paper_bet is not None
    assert void.paper_bet.status is PaperBetStatus.VOID
    assert void.paper_bet.profit_loss == Decimal("0.00")

    quarantined = catalog[MockScenarioKey.QUARANTINED_RESULT]
    assert quarantined.opportunity.event.status is EventStatus.SCHEDULED
    assert quarantined.current_event.status is EventStatus.FINISHED
    assert quarantined.current_market.status is MarketStatus.SETTLED
    assert quarantined.result_state is MockResultState.QUARANTINED
    assert quarantined.quarantine_reason is not None
    assert quarantined.paper_bet is not None
    assert quarantined.paper_bet.status is PaperBetStatus.PENDING_REVIEW


def test_all_timestamps_are_controlled_relative_to_the_injected_clock() -> None:
    catalog = build_catalog()

    for index, scenario in enumerate(catalog.scenarios):
        for odds in scenario.odds_history:
            assert catalog.reference_time - odds.captured_at == timedelta(seconds=odds.age_seconds)
        if scenario.result_state is MockResultState.PENDING:
            assert scenario.current_event.starts_at == REFERENCE_TIME + timedelta(
                hours=4, minutes=30 * index
            )
        assert scenario.opportunity.model.prediction_cutoff < scenario.current_event.starts_at


def test_mock_catalog_matches_the_versioned_full_data_snapshot() -> None:
    catalog = build_catalog()
    payload = catalog.model_dump_json(by_alias=True)
    expected_digest = SNAPSHOT_PATH.read_text(encoding="utf-8").strip()

    assert sha256(payload.encode()).hexdigest() == expected_digest
    assert MockScenarioCatalog.model_validate_json(payload) == catalog


@pytest.mark.parametrize(
    "seed",
    ("metiquo-demo-v1", "seed-000", "seed-999", "graine-déterministe"),
)
def test_determinism_property_for_representative_seeds(seed: str) -> None:
    first = build_catalog(seed)
    second = build_catalog(seed)

    assert first == second
    assert first.model_dump_json(by_alias=True) == second.model_dump_json(by_alias=True)


def test_seed_controls_ids_while_clock_controls_only_relative_times() -> None:
    initial = build_catalog()
    shifted = build_catalog(reference_time=REFERENCE_TIME + timedelta(days=7))
    other_seed = build_catalog(seed="another-seed")

    initial_ids = {scenario.opportunity.signal_id for scenario in initial.scenarios}
    other_ids = {scenario.opportunity.signal_id for scenario in other_seed.scenarios}
    assert initial_ids.isdisjoint(other_ids)

    for first, second in zip(initial.scenarios, shifted.scenarios, strict=True):
        assert first.opportunity.signal_id == second.opportunity.signal_id
        assert first.opportunity.value == second.opportunity.value
        assert first.opportunity.book.decimal_odds == second.opportunity.book.decimal_odds
        assert second.current_event.starts_at - first.current_event.starts_at == timedelta(days=7)
        assert (
            second.opportunity.book.captured_at - first.opportunity.book.captured_at
            == timedelta(days=7)
        )


def test_empty_seed_is_rejected() -> None:
    with pytest.raises(ValueError, match="graine mock ne peut pas être vide"):
        build_catalog(seed="   ")
