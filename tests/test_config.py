"""Tests de la frontière de configuration serveur."""

from datetime import UTC
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from pydantic import ValidationError

from metiquo.config import (
    AppEnvironment,
    ConfigurationError,
    DataMode,
    OddsProvider,
    Settings,
    load_settings,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ENV = ROOT / ".env.example"


def build_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "app_data_mode": "mock",
        "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
        "odds_provider": "mock",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_valid_configuration_is_typed_and_uses_utc_internally() -> None:
    settings = build_settings()

    assert settings.app_env is AppEnvironment.TEST
    assert settings.app_data_mode is DataMode.MOCK
    assert settings.odds_provider is OddsProvider.MOCK
    assert settings.mock_seed == "metiquo-demo-v1"
    assert settings.display_tzinfo.key == "Europe/Paris"
    assert settings.internal_tzinfo is UTC


@pytest.mark.parametrize(
    ("overrides", "expected_message"),
    [
        ({"odds_max_age_seconds": 0}, "greater than 0"),
        ({"database_url": "sqlite:///metiquo.db"}, "doit utiliser PostgreSQL"),
        ({"display_timezone": "Paris"}, "fuseau IANA connu"),
        ({"mock_seed": "   "}, "at least 1 character"),
        ({"oe_allow_stale": True, "oe_require_fresh": True}, "ne peuvent pas être vrais"),
        (
            {"app_data_mode": "real", "odds_provider": "mock"},
            "APP_DATA_MODE=real interdit ODDS_PROVIDER=mock",
        ),
    ],
)
def test_invalid_configuration_is_rejected(
    overrides: dict[str, object], expected_message: str
) -> None:
    with pytest.raises(ValidationError, match=expected_message):
        build_settings(**overrides)


def test_database_url_is_redacted() -> None:
    password = "credential-that-must-not-leak"
    settings = build_settings(
        database_url=f"postgresql+psycopg://metiquo:{password}@postgres:5432/metiquo"
    )

    assert password not in repr(settings)
    assert "**********" in repr(settings)


def test_mock_seed_is_normalized_at_the_configuration_boundary() -> None:
    assert build_settings(mock_seed="  stable-seed  ").mock_seed == "stable-seed"


def test_startup_error_names_invalid_variable_without_its_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_value = "not-a-number-that-must-not-leak"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_DATA_MODE", "mock")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://metiquo@postgres:5432/metiquo")
    monkeypatch.setenv("ODDS_MAX_AGE_SECONDS", invalid_value)
    load_settings.cache_clear()

    with pytest.raises(ConfigurationError) as captured:
        load_settings()

    assert "ODDS_MAX_AGE_SECONDS" in str(captured.value)
    assert invalid_value not in str(captured.value)
    load_settings.cache_clear()


def test_env_example_is_valid_and_contains_no_secret() -> None:
    text = EXAMPLE_ENV.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "password" not in lowered
    assert "secret" not in lowered
    assert "token" not in lowered

    database_line = next(line for line in text.splitlines() if line.startswith("DATABASE_URL="))
    database_url = database_line.partition("=")[2]
    assert urlsplit(database_url).password is None

    values = {
        line.partition("=")[0].lower(): line.partition("=")[2]
        for line in text.splitlines()
        if line and not line.startswith("#")
    }
    settings = Settings.model_validate(values)
    assert settings.app_env is AppEnvironment.DEVELOPMENT
