"""Configuration serveur validée à la frontière du processus."""

import json
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
from metiquo.contracts.enums import MarketType, OddsPhase
from metiquo.foundation.network_boundary import (
    allowed_without_auth,
    literal_address,
    origin_host,
    private_networks,
)

type PositiveSeconds = Annotated[int, Field(gt=0)]


class AppEnvironment(StrEnum):
    """Environnements d'exécution acceptés."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    DISABLED = "disabled"
    OWNER = "owner"


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
        hide_input_in_errors=True,
    )

    app_env: AppEnvironment
    app_data_mode: DataMode
    database_url: SecretStr
    database_url_file: Path | None = Field(default=None, repr=False, exclude=True)
    oe_google_drive_bearer_file: Path | None = Field(default=None, repr=False, exclude=True)
    auth_mode: AuthMode = AuthMode.DISABLED
    app_publish_host: str = "127.0.0.1"
    app_public_origin: str = "http://localhost:3000"
    auth_private_networks: tuple[str, ...] = ()
    auth_session_idle_seconds: int = Field(default=1800, ge=60, le=86400)
    auth_session_absolute_seconds: int = Field(default=43200, ge=300, le=604800)
    auth_session_rotation_seconds: int = Field(default=900, ge=60, le=86400)
    auth_session_grace_seconds: int = Field(default=10, ge=0, le=30)

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
    worker_scheduler_enabled: bool = True
    worker_scheduler_tick_seconds: int = Field(default=15, ge=1, le=300)
    worker_retry_delays_seconds: tuple[int, ...] = (600, 1800, 7200)
    worker_retry_jitter_fraction: float = Field(default=0.1, ge=0, le=0.5)
    oe_sync_interval_seconds: int = Field(default=10800, ge=60)
    oe_closed_audit_months: int = Field(default=1, ge=1, le=12)
    oe_deep_check_interval_seconds: int = Field(default=86400, ge=60)
    paper_settlement_interval_seconds: int = Field(default=300, ge=60)
    paper_report_interval_seconds: int = Field(default=300, ge=60)
    model_freshness_sla_seconds: int = Field(default=2592000, gt=0)
    alert_interval_seconds: int = Field(default=300, ge=60)
    alert_cooldown_seconds: int = Field(default=21600, ge=60)
    alert_mapping_backlog_limit: int = Field(default=10, ge=1)
    backup_enabled: bool = True
    backup_root: Path | None = None
    backup_interval_seconds: int = Field(default=86400, ge=3600)
    backup_freshness_sla_seconds: int = Field(default=129600, ge=3600)
    backup_retention_count: int = Field(default=7, ge=1, le=3650)
    backup_timeout_seconds: int = Field(default=3600, ge=1, le=86400)
    backup_external: bool = False
    backup_age_recipient: str | None = None
    backup_age_binary: str = "age"
    backup_pg_dump_binary: str = "pg_dump"
    backup_pg_restore_binary: str = "pg_restore"

    odds_provider: OddsProvider = OddsProvider.MOCK
    odds_max_age_seconds: int = Field(default=90, gt=0)
    odds_provider_max_age_seconds: dict[str, PositiveSeconds] = Field(default_factory=dict)
    odds_market_max_age_seconds: dict[MarketType, PositiveSeconds] = Field(default_factory=dict)
    odds_phase_max_age_seconds: dict[OddsPhase, PositiveSeconds] = Field(default_factory=dict)
    mock_seed: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
    ] = "metiquo-demo-v1"
    stake_provider_enabled: bool = False
    stake_written_authorization_confirmed: bool = False
    stake_lawful_jurisdiction_confirmed: bool = False
    stake_legal_validation_confirmed: bool = False

    signal_min_edge: Decimal = Field(default=Decimal("0.03"), ge=0, le=1)
    signal_min_ev: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    signal_min_conservative_ev: Decimal = Field(default=Decimal("0.00"), ge=0, le=1)
    signal_max_kelly_fraction: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    signal_min_mapping_confidence: Decimal = Field(default=Decimal("0.80"), ge=0, le=1)

    paper_bankroll_policy_version: str = Field(
        default="paper-manual-v1", min_length=1, max_length=128
    )
    paper_bankroll_currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    paper_bankroll_initial: Decimal = Field(default=Decimal(1000), gt=0, allow_inf_nan=False)
    paper_max_open_exposure: Decimal = Field(default=Decimal(100), gt=0, allow_inf_nan=False)
    paper_settlement_delay_seconds: int = Field(default=300, ge=0)
    paper_settlement_max_attempts: int = Field(default=3, ge=1, le=5)
    paper_closing_max_age_seconds: int = Field(default=90, gt=0)

    @model_validator(mode="before")
    @classmethod
    def read_server_secret_files(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        values = dict(value)
        for name in ("database_url", "oe_google_drive_bearer"):
            file_name = f"{name}_file"
            file_value = values.get(file_name)
            if not file_value:
                continue
            if values.get(name):
                raise ValueError(
                    f"{name.upper()} et {file_name.upper()} sont mutuellement exclusifs"
                )
            try:
                path = Path(file_value)
                if not path.is_absolute() or not path.is_file() or path.stat().st_size > 16384:
                    raise OSError
                content = path.read_text(encoding="utf-8").removesuffix("\n").removesuffix("\r")
                if not content or len(content.encode()) > 16384:
                    raise OSError
            except (OSError, ValueError, TypeError):
                raise ValueError(
                    f"{file_name.upper()} exige un fichier serveur lisible et borné"
                ) from None
            values[name] = SecretStr(content)
        return values

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

    @field_validator("auth_private_networks", mode="before")
    @classmethod
    def parse_private_networks(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_auth_boundary(self) -> Self:
        self.check_auth_boundary()
        return self

    def check_auth_boundary(self) -> None:
        if self.auth_session_rotation_seconds >= self.auth_session_idle_seconds:
            raise ValueError("La rotation de session doit précéder son expiration inactive")
        if self.auth_session_idle_seconds > self.auth_session_absolute_seconds:
            raise ValueError("La durée inactive ne doit pas dépasser la durée absolue")
        networks = private_networks(self.auth_private_networks)
        literal_address(self.app_publish_host)
        host = origin_host(self.app_public_origin)
        if (
            self.auth_mode is AuthMode.OWNER
            and urlsplit(self.app_public_origin).scheme != "https"
            and not (
                allowed_without_auth(host, ()) and allowed_without_auth(self.app_publish_host, ())
            )
        ):
            raise ValueError("AUTH_MODE=owner exige HTTPS hors loopback")
        if self.auth_mode is AuthMode.DISABLED:
            if not allowed_without_auth(self.app_publish_host, networks):
                raise ValueError(
                    "AUTH_MODE=disabled interdit APP_PUBLISH_HOST "
                    "hors loopback ou réseau privé explicite"
                )
            if not allowed_without_auth(host, networks):
                raise ValueError(
                    "AUTH_MODE=disabled interdit APP_PUBLIC_ORIGIN "
                    "hors loopback ou réseau privé explicite"
                )

    @field_validator("worker_retry_delays_seconds", mode="before")
    @classmethod
    def parse_worker_retry_delays(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value

    @field_validator("worker_retry_delays_seconds")
    @classmethod
    def validate_worker_retry_delays(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value or len(value) > 20 or any(not 1 <= item <= 86400 for item in value):
            raise ValueError("Les délais du worker doivent être bornés à 1..86400 secondes")
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

    @field_validator("odds_provider_max_age_seconds")
    @classmethod
    def normalize_odds_provider_age_overrides(
        cls, value: dict[str, PositiveSeconds]
    ) -> dict[str, PositiveSeconds]:
        """Normaliser les codes provider des surcharges de fraîcheur."""

        normalized = {provider.strip(): seconds for provider, seconds in value.items()}
        if len(normalized) != len(value) or any(not provider for provider in normalized):
            raise ValueError(
                "ODDS_PROVIDER_MAX_AGE_SECONDS refuse un code vide ou dupliqué après trim"
            )
        return normalized

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
        if self.stake_provider_enabled:
            required_gates = {
                "STAKE_WRITTEN_AUTHORIZATION_CONFIRMED": (
                    self.stake_written_authorization_confirmed
                ),
                "STAKE_LAWFUL_JURISDICTION_CONFIRMED": (self.stake_lawful_jurisdiction_confirmed),
                "STAKE_LEGAL_VALIDATION_CONFIRMED": self.stake_legal_validation_confirmed,
            }
            missing = [name for name, confirmed in required_gates.items() if not confirmed]
            if missing:
                raise ValueError(
                    "STAKE_PROVIDER_ENABLED exige les gates de conformité : " + ", ".join(missing)
                )
            raise ValueError(
                "STAKE_PROVIDER_ENABLED reste interdit : aucune implémentation autorisée "
                "n'est livrée"
            )
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
