"""Fournisseurs explicitement désactivés et observables sans accès externe."""

from datetime import datetime

from metiquo.contracts.enums import GameTitle, ProviderStatus
from metiquo.contracts.odds_provider import (
    OddsCaptureResult,
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
)
from metiquo.foundation.time import Clock, SystemClock


class ProviderDisabledError(RuntimeError):
    """Une opération de collecte a été demandée à un fournisseur désactivé."""


class DisabledProvider:
    """Implémentation sûre du contrat qui ne collecte et ne publie aucune cote."""

    def __init__(self, provider_code: str, reason: str, clock: Clock | None = None) -> None:
        normalized_code = provider_code.strip()
        normalized_reason = reason.strip()
        if not normalized_code:
            raise ValueError("provider_code est obligatoire")
        if not normalized_reason:
            raise ValueError("reason est obligatoire")
        self.provider_code = normalized_code
        self.disabled_reason = normalized_reason
        self._clock = clock or SystemClock()

    def list_events(
        self,
        starts_from: datetime,
        starts_to: datetime,
        game_title: GameTitle,
    ) -> tuple[ProviderEvent, ...]:
        """Retourner une vue vide, sans tenter aucune collecte."""

        del game_title
        if starts_to < starts_from:
            raise ValueError("starts_to doit être postérieur ou égal à starts_from")
        return ()

    def get_event_markets(self, provider_event_id: str) -> tuple[ProviderMarket, ...]:
        """Retourner une vue vide, sans tenter aucune collecte."""

        del provider_event_id
        return ()

    def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult:
        """Refuser explicitement toute collecte."""

        raise ProviderDisabledError(
            f"Le provider {self.provider_code!r} est désactivé : {self.disabled_reason} "
            f"(événement {provider_event_id!r})"
        )

    def health(self) -> ProviderHealth:
        """Ne jamais présenter un fournisseur désactivé comme opérationnel."""

        return ProviderHealth(
            provider_code=self.provider_code,
            status=ProviderStatus.UNAVAILABLE,
            checked_at=self._clock.now().value,
            last_success_at=None,
            detail=self.disabled_reason,
        )
