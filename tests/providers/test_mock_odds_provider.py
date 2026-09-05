"""Application du contrat commun au fournisseur mock déterministe."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from metiquo.contracts.enums import GameTitle, ProviderStatus
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.mock import MockScenarioCatalog, MockScenarioKey, build_mock_scenario_catalog
from metiquo.repositories import MockOddsProvider
from tests.providers.odds_provider_contract import (
    OddsProviderContractFixture,
    assert_odds_provider_contract,
)

_REFERENCE_TIME = datetime(2026, 9, 4, 12, tzinfo=UTC)


def _provider(at: datetime = _REFERENCE_TIME) -> tuple[MockOddsProvider, MockScenarioCatalog]:
    catalog = build_mock_scenario_catalog(
        "odd-003-contract",
        FixedClock(UtcInstant(_REFERENCE_TIME)),
    )
    return MockOddsProvider(catalog, FixedClock(UtcInstant(at))), catalog


def test_mock_passes_the_exact_reusable_provider_contract() -> None:
    provider, _ = _provider()

    assert_odds_provider_contract(
        OddsProviderContractFixture(
            provider=provider,
            starts_from=_REFERENCE_TIME - timedelta(days=1),
            starts_to=_REFERENCE_TIME + timedelta(days=2),
            game_title=GameTitle.LEAGUE_OF_LEGENDS,
        )
    )


def test_injected_clock_reveals_price_changes_without_mutating_history() -> None:
    _, catalog = _provider()
    changed = catalog[MockScenarioKey.ODDS_CHANGE_WHILE_OPEN]
    first, second = changed.odds_history
    provider_before = MockOddsProvider(
        catalog,
        FixedClock(UtcInstant(second.captured_at - timedelta(microseconds=1))),
    )
    provider_after = MockOddsProvider(
        catalog,
        FixedClock(UtcInstant(second.captured_at + timedelta(seconds=1))),
    )
    event_id = f"mock-event-{MockScenarioKey.ODDS_CHANGE_WHILE_OPEN.value}"

    before_market = provider_before.get_event_markets(event_id)[0]
    before_capture = provider_before.capture_snapshot(event_id)
    after_market = provider_after.get_event_markets(event_id)[0]
    after_capture = provider_after.capture_snapshot(event_id)

    assert before_market.selections[0].decimal_odds == Decimal("4.20")
    assert before_capture.snapshots == (first.model_copy(update={"age_seconds": 34}),)
    assert after_market.selections[0].decimal_odds == Decimal("3.60")
    assert tuple(snapshot.odds_snapshot_id for snapshot in after_capture.snapshots) == (
        first.odds_snapshot_id,
        second.odds_snapshot_id,
    )
    assert changed.odds_history == (first, second)


def test_injected_clock_recomputes_staleness_and_health_at_read_time() -> None:
    provider, catalog = _provider(_REFERENCE_TIME + timedelta(minutes=5))
    stale = catalog[MockScenarioKey.STALE_ODDS]
    event_id = f"mock-event-{MockScenarioKey.STALE_ODDS.value}"

    snapshot = provider.capture_snapshot(event_id).snapshots[-1]
    health = provider.health()

    assert snapshot.age_seconds == 900
    assert stale.odds_history[-1].age_seconds == 600
    assert health.checked_at == _REFERENCE_TIME + timedelta(minutes=5)
    assert health.status is ProviderStatus.DEGRADED
    assert health.last_success_at is not None


def test_mock_provider_module_contains_no_network_client() -> None:
    source = (
        (Path(__file__).resolve().parents[2] / "python" / "metiquo" / "repositories" / "mock.py")
        .read_text(encoding="utf-8")
        .casefold()
    )

    for forbidden in ("httpx", "requests", "urllib", "socket", "selenium", "playwright"):
        assert forbidden not in source
