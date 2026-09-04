"""Test de reproductibilité du contrat OpenAPI versionné."""

from pathlib import Path

from metiquo.api.openapi import render_openapi

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_CONTRACT = ROOT / "packages" / "contracts" / "openapi" / "v1.json"


def test_committed_openapi_contract_is_current() -> None:
    assert OPENAPI_CONTRACT.read_text(encoding="utf-8") == render_openapi()


def test_openapi_contract_contains_versioned_system_routes() -> None:
    rendered = render_openapi()

    assert '"/health"' in rendered
    assert '"/ready"' in rendered
    assert '"/api/v1/system/status"' in rendered
    assert '"ProblemDetails"' in rendered
    assert '"application/problem+json"' in rendered
