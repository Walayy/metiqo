"""L'absence d'authentification exige une exposition locale ou privée explicite."""

import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from metiquo.api.app import create_app
from metiquo.config import ConfigurationError
from tests.test_config import build_settings


@pytest.mark.parametrize(
    "host", ["0.0.0.0", "::", "8.8.8.8", "169.254.1.2", "100.64.1.2", "private.example"]
)
def test_disabled_auth_rejects_public_wildcard_and_implicit_private_bindings(host: str) -> None:
    with pytest.raises(ValidationError, match="APP_PUBLISH_HOST"):
        build_settings(auth_mode="disabled", app_publish_host=host)


@pytest.mark.parametrize(
    "origin", ["https://metiquo.example", "https://8.8.8.8", "http://192.168.1.5:3000"]
)
def test_disabled_auth_also_checks_browser_origin(origin: str) -> None:
    with pytest.raises(ValidationError, match="APP_PUBLIC_ORIGIN"):
        build_settings(auth_mode="disabled", app_public_origin=origin)


def test_private_network_must_be_explicit_and_exclude_public_ranges() -> None:
    settings = build_settings(
        auth_mode="disabled",
        app_publish_host="192.168.10.4",
        app_public_origin="http://192.168.10.4:3000",
        auth_private_networks=["192.168.10.0/24"],
    )
    assert settings.auth_mode.value == "disabled"
    for network in ("0.0.0.0/0", "::/0", "8.8.8.0/24", "169.254.0.0/16"):
        with pytest.raises(ValidationError, match="AUTH_PRIVATE_NETWORKS"):
            build_settings(auth_private_networks=[network])


def test_loopback_defaults_and_ipv6_are_allowed() -> None:
    assert build_settings().auth_mode.value == "disabled"
    assert build_settings(app_publish_host="::1", app_public_origin="http://[::1]:3000")


def test_api_revalidates_injected_settings_and_owner_mode_fails_closed() -> None:
    # Les doubles injectés ne doivent pas permettre de contourner le garde de démarrage.
    copied = build_settings().model_copy(update={"app_publish_host": "0.0.0.0"})
    with pytest.raises(ValueError, match="APP_PUBLISH_HOST"):
        create_app(settings=copied)
    owner = build_settings(
        auth_mode="owner", app_publish_host="0.0.0.0", app_public_origin="https://metiquo.example"
    )
    with pytest.raises(ConfigurationError, match="AUTH_OWNER_UNAVAILABLE"):
        create_app(settings=owner)


def test_real_uvicorn_startup_refuses_public_disabled_auth() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "metiquo.api.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
        ],
        env={
            **os.environ,
            "APP_ENV": "test",
            "APP_DATA_MODE": "mock",
            "ODDS_PROVIDER": "mock",
            "AUTH_MODE": "disabled",
            "APP_PUBLISH_HOST": "0.0.0.0",
            "APP_PUBLIC_ORIGIN": "http://localhost:3000",
            "AUTH_PRIVATE_NETWORKS": "[]",
            "DATABASE_URL": "postgresql+psycopg://metiquo@127.0.0.1:1/metiquo",
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "APP_PUBLISH_HOST" in result.stderr
    assert "Application startup complete" not in result.stderr
