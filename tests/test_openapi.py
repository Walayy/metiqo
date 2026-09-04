"""Tests de reproductibilité du contrat OpenAPI versionné."""

import json
from pathlib import Path

import pytest

from metiquo.api.openapi import render_openapi, verify_openapi_content

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_CONTRACT = ROOT / "packages" / "contracts" / "openapi" / "v1.json"


def test_committed_openapi_contract_is_current() -> None:
    assert OPENAPI_CONTRACT.read_text(encoding="utf-8") == render_openapi()


def test_openapi_content_verifier_detects_drift() -> None:
    verify_openapi_content(render_openapi())

    with pytest.raises(RuntimeError, match="obsolète"):
        verify_openapi_content("{}\n")


def test_openapi_contract_contains_versioned_system_routes() -> None:
    rendered = render_openapi()

    assert '"/health"' in rendered
    assert '"/ready"' in rendered
    assert '"/api/v1/system/status"' in rendered
    assert '"ProblemDetails"' in rendered
    assert '"application/problem+json"' in rendered


def test_openapi_contract_publishes_domain_components_and_mock_read_routes() -> None:
    document = json.loads(render_openapi())
    schemas = document["components"]["schemas"]

    assert {
        "Opportunity",
        "Event",
        "Market",
        "OddsSnapshot",
        "Prediction",
        "Value",
        "Quality",
        "ModelSummary",
        "BacktestSummary",
        "PaperBet",
        "MappingReview",
        "GameTitle",
        "MarketType",
        "MarketPeriod",
        "SelectionType",
        "ValueGrade",
        "FreshnessStatus",
        "AbstentionReason",
        "ProviderStatus",
        "MarketStatus",
        "EventStatus",
    } <= set(schemas)
    assert {
        "/health",
        "/ready",
        "/api/v1/system/status",
        "/api/v1/opportunities",
        "/api/v1/opportunities/{signal_id}",
        "/api/v1/opportunities/{signal_id}/explanation",
        "/api/v1/events",
        "/api/v1/events/{event_id}",
        "/api/v1/events/{event_id}/markets",
        "/api/v1/events/{event_id}/odds-history",
        "/api/v1/models",
        "/api/v1/models/{model_version_id}",
        "/api/v1/backtests",
        "/api/v1/backtests/{backtest_id}",
        "/api/v1/paper-bets",
        "/api/v1/paper-bets/{paper_bet_id}",
        "/api/v1/admin/data-sources",
        "/api/v1/admin/ingestion-runs",
        "/api/v1/admin/quality-issues",
        "/api/v1/admin/jobs",
        "/api/v1/admin/mappings/pending",
    } == set(document["paths"])


def test_all_openapi_component_references_resolve() -> None:
    document = json.loads(render_openapi())
    schemas = document["components"]["schemas"]

    def references(value: object) -> set[str]:
        if isinstance(value, dict):
            found = {
                item.removeprefix("#/components/schemas/")
                for key, item in value.items()
                if key == "$ref"
                and isinstance(item, str)
                and item.startswith("#/components/schemas/")
            }
            return found.union(*(references(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(references(item) for item in value))
        return set()

    assert references(document) <= set(schemas)
