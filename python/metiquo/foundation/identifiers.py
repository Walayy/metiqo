"""Identifiants opaques séparés par domaine."""

from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class OpaqueId:
    """UUID dont la classe concrète porte le domaine métier."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise TypeError("Un identifiant opaque doit encapsuler un UUID")

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    @classmethod
    def parse(cls, value: str) -> Self:
        try:
            parsed = UUID(value)
        except (AttributeError, ValueError) as error:
            raise ValueError(f"{cls.__name__} invalide") from error
        return cls(parsed)

    def __str__(self) -> str:
        return str(self.value)


class EventId(OpaqueId):
    """Identifiant d'un événement esport."""


class TeamId(OpaqueId):
    """Identifiant d'une équipe canonique."""


class PlayerId(OpaqueId):
    """Identifiant d'un joueur canonique."""


class SnapshotId(OpaqueId):
    """Identifiant d'un snapshot de données."""


class OddsSnapshotId(OpaqueId):
    """Identifiant d'un snapshot de cotes."""


class ModelVersionId(OpaqueId):
    """Identifiant d'une version de modèle."""


class PredictionId(OpaqueId):
    """Identifiant d'une prédiction immuable."""


class SignalId(OpaqueId):
    """Identifiant d'un signal immuable."""


class PaperBetId(OpaqueId):
    """Identifiant d'un pari fictif."""


class JobId(OpaqueId):
    """Identifiant d'un job asynchrone."""


class TraceId(OpaqueId):
    """Identifiant d'une trace distribuée locale."""


class CorrelationId(OpaqueId):
    """Identifiant reliant plusieurs opérations métier."""
