"""Parcours intégrés provider vers le gate coté résolu P5."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine

from metiquo.contracts import Event
from metiquo.contracts.enums import (
    EventStatus,
    GameTitle,
    MarketPeriod,
    MarketType,
    SelectionType,
)
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.mapping import (
    EventMappingStatus,
    MarketMappingReason,
    MarketRulesReference,
    PostgresEventMatchingService,
    PostgresMarketMappingService,
)
from metiquo.mock import build_mock_scenario_catalog
from metiquo.providers import ManualImportOddsProvider
from metiquo.repositories import MockOddsProvider
from metiquo.repositories.postgres_canonical import PostgresCanonicalRepository
from metiquo.services import (
    OddsCaptureService,
    OddsCaptureSource,
    OddsPricingGateError,
    PostgresResolvedOddsGate,
    ResolvedOddsGateReason,
    ResolvedOddsPipeline,
)
from tests.integration.test_migrations import alembic_config

_NOW = datetime(2026, 9, 7, 20, 0, tzinfo=UTC)
_START = _NOW + timedelta(hours=22)


@pytest.mark.integration
def test_manual_and_mock_providers_reach_mapping_with_only_resolved_odds_ready(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    clock = FixedClock(UtcInstant(_NOW))
    market_mapping = PostgresMarketMappingService(engine, clock)
    market_mapping.register_rules(_rules())
    pipeline = ResolvedOddsPipeline(
        OddsCaptureService(engine, clock),
        PostgresEventMatchingService(engine, clock),
        market_mapping,
        PostgresResolvedOddsGate(engine),
    )
    manual = _manual_provider("manual-gate", "Canonical League")
    provider_event = manual.list_events(
        _START - timedelta(minutes=1),
        _START + timedelta(minutes=1),
        GameTitle.LEAGUE_OF_LEGENDS,
    )[0]
    canonical_event = _canonical_event("Canonical League")
    source = OddsCaptureSource(
        "manual_import",
        "Manual gate fixture",
        "sha256:map-006-manual-fixture",
    )

    first = pipeline.process(manual, provider_event, source, (canonical_event,))
    history_before = PostgresCanonicalRepository(engine, clock).odds_history(
        canonical_event.event_id
    )
    replay = pipeline.process(manual, provider_event, source, (canonical_event,))
    history_after = PostgresCanonicalRepository(engine, clock).odds_history(
        canonical_event.event_id
    )

    assert first.ready is True
    context = first.require_pricing_ready()
    assert context.canonical_event_id == canonical_event.event_id
    assert context.usable_snapshot_count == 2
    assert context.market_mappings[0].require_mapped().rules_reference == "match-winner-v1"
    assert first.event_mapping.status is EventMappingStatus.AUTO_MATCHED
    assert len(history_before) == len(history_after) == 2
    assert tuple(item.odds_snapshot_id for item in history_after) == tuple(
        item.odds_snapshot_id for item in history_before
    )
    assert replay.capture.inserted_snapshots == 0
    assert replay.capture.duplicate_snapshots == 2

    catalog = build_mock_scenario_catalog("map-006-mock", clock)
    mock = MockOddsProvider(catalog, clock)
    market_mapping.register_rules(
        MarketRulesReference(
            reference="lol-match-winner-v1",
            market_type=MarketType.MATCH_WINNER,
            period=MarketPeriod.SERIES,
            line_required=False,
            unit="winner",
            selection_types=(SelectionType.TEAM_A, SelectionType.TEAM_B),
            remake_policy="void",
            forfeit_policy="settle",
            cancelled_policy="void",
        )
    )
    mock_event = mock.list_events(
        _NOW - timedelta(days=1),
        _NOW + timedelta(days=2),
        GameTitle.LEAGUE_OF_LEGENDS,
    )[0]
    mock_candidate = next(
        scenario.current_event
        for scenario in catalog.scenarios
        if f"mock-event-{scenario.scenario_key.value}" == mock_event.provider_event_id
    )
    mock_result = pipeline.process(
        mock,
        mock_event,
        OddsCaptureSource("mock", "Mock gate fixture", "mock:map-006"),
        (mock_candidate,),
    )

    assert mock_result.event_mapping.status is EventMappingStatus.AUTO_MATCHED
    assert mock_result.market_mappings[0].reason is MarketMappingReason.OUTCOME_STRUCTURE_MISMATCH
    assert mock_result.reason_codes == (ResolvedOddsGateReason.MARKET_MAPPING_UNRESOLVED,)
    with pytest.raises(OddsPricingGateError, match="MARKET_MAPPING_UNRESOLVED"):
        mock_result.require_pricing_ready()
    assert PostgresCanonicalRepository(engine, clock).odds_history(mock_candidate.event_id)
    engine.dispose()


@pytest.mark.integration
def test_ambiguous_event_with_resolved_market_never_reaches_pricing(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    clock = FixedClock(UtcInstant(_NOW))
    market_mapping = PostgresMarketMappingService(engine, clock)
    market_mapping.register_rules(_rules())
    pipeline = ResolvedOddsPipeline(
        OddsCaptureService(engine, clock),
        PostgresEventMatchingService(engine, clock),
        market_mapping,
        PostgresResolvedOddsGate(engine),
    )
    manual = _manual_provider("manual-ambiguous", "Provider League")
    provider_event = manual.list_events(
        _START - timedelta(minutes=1),
        _START + timedelta(minutes=1),
        GameTitle.LEAGUE_OF_LEGENDS,
    )[0]
    canonical_event = _canonical_event("Canonical League")

    result = pipeline.process(
        manual,
        provider_event,
        OddsCaptureSource(
            "manual_import",
            "Ambiguous gate fixture",
            "sha256:map-006-ambiguous-fixture",
        ),
        (canonical_event,),
    )

    assert result.event_mapping.status is EventMappingStatus.REVIEW
    assert all(decision.resolved for decision in result.market_mappings)
    assert result.reason_codes == (ResolvedOddsGateReason.EVENT_MAPPING_UNRESOLVED,)
    with pytest.raises(OddsPricingGateError, match="EVENT_MAPPING_UNRESOLVED"):
        result.require_pricing_ready()
    assert PostgresCanonicalRepository(engine, clock).odds_history(canonical_event.event_id) == ()
    engine.dispose()


def _rules() -> MarketRulesReference:
    return MarketRulesReference(
        reference="match-winner-v1",
        market_type=MarketType.MATCH_WINNER,
        period=MarketPeriod.SERIES,
        line_required=False,
        unit="winner",
        selection_types=(SelectionType.TEAM_A, SelectionType.TEAM_B),
        remake_policy="void",
        forfeit_policy="settle",
        cancelled_policy="void",
    )


def _canonical_event(competition: str) -> Event:
    return Event(
        event_id=uuid4(),
        game_title=GameTitle.LEAGUE_OF_LEGENDS,
        competition=competition,
        team_a_id=uuid4(),
        team_a="Manual Alpha",
        team_b_id=uuid4(),
        team_b="Manual Beta",
        starts_at=_START,
        best_of=3,
        status=EventStatus.SCHEDULED,
        observed_at=_NOW,
    )


def _manual_provider(provider_code: str, competition: str) -> ManualImportOddsProvider:
    provider = ManualImportOddsProvider(provider_code, clock=FixedClock(UtcInstant(_NOW)))
    common: dict[str, object] = {
        "provider": provider_code,
        "provider_event_id": "manual-event",
        "game_title": "lol",
        "competition": competition,
        "participant_a": "Manual Alpha",
        "participant_b": "Manual Beta",
        "starts_at": _START.isoformat(),
        "best_of": 3,
        "event_status": "scheduled",
        "provider_market_id": "manual-market",
        "market_label": "Match Winner",
        "market_type": "MATCH_WINNER",
        "period": "SERIES",
        "line": None,
        "unit": "winner",
        "market_status": "open",
        "captured_at": (_NOW - timedelta(seconds=30)).isoformat(),
        "timestamp_reliable": True,
        "settlement_rules_version": "match-winner-v1",
        "remake_policy": "void",
        "forfeit_policy": "settle",
        "cancelled_policy": "void",
    }
    rows = [
        {
            **common,
            "provider_selection_id": "manual-team-a",
            "selection": "TEAM_A",
            "selection_label": "Manual Alpha",
            "decimal_odds": "1.80",
            "provenance_reference": "manual:map-006:team-a",
        },
        {
            **common,
            "provider_selection_id": "manual-team-b",
            "selection": "TEAM_B",
            "selection_label": "Manual Beta",
            "decimal_odds": "2.10",
            "provenance_reference": "manual:map-006:team-b",
        },
    ]
    result = provider.import_document(
        json.dumps(rows, separators=(",", ":")).encode(),
        document_format="json",
    )
    assert result.committed is True
    return provider
