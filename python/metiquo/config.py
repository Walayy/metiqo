"""Configuration serveur validée à la frontière du processus."""

from datetime import UTC, tzinfo
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    Field,
    SecretStr,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from metiquo.contracts.enums import DataMode as DataMode


class AppEnvironment(StrEnum):
    """Environnements d'exécution acceptés."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class ObjectStoreBackend(StrEnum):
    """Stockages objet prévus par l'architecture."""

    FILESYSTEM = "filesystem"
    S3 = "s3"


class OddsProvider(StrEnum):
    """Providers de cotes activables à ce stade."""

    DISABLED = "disabled"
    MOCK = "mock"


class Settings(BaseSettings):
    """Source de vérité typée de la configuration serveur Metiquo."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
    )

    app_env: AppEnvironment
    app_data_mode: DataMode
    database_url: SecretStr

    object_store_backend: ObjectStoreBackend = ObjectStoreBackend.FILESYSTEM
    object_store_root: Path = Path("/data")
    display_timezone: str = "Europe/Paris"

    oe_allow_stale: bool = True
    oe_require_fresh: bool = False
    oe_current_year: int = Field(default=2026, ge=2014, le=9999)
    oe_freshness_sla_seconds: int = Field(default=10_800, gt=0)
    oe_source_catalog_path: Path = Path("/app/config/oracles_elixir_sources.yml")
    oe_connect_timeout_seconds: float = Field(default=10.0, gt=0)
    oe_read_timeout_seconds: float = Field(default=60.0, gt=0)
    oe_download_timeout_seconds: float = Field(default=900.0, gt=0)
    oe_max_download_bytes: int = Field(default=4 * 1024 * 1024 * 1024, gt=0)
    oe_max_redirects: int = Field(default=3, ge=0, le=10)
    oe_retry_max_attempts: int = Field(default=4, ge=1, le=10)
    oe_retry_base_seconds: float = Field(default=1.0, gt=0)
    oe_retry_max_seconds: float = Field(default=30.0, gt=0)
    oe_google_drive_bearer: SecretStr | None = None

    odds_provider: OddsProvider = OddsProvider.MOCK
    odds_max_age_seconds: int = Field(default=90, gt=0)
    mock_seed: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
    ] = "metiquo-demo-v1"

    signal_min_edge: Decimal = Field(default=Decimal("0.03"), ge=0, le=1)
    signal_min_ev: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    signal_min_conservative_ev: Decimal = Field(default=Decimal("0.00"), ge=0, le=1)
    signal_max_kelly_fraction: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    signal_min_mapping_confidence: Decimal = Field(default=Decimal("0.80"), ge=0, le=1)

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        """Refuser une URL non PostgreSQL ou incomplète sans exposer sa valeur."""

        parsed = urlsplit(value.get_secret_value())
        if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
            raise ValueError("DATABASE_URL doit utiliser PostgreSQL avec le driver psycopg")
        if parsed.hostname is None or parsed.path in {"", "/"}:
            raise ValueError("DATABASE_URL doit préciser un hôte et une base")
        return value

    @field_validator("display_timezone")
    @classmethod
    def validate_display_timezone(cls, value: str) -> str:
        """Valider un identifiant IANA réservé au rendu de l'interface."""

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("DISPLAY_TIMEZONE doit être un fuseau IANA connu") from error
        return value

    @field_validator("oe_google_drive_bearer")
    @classmethod
    def validate_google_drive_bearer(cls, value: SecretStr | None) -> SecretStr | None:
        """Refuser un credential vide tout en conservant sa valeur masquée."""

        if value is not None and not value.get_secret_value().strip():
            raise ValueError("OE_GOOGLE_DRIVE_BEARER ne peut pas être vide")
        return value

    @model_validator(mode="after")
    def validate_modes(self) -> Self:
        """Empêcher les configurations ambiguës et le mélange mock/réel."""

        if self.oe_allow_stale and self.oe_require_fresh:
            raise ValueError(
                "OE_ALLOW_STALE et OE_REQUIRE_FRESH ne peuvent pas être vrais ensemble"
            )
        if self.oe_retry_base_seconds > self.oe_retry_max_seconds:
            raise ValueError("OE_RETRY_BASE_SECONDS ne peut pas dépasser OE_RETRY_MAX_SECONDS")
        if self.app_data_mode is DataMode.REAL and self.odds_provider is OddsProvider.MOCK:
            raise ValueError("APP_DATA_MODE=real interdit ODDS_PROVIDER=mock")
        if self.app_data_mode is DataMode.MOCK and self.odds_provider not in {
            OddsProvider.DISABLED,
            OddsProvider.MOCK,
        }:
            raise ValueError("APP_DATA_MODE=mock interdit tout provider de cotes réel")
        return self

    @property
    def display_tzinfo(self) -> ZoneInfo:
        """Fuseau appliqué exclusivement lors du rendu."""

        return ZoneInfo(self.display_timezone)

    @property
    def internal_tzinfo(self) -> tzinfo:
        """Fuseau invariant pour les instants persistés et calculés."""

        return UTC


class ConfigurationError(RuntimeError):
    """Erreur de démarrage lisible et dépourvue de valeurs sensibles."""


def _format_validation_error(error: ValidationError) -> str:
    problems: list[str] = []
    for detail in error.errors(include_input=False, include_url=False):
        location = ".".join(str(part).upper() for part in detail["loc"])
        problems.append(f"{location}: {detail['msg']}")
    return "; ".join(problems)


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Charger une fois la configuration et échouer avant le démarrage applicatif."""

    try:
        return Settings()
    except ValidationError as error:
        message = _format_validation_error(error)
        raise ConfigurationError(f"Configuration Metiquo invalide : {message}") from None
