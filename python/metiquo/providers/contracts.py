"""Port fournisseur de cotes indépendant de tout adaptateur concret."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from metiquo.contracts.enums import GameTitle
from metiquo.contracts.odds_provider import (
    OddsCaptureResult,
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
)


@runtime_checkable
class OddsProvider(Protocol):
    """Surface commune que chaque fournisseur autorisé doit implémenter."""

    provider_code: str

    def list_events(
        self,
        starts_from: datetime,
        starts_to: datetime,
        game_title: GameTitle,
    ) -> tuple[ProviderEvent, ...]:
        """Lister les événements de la fenêtre dans le vocabulaire commun."""

        ...

    def get_event_markets(self, provider_event_id: str) -> tuple[ProviderMarket, ...]:
        """Retourner les marchés connus, ou un tuple vide pour un événement absent."""

        ...

    def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult:
        """Capturer l'événement ou lever LookupError lorsque son identité est inconnue."""

        ...

    def health(self) -> ProviderHealth:
        """Exposer un état sanitaire sans secret de configuration."""

        ...
