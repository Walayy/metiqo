"""Frontière obligatoire entre données mock et données réelles."""

from dataclasses import dataclass
from enum import StrEnum

from metiquo.contracts.enums import DataMode
from metiquo.db.schemas import MOCK_SCHEMA


class DataModeViolation(RuntimeError):
    """Accès refusé parce qu'il franchirait la frontière de mode."""


class LogicalSchema(StrEnum):
    """Namespaces métier utilisables par les repositories réels."""

    RAW = "raw"
    CORE = "core"
    ODDS = "odds"
    FEATURES = "features"
    ML = "ml"
    SIGNALS = "signals"
    OPS = "ops"


class ExternalDataSource(StrEnum):
    """Sources réseau qui doivent être bloquées en mode mock."""

    ORACLES_ELIXIR = "oracles_elixir"
    ODDS_PROVIDER = "odds_provider"


@dataclass(frozen=True, slots=True)
class DataAccessBoundary:
    """Résout le namespace et autorise les effets selon un mode unique."""

    data_mode: DataMode

    def __post_init__(self) -> None:
        if not isinstance(self.data_mode, DataMode):
            raise TypeError("DataAccessBoundary exige un DataMode canonique")

    def physical_schema(self, logical_schema: LogicalSchema) -> str:
        """Router tous les domaines mock vers leur namespace isolé."""

        if self.data_mode is DataMode.MOCK:
            return MOCK_SCHEMA
        return logical_schema.value

    def schema_translate_map(self) -> dict[str, str]:
        """Fournir une traduction SQLAlchemy neuve et non partageable."""

        return {schema.value: self.physical_schema(schema) for schema in LogicalSchema}

    def require_payload_mode(self, payload_mode: DataMode) -> None:
        """Refuser une lecture ou écriture portant l'autre mode."""

        if payload_mode is not self.data_mode:
            raise DataModeViolation(
                f"Le contexte {self.data_mode.value} refuse les données {payload_mode.value}"
            )

    def require_external_access(self, source: ExternalDataSource) -> None:
        """Interdire toute requête Oracle ou bookmaker depuis le mode mock."""

        if self.data_mode is DataMode.MOCK:
            raise DataModeViolation(f"Le mode mock interdit tout accès externe à {source.value}")
