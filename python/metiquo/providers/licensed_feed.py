"""Frontière abstraite pour un futur flux de cotes contractuellement autorisé."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from metiquo.contracts.enums import GameTitle
from metiquo.contracts.odds_provider import (
    OddsCaptureResult,
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
)

_PROVIDER_CODE_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


class LicensedFeedActivationError(RuntimeError):
    """Le flux ne dispose pas des preuves nécessaires à son activation."""


@dataclass(frozen=True, slots=True)
class LicensedOddsFeedConfiguration:
    """Métadonnées non secrètes exigées avant de brancher un adaptateur licencié."""

    provider_code: str
    agreement_reference: str
    rights_confirmed: bool = False

    def __post_init__(self) -> None:
        provider_code = self.provider_code.strip()
        agreement_reference = self.agreement_reference.strip()
        if not _PROVIDER_CODE_PATTERN.fullmatch(provider_code):
            raise ValueError("provider_code doit contenir 1 à 64 caractères parmi a-z, 0-9, _ et -")
        if not agreement_reference:
            raise ValueError("agreement_reference est obligatoire")
        if len(agreement_reference) > 256:
            raise ValueError("agreement_reference ne peut pas dépasser 256 caractères")
        object.__setattr__(self, "provider_code", provider_code)
        object.__setattr__(self, "agreement_reference", agreement_reference)

    def assert_activatable(self) -> None:
        """Refuser un branchement qui ne confirme pas explicitement les droits d'usage."""

        if not self.rights_confirmed:
            raise LicensedFeedActivationError(
                "Le flux licencié exige une confirmation explicite des droits contractuels"
            )


class LicensedOddsFeedProvider(ABC):
    """Base d'adaptateur sans transport, endpoint ni credential présupposé."""

    def __init__(self, configuration: LicensedOddsFeedConfiguration) -> None:
        configuration.assert_activatable()
        self._configuration = configuration

    @property
    def provider_code(self) -> str:
        """Identité logique stable du fournisseur licencié."""

        return self._configuration.provider_code

    @property
    def configuration(self) -> LicensedOddsFeedConfiguration:
        """Retourner uniquement les métadonnées non secrètes de l'adaptateur."""

        return self._configuration

    @abstractmethod
    def list_events(
        self,
        starts_from: datetime,
        starts_to: datetime,
        game_title: GameTitle,
    ) -> tuple[ProviderEvent, ...]:
        """Normaliser les événements autorisés dans le contrat commun."""

    @abstractmethod
    def get_event_markets(self, provider_event_id: str) -> tuple[ProviderMarket, ...]:
        """Normaliser les marchés autorisés dans le contrat commun."""

    @abstractmethod
    def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult:
        """Produire des snapshots immuables accompagnés de leur provenance."""

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Exposer la santé du flux sans révéler sa configuration sensible."""
