"""Manifeste déterministe de la démo mock complète."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import TypedDict

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.mock.scenarios import MockScenarioCatalog, build_mock_scenario_catalog

DEFAULT_REFERENCE_TIME = datetime(2026, 9, 4, 12, tzinfo=UTC)


class ScenarioManifest(TypedDict):
    """Références stables utiles pour parcourir un scénario de démo."""

    eventId: str
    grade: str
    key: str
    publishable: bool
    signalId: str


class DemoManifest(TypedDict):
    """Résumé sérialisable d'une graine mock validée."""

    catalogSha256: str
    dataMode: str
    externalNetworkAccess: bool
    referenceTime: str
    scenarioCount: int
    scenarios: list[ScenarioManifest]
    seed: str


def _catalog_digest(catalog: MockScenarioCatalog) -> str:
    serialized = json.dumps(
        catalog.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(serialized).hexdigest()


def build_demo_manifest(seed: str, reference_time: datetime) -> DemoManifest:
    """Construire le catalogue complet sans DB ni accès réseau et retourner son manifeste."""

    catalog = build_mock_scenario_catalog(seed, FixedClock(UtcInstant(reference_time)))
    scenarios: list[ScenarioManifest] = []
    for scenario in catalog.scenarios:
        opportunity = scenario.opportunity
        scenarios.append(
            {
                "eventId": str(opportunity.event.event_id),
                "grade": opportunity.value.grade.value,
                "key": scenario.scenario_key.value,
                "publishable": opportunity.quality.publishable,
                "signalId": str(opportunity.signal_id),
            }
        )
    return {
        "catalogSha256": _catalog_digest(catalog),
        "dataMode": "mock",
        "externalNetworkAccess": False,
        "referenceTime": catalog.reference_time.isoformat().replace("+00:00", "Z"),
        "scenarioCount": len(scenarios),
        "scenarios": scenarios,
        "seed": catalog.seed,
    }
