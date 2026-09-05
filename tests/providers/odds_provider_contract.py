"""Suite de contrat réutilisable par chaque implémentation OddsProvider."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from metiquo.contracts.enums import GameTitle
from metiquo.providers import OddsProvider


@dataclass(frozen=True, slots=True)
class OddsProviderContractFixture:
    """Fenêtre déterministe contenant au moins un événement capturable."""

    provider: OddsProvider
    starts_from: datetime
    starts_to: datetime
    game_title: GameTitle = GameTitle.LEAGUE_OF_LEGENDS
    unknown_event_id: str = "contract-unknown-event"


def assert_odds_provider_contract(fixture: OddsProviderContractFixture) -> None:
    """Exécuter les invariants communs sans connaître la classe de l'adaptateur."""

    provider = fixture.provider
    assert isinstance(provider, OddsProvider)
    assert provider.provider_code.strip() == provider.provider_code
    assert provider.provider_code

    events = provider.list_events(
        fixture.starts_from,
        fixture.starts_to,
        fixture.game_title,
    )
    assert isinstance(events, tuple)
    assert events
    assert len({event.provider_event_id for event in events}) == len(events)

    for event in events:
        assert event.game_title is fixture.game_title
        assert fixture.starts_from <= event.starts_at <= fixture.starts_to
        assert len({participant.casefold() for participant in event.participants}) == len(
            event.participants
        )
        markets = provider.get_event_markets(event.provider_event_id)
        assert isinstance(markets, tuple)
        assert markets
        assert len({market.provider_market_id for market in markets}) == len(markets)
        assert all(market.provider_event_id == event.provider_event_id for market in markets)
        for market in markets:
            assert len({selection.provider_selection_id for selection in market.selections}) == len(
                market.selections
            )
            assert len({selection.selection for selection in market.selections}) == len(
                market.selections
            )
            assert all(selection.decimal_odds >= 1 for selection in market.selections)

        capture = provider.capture_snapshot(event.provider_event_id)
        assert capture.provider_event_id == event.provider_event_id
        assert capture.snapshots
        assert all(snapshot.provider == provider.provider_code for snapshot in capture.snapshots)
        assert all(snapshot.captured_at <= capture.captured_at for snapshot in capture.snapshots)

    health = provider.health()
    assert health.provider_code == provider.provider_code
    assert health.last_success_at is None or health.last_success_at <= health.checked_at

    assert provider.get_event_markets(fixture.unknown_event_id) == ()
    with pytest.raises(LookupError):
        provider.capture_snapshot(fixture.unknown_event_id)
    with pytest.raises(ValueError):
        provider.list_events(
            fixture.starts_to,
            fixture.starts_from - timedelta(microseconds=1),
            fixture.game_title,
        )
