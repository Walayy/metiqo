"""Tests de contrat des repositories et du provider mock."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from metiquo.contracts.enums import GameTitle, MappingReviewStatus, ProviderStatus
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.mock import MockScenarioKey, build_mock_scenario_catalog
from metiquo.repositories import MockOddsProvider, build_mock_repository_bundle
from metiquo.repositories.contracts import OddsProvider
from metiquo.services import ReadService

REFERENCE_TIME = datetime(2026, 9, 4, 12, tzinfo=UTC)


def build_service() -> tuple[ReadService, MockOddsProvider]:
    catalog = build_mock_scenario_catalog("metiquo-demo-v1", FixedClock(UtcInstant(REFERENCE_TIME)))
    bundle = build_mock_repository_bundle(catalog)
    service = ReadService(
        opportunities=bundle.opportunities,
        events=bundle.events,
        models=bundle.models,
        paper=bundle.paper,
        data_health=bundle.data_health,
        mappings=bundle.mappings,
    )
    return service, bundle.odds_provider


def test_all_mock_reads_cross_the_common_service_boundary() -> None:
    service, _ = build_service()

    assert len(service.list_opportunities()) == 12
    assert len(service.list_events()) == 12
    assert len(service.list_models()) == 12
    assert len(service.list_paper_bets()) == 2
    assert len(service.list_data_sources()) == 1
    assert len(service.list_pending_mappings()) == 1

    opportunity = service.list_opportunities()[0]
    assert service.get_opportunity(opportunity.signal_id) == opportunity
    assert service.get_event(opportunity.event.event_id) is not None
    assert service.list_event_markets(opportunity.event.event_id)
    assert service.get_odds_history(opportunity.event.event_id)
    assert service.get_model(opportunity.model.model_version_id) is not None

    paper_bet = service.list_paper_bets()[0]
    assert service.get_paper_bet(paper_bet.paper_bet_id) == paper_bet

    assert service.get_opportunity(uuid4()) is None
    assert service.get_event(uuid4()) is None
    assert service.get_model(uuid4()) is None
    assert service.get_paper_bet(uuid4()) is None
    assert service.list_event_markets(uuid4()) == ()
    assert service.get_odds_history(uuid4()) == ()


def test_mapping_and_data_health_repositories_preserve_operational_truth() -> None:
    service, provider = build_service()

    reviews = service.list_pending_mappings()
    assert len(reviews) == 1
    assert reviews[0].status is MappingReviewStatus.PENDING
    assert provider.health() == service.list_data_sources()[0]
    assert provider.health().status is ProviderStatus.DEGRADED
    assert provider.health().last_success_at is not None


def accepts_provider_contract(provider: OddsProvider) -> str:
    return provider.provider_code


def test_mock_odds_provider_implements_interchangeable_contract() -> None:
    _, provider = build_service()

    assert accepts_provider_contract(provider) == "mock-provider"
    events = provider.list_events(
        REFERENCE_TIME - timedelta(days=1),
        REFERENCE_TIME + timedelta(days=2),
        GameTitle.LEAGUE_OF_LEGENDS,
    )
    assert len(events) == 12
    first = events[0]
    markets = provider.get_event_markets(first.provider_event_id)
    assert len(markets) == 1
    assert markets[0].provider_event_id == first.provider_event_id
    assert markets[0].selections

    capture = provider.capture_snapshot(first.provider_event_id)
    assert capture.provider_event_id == first.provider_event_id
    assert capture.snapshots
    assert all(snapshot.provider == provider.provider_code for snapshot in capture.snapshots)

    assert provider.get_event_markets("unknown") == ()
    with pytest.raises(LookupError, match="Événement fournisseur inconnu"):
        provider.capture_snapshot("unknown")
    with pytest.raises(ValueError, match="startsTo"):
        provider.list_events(
            REFERENCE_TIME,
            REFERENCE_TIME - timedelta(seconds=1),
            GameTitle.LEAGUE_OF_LEGENDS,
        )


def test_odds_history_remains_append_only_and_chronological() -> None:
    service, _ = build_service()
    changed = next(
        opportunity
        for opportunity in service.list_opportunities()
        if opportunity.explanation_reference
        == f"mock-v1:{MockScenarioKey.ODDS_CHANGE_WHILE_OPEN.value}"
    )

    snapshots = service.get_odds_history(changed.event.event_id)
    assert len(snapshots) == 2
    assert snapshots[0].odds_snapshot_id != snapshots[1].odds_snapshot_id
    assert snapshots[0].captured_at < snapshots[1].captured_at
