"""Preuves de désactivation et de conformité du squelette Stake."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from infra.scripts.check_provider_compliance import scan_provider_compliance
from pydantic import ValidationError

from metiquo.config import Settings
from metiquo.contracts.enums import GameTitle, ProviderStatus
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.providers import (
    STAKE_DISABLED_REASON,
    OddsProvider,
    ProviderDisabledError,
    StakeAuthorizedProvider,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 7, 16, 0, tzinfo=UTC)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "app_data_mode": "real",
        "database_url": "postgresql+psycopg://metiqo@postgres:5432/metiqo",
        "odds_provider": "disabled",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_stake_provider_is_disabled_by_default_at_startup() -> None:
    settings = _settings()

    assert settings.stake_provider_enabled is False
    assert settings.stake_written_authorization_confirmed is False
    assert settings.stake_lawful_jurisdiction_confirmed is False
    assert settings.stake_legal_validation_confirmed is False


def test_startup_rejects_enablement_without_every_compliance_gate() -> None:
    with pytest.raises(ValidationError, match="STAKE_WRITTEN_AUTHORIZATION_CONFIRMED"):
        _settings(stake_provider_enabled=True)


def test_startup_still_rejects_enablement_without_an_authorized_implementation() -> None:
    with pytest.raises(ValidationError, match="aucune implémentation autorisée"):
        _settings(
            stake_provider_enabled=True,
            stake_written_authorization_confirmed=True,
            stake_lawful_jurisdiction_confirmed=True,
            stake_legal_validation_confirmed=True,
        )


def test_disabled_provider_satisfies_the_boundary_without_collecting_data() -> None:
    provider = StakeAuthorizedProvider(FixedClock(UtcInstant(NOW)))

    assert isinstance(provider, OddsProvider)
    assert provider.list_events(NOW, NOW, GameTitle.LEAGUE_OF_LEGENDS) == ()
    assert provider.get_event_markets("event") == ()
    with pytest.raises(ProviderDisabledError, match="autorisation écrite"):
        provider.capture_snapshot("event")

    health = provider.health()
    assert health.status is ProviderStatus.UNAVAILABLE
    assert health.checked_at == NOW
    assert health.last_success_at is None
    assert health.detail == STAKE_DISABLED_REASON


def test_disabled_provider_rejects_an_inverted_window() -> None:
    provider = StakeAuthorizedProvider(FixedClock(UtcInstant(NOW)))

    with pytest.raises(ValueError, match="starts_to"):
        provider.list_events(
            datetime(2026, 9, 8, tzinfo=UTC),
            NOW,
            GameTitle.LEAGUE_OF_LEGENDS,
        )


def test_repository_compliance_scan_blocks_documented_circumvention_patterns(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "python" / "metiquo"
    source_root.mkdir(parents=True)
    (source_root / "unsafe.py").write_text(
        'provider_url = "https://example.stake.com/private"\n'
        'tool = "captcha_solver"\n'
        'network = "residential_proxy"\n'
        'action = "place_bet"\n',
        encoding="utf-8",
    )

    violations = scan_provider_compliance(tmp_path)

    assert {violation.rule for violation in violations} == {
        "automatisation de mise",
        "endpoint Stake",
        "proxy résidentiel",
        "solveur CAPTCHA",
    }


def test_repository_compliance_scan_is_clean_and_wired_into_ci() -> None:
    assert scan_provider_compliance(ROOT) == ()
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "infra/scripts/check_provider_compliance.py" in makefile
    assert "make check" in workflow
