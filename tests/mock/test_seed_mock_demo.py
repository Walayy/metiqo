"""Preuves du script de graine de la démo mock."""

from datetime import UTC, datetime

from metiquo.mock import MockScenarioKey
from metiquo.mock.demo import build_demo_manifest


def test_demo_manifest_is_complete_deterministic_and_network_free() -> None:
    reference_time = datetime(2026, 9, 4, 12, tzinfo=UTC)

    first = build_demo_manifest("metiquo-demo-v1", reference_time)
    second = build_demo_manifest("metiquo-demo-v1", reference_time)

    assert first == second
    assert first["scenarioCount"] == 12
    assert first["dataMode"] == "mock"
    assert first["externalNetworkAccess"] is False
    assert len(first["catalogSha256"]) == 64
    assert tuple(scenario["key"] for scenario in first["scenarios"]) == tuple(
        key.value for key in MockScenarioKey
    )
    assert any(scenario["publishable"] for scenario in first["scenarios"])
    assert all(scenario["eventId"] and scenario["signalId"] for scenario in first["scenarios"])


def test_another_seed_changes_the_catalog_identity() -> None:
    reference_time = datetime(2026, 9, 4, 12, tzinfo=UTC)

    first = build_demo_manifest("metiquo-demo-v1", reference_time)
    second = build_demo_manifest("another-demo", reference_time)

    assert first["catalogSha256"] != second["catalogSha256"]
    assert first["scenarios"][0]["eventId"] != second["scenarios"][0]["eventId"]
