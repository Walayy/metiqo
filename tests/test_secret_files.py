"""Secrets montés, erreurs expurgées et absence de secret dans les valeurs publiques."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from metiquo.config import Settings, load_settings


def test_server_credentials_can_be_loaded_from_files(tmp_path: Path) -> None:
    database_file = tmp_path / "database_url"
    bearer_file = tmp_path / "drive_bearer"
    database_file.write_text(
        "postgresql+psycopg://metiquo:fixture-private-credential@postgres:5432/metiquo\n",
        encoding="utf-8",
    )
    bearer_file.write_text("fixture-private-drive-bearer\n", encoding="utf-8")
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "mock",
            "odds_provider": "mock",
            "database_url_file": database_file,
            "oe_google_drive_bearer_file": bearer_file,
        }
    )
    assert settings.database_url.get_secret_value().endswith("@postgres:5432/metiquo")
    assert settings.oe_google_drive_bearer is not None
    assert settings.oe_google_drive_bearer.get_secret_value() == "fixture-private-drive-bearer"
    assert "fixture-private" not in repr(settings) + settings.model_dump_json()
    for contents in ("", "invalid-fixture-private-database-url", "x" * 16385):
        database_file.write_text(contents, encoding="utf-8")
        with pytest.raises(ValidationError) as captured:
            Settings.model_validate(
                {
                    "app_env": "test",
                    "app_data_mode": "mock",
                    "database_url_file": database_file,
                }
            )
        assert "invalid-fixture-private" not in str(captured.value)


def test_ambiguous_and_missing_secret_files_fail_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    values = {"app_env": "test", "app_data_mode": "mock", "database_url_file": missing}
    with pytest.raises(ValidationError, match="fichier"):
        Settings.model_validate(values)
    with pytest.raises(ValidationError, match="mutuellement exclusifs"):
        Settings.model_validate(
            {
                **values,
                "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            }
        )


def test_environment_file_convention_works_without_plaintext_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mounted = tmp_path / "database_url"
    mounted.write_text("postgresql+psycopg://metiquo@postgres:5432/metiquo", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_DATA_MODE", "mock")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL_FILE", str(mounted))
    load_settings.cache_clear()
    try:
        assert load_settings().database_url.get_secret_value().endswith("/metiquo")
    finally:
        load_settings.cache_clear()
