"""Preuves de la frontière du futur flux licencié."""

from datetime import datetime
from inspect import isabstract
from pathlib import Path

import pytest

from metiquo.contracts.enums import GameTitle
from metiquo.contracts.odds_provider import (
    OddsCaptureResult,
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
)
from metiquo.providers import (
    LicensedFeedActivationError,
    LicensedOddsFeedConfiguration,
    LicensedOddsFeedProvider,
    OddsProvider,
)


class _ContractSkeleton(LicensedOddsFeedProvider):
    """Squelette de test : il ne réalise aucun accès externe."""

    def list_events(
        self,
        starts_from: datetime,
        starts_to: datetime,
        game_title: GameTitle,
    ) -> tuple[ProviderEvent, ...]:
        return ()

    def get_event_markets(self, provider_event_id: str) -> tuple[ProviderMarket, ...]:
        return ()

    def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult:
        raise LookupError(provider_event_id)

    def health(self) -> ProviderHealth:
        raise NotImplementedError


def test_configuration_is_normalized_and_contains_only_non_secret_metadata() -> None:
    configuration = LicensedOddsFeedConfiguration(
        provider_code="  licensed-example  ",
        agreement_reference="  agreement-internal-reference  ",
        rights_confirmed=True,
    )

    assert configuration.provider_code == "licensed-example"
    assert configuration.agreement_reference == "agreement-internal-reference"
    assert configuration.rights_confirmed is True
    assert set(configuration.__dataclass_fields__) == {
        "provider_code",
        "agreement_reference",
        "rights_confirmed",
    }


@pytest.mark.parametrize(
    ("provider_code", "agreement_reference", "message"),
    [
        ("Licensed Example", "agreement", "provider_code"),
        ("licensed-example", "   ", "agreement_reference"),
        ("licensed-example", "x" * 257, "256"),
    ],
)
def test_configuration_rejects_ambiguous_identity(
    provider_code: str, agreement_reference: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        LicensedOddsFeedConfiguration(provider_code, agreement_reference)


def test_adapter_cannot_activate_without_confirmed_rights() -> None:
    configuration = LicensedOddsFeedConfiguration(
        provider_code="licensed-example",
        agreement_reference="agreement-internal-reference",
    )

    with pytest.raises(LicensedFeedActivationError, match="droits contractuels"):
        _ContractSkeleton(configuration)


def test_complete_future_adapter_is_structurally_an_odds_provider() -> None:
    provider = _ContractSkeleton(
        LicensedOddsFeedConfiguration(
            provider_code="licensed-example",
            agreement_reference="agreement-internal-reference",
            rights_confirmed=True,
        )
    )

    assert isabstract(LicensedOddsFeedProvider)
    assert LicensedOddsFeedProvider.__abstractmethods__ == {
        "capture_snapshot",
        "get_event_markets",
        "health",
        "list_events",
    }
    assert isinstance(provider, OddsProvider)
    assert provider.provider_code == "licensed-example"


def test_production_boundary_defines_no_vendor_transport_or_authentication_value() -> None:
    source_path = (
        Path(__file__).resolve().parents[2]
        / "python"
        / "metiquo"
        / "providers"
        / "licensed_feed.py"
    )
    source = source_path.read_text(encoding="utf-8").casefold()

    assert "http://" not in source
    assert "https://" not in source
    assert "api_key =" not in source
    assert "token =" not in source
    assert "password =" not in source
