"""Les décisions manuelles ne sont jamais remplacées par un simple flag GO."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from infra.scripts.check_provider_compliance import scan_provider_compliance
from pydantic import ValidationError

from metiquo.api.app import create_app
from metiquo.api.readiness import ReadinessCheck
from metiquo.foundation.release_compliance import verify_release
from tests.api.test_api import StubReadinessProbe, get
from tests.test_config import build_settings


def evidence(tmp_path: Path) -> Path:
    now = datetime.now(UTC)
    proof = tmp_path / "synthetic-test-proof.txt"
    proof.write_text("Synthetic permission fixture; no actual authorization.")
    review = {
        "approvedBy": "Test reviewer",
        "reviewedAt": (now - timedelta(hours=1)).isoformat(),
        "expiresAt": (now + timedelta(days=1)).isoformat(),
        "scope": ["public", "commercial"],
        "proof": proof.name,
        "sha256": hashlib.sha256(proof.read_bytes()).hexdigest(),
    }
    path = tmp_path / "release.json"
    path.write_text(json.dumps({"OE-COMMERCIAL": review, "RIOT-PRODUCT": review}))
    return path


def test_personal_build_defaults_to_no_go_and_disabled_stake() -> None:
    settings = build_settings(app_env="production")
    assert settings.release_audience == "personal"
    assert settings.oe_commercial_gate == settings.riot_product_gate == "NO-GO"
    assert not settings.stake_provider_enabled


@pytest.mark.parametrize("audience", ["public", "commercial"])
def test_public_release_fails_without_manual_evidence(audience: str) -> None:
    with pytest.raises(ValidationError, match="NO-GO"):
        build_settings(release_audience=audience)
    with pytest.raises(ValidationError, match="preuve"):
        build_settings(release_audience=audience, oe_commercial_gate="GO", riot_product_gate="GO")


def test_go_requires_complete_scoped_current_untampered_evidence(tmp_path: Path) -> None:
    path = evidence(tmp_path)
    overrides = dict(
        release_audience="commercial",
        oe_commercial_gate="GO",
        riot_product_gate="GO",
        release_evidence_file=path,
    )
    assert build_settings(**overrides).release_audience == "commercial"
    original = json.loads(path.read_text())
    for field, value in [
        ("expiresAt", "2000-01-01T00:00:00Z"),
        ("reviewedAt", "2099-01-01T00:00:00Z"),
        ("approvedBy", " "),
        ("scope", ["public"]),
        ("sha256", "0" * 64),
        ("proof", "../missing.txt"),
    ]:
        altered = json.loads(json.dumps(original))
        altered["OE-COMMERCIAL"][field] = value
        path.write_text(json.dumps(altered))
        with pytest.raises(ValidationError, match="preuve"):
            build_settings(**overrides)
    path.write_text(json.dumps({"OE-COMMERCIAL": original["OE-COMMERCIAL"]}))
    with pytest.raises(ValidationError, match="preuve"):
        build_settings(**overrides)
    path.write_text(json.dumps(original))
    (tmp_path / "synthetic-test-proof.txt").write_text("Modified after manual review")
    with pytest.raises(ValidationError, match="preuve"):
        build_settings(**overrides)


def test_personal_go_also_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="preuve"):
        build_settings(oe_commercial_gate="GO")
    with pytest.raises(ValueError, match="NO-GO"):
        verify_release("public", {}, None)


def test_api_reports_refusal_without_database_or_confidential_evidence() -> None:
    probe = StubReadinessProbe(ReadinessCheck(available=False))
    app = create_app(settings=build_settings(), readiness_probe=probe)
    response = get(app, "/api/v1/system/compliance")
    assert response.status_code == 200
    assert response.json() == {
        "audience": "personal",
        "gates": {"OE-COMMERCIAL": "NO-GO", "RIOT-PRODUCT": "NO-GO"},
        "publicReleaseAllowed": False,
        "stakeProviderEnabled": False,
    }
    assert probe.calls == 0


@pytest.mark.parametrize(
    ("audience", "exit_code"), [("personal", 0), ("public", 1), ("commercial", 1)]
)
def test_release_cli_actually_blocks_public_and_commercial(audience: str, exit_code: int) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "infra.scripts.check_release", "--audience", audience],
        env={
            **os.environ,
            "APP_ENV": "test",
            "APP_DATA_MODE": "mock",
            "ODDS_PROVIDER": "mock",
            "DATABASE_URL": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "RELEASE_AUDIENCE": "personal",
            "OE_COMMERCIAL_GATE": "NO-GO",
            "RIOT_PRODUCT_GATE": "NO-GO",
        },
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == exit_code, result.stderr
    assert json.loads(result.stdout)["allowed"] is (exit_code == 0)


def test_marketing_promises_block_the_compliance_scan(tmp_path: Path) -> None:
    source = tmp_path / "apps/web/page.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("<p>Metiquo ne garantit aucun gain.</p>", encoding="utf-8")
    assert not scan_provider_compliance(tmp_path)
    for claim in ("gain garanti", "guaranteed profit", "lock of the day"):
        source.write_text(f"<p>{claim}</p>", encoding="utf-8")
        assert scan_provider_compliance(tmp_path)[0].rule == "promesse de gain"
