"""Preuve autonome du contrat fournisseur de cotes."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from metiquo.contracts import OddsCaptureResult, OddsSnapshot
from metiquo.contracts.enums import (
    EventStatus,
    GameTitle,
    MarketPeriod,
    MarketStatus,
    MarketType,
    ProviderStatus,
    SelectionType,
)
from metiquo.contracts.odds_provider import (
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
    ProviderSelection,
)
from tests.providers.odds_provider_contract import (
    OddsProviderContractFixture,
    assert_odds_provider_contract,
)

_NOW = datetime(2026, 9, 7, 16, 0, tzinfo=UTC)
_STARTS_AT = datetime(2026, 9, 8, 18, 0, tzinfo=UTC)
_EVENT_ID = UUID("11111111-1111-4111-8111-111111111111")
_MARKET_ID = UUID("22222222-2222-4222-8222-222222222222")


class _ReferenceOddsProvider:
    """Implémentation minimale servant uniquement à éprouver la suite commune."""

    provider_code = "reference-provider"

    def list_events(
        self,
        starts_from: datetime,
        starts_to: datetime,
        game_title: GameTitle,
    ) -> tuple[ProviderEvent, ...]:
        if starts_to < starts_from:
            raise ValueError("fenêtre inversée")
        if game_title is not GameTitle.LEAGUE_OF_LEGENDS:
            return ()
        event = ProviderEvent(
            provider_event_id="reference-event",
            game_title=game_title,
            competition="Reference League",
            participants=("Team Alpha", "Team Beta"),
            starts_at=_STARTS_AT,
            best_of=3,
            status=EventStatus.SCHEDULED,
            collected_at=_NOW,
            source_reference="reference:event:v1",
        )
        return (event,) if starts_from <= event.starts_at <= starts_to else ()

    def get_event_markets(self, provider_event_id: str) -> tuple[ProviderMarket, ...]:
        if provider_event_id != "reference-event":
            return ()
        return (
            ProviderMarket(
                provider_event_id=provider_event_id,
                provider_market_id="reference-market",
                raw_label="Match Winner",
                market_type=MarketType.MATCH_WINNER,
                period=MarketPeriod.SERIES,
                unit="winner",
                selections=(
                    ProviderSelection(
                        provider_selection_id="reference-team-a",
                        selection=SelectionType.TEAM_A,
                        label="Team Alpha",
                        decimal_odds=Decimal("1.80"),
                    ),
                    ProviderSelection(
                        provider_selection_id="reference-team-b",
                        selection=SelectionType.TEAM_B,
                        label="Team Beta",
                        decimal_odds=Decimal("2.10"),
                    ),
                ),
                status=MarketStatus.OPEN,
                remake_policy="void",
                forfeit_policy="settle",
                cancelled_policy="void",
                captured_at=_NOW,
                settlement_rules_version="match-winner-v1",
            ),
        )

    def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult:
        if provider_event_id != "reference-event":
            raise LookupError(provider_event_id)
        snapshots = tuple(
            OddsSnapshot(
                odds_snapshot_id=UUID(snapshot_id),
                event_id=_EVENT_ID,
                market_id=_MARKET_ID,
                selection=selection,
                provider=self.provider_code,
                provider_status=ProviderStatus.OPERATIONAL,
                market_status=MarketStatus.OPEN,
                decimal_odds=odds,
                captured_at=_NOW,
                age_seconds=0,
                raw_implied_probability=probability,
                no_vig_probability=None,
                provenance_reference=f"reference:{selection.value}:v1",
            )
            for snapshot_id, selection, odds, probability in (
                (
                    "33333333-3333-4333-8333-333333333333",
                    SelectionType.TEAM_A,
                    Decimal("1.80"),
                    Decimal("0.55555556"),
                ),
                (
                    "44444444-4444-4444-8444-444444444444",
                    SelectionType.TEAM_B,
                    Decimal("2.10"),
                    Decimal("0.47619048"),
                ),
            )
        )
        return OddsCaptureResult(
            provider_event_id=provider_event_id,
            captured_at=_NOW,
            snapshots=snapshots,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider_code=self.provider_code,
            status=ProviderStatus.OPERATIONAL,
            checked_at=_NOW,
            last_success_at=_NOW,
        )


def test_reference_adapter_passes_the_reusable_provider_suite() -> None:
    assert_odds_provider_contract(
        OddsProviderContractFixture(
            provider=_ReferenceOddsProvider(),
            starts_from=datetime(2026, 9, 8, tzinfo=UTC),
            starts_to=datetime(2026, 9, 9, tzinfo=UTC),
        )
    )


def test_normalized_event_rejects_duplicate_participants() -> None:
    with pytest.raises(ValidationError, match="participants fournisseur doivent être distincts"):
        ProviderEvent(
            provider_event_id="duplicate-participants",
            game_title=GameTitle.LEAGUE_OF_LEGENDS,
            competition="Reference League",
            participants=("Team Alpha", " TEAM ALPHA "),
            starts_at=_STARTS_AT,
            status=EventStatus.SCHEDULED,
            collected_at=_NOW,
            source_reference="reference:event:v1",
        )


def test_normalized_market_rejects_duplicate_selection_identity() -> None:
    selection = ProviderSelection(
        provider_selection_id="same-selection",
        selection=SelectionType.TEAM_A,
        label="Team Alpha",
        decimal_odds=Decimal("1.80"),
    )
    with pytest.raises(ValidationError, match="sélections fournisseur doivent être distinctes"):
        ProviderMarket(
            provider_event_id="reference-event",
            provider_market_id="duplicate-market",
            raw_label="Match Winner",
            market_type=MarketType.MATCH_WINNER,
            period=MarketPeriod.SERIES,
            unit="winner",
            selections=(selection, selection),
            status=MarketStatus.OPEN,
            remake_policy="void",
            forfeit_policy="settle",
            cancelled_policy="void",
            captured_at=_NOW,
            settlement_rules_version="match-winner-v1",
        )


def test_contract_boundary_has_no_concrete_provider_dependency() -> None:
    root = Path(__file__).resolve().parents[2] / "python" / "metiquo"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            root / "contracts" / "odds_provider.py",
            root / "providers" / "contracts.py",
        )
    ).casefold()

    assert "repositories.mock" not in source
    assert "manualimportoddsprovider" not in source
    assert "licensedoddsfeedprovider" not in source
