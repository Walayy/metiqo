"""Contrat statique de l'orchestration Docker Compose."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORE_SERVICES = {"postgres", "volume-init", "api", "worker", "web"}
FORBIDDEN_SERVICES = {"airflow", "celery", "feature-store", "kafka", "redis", "spark"}
PERSISTENT_VOLUMES = {"postgres_data", "raw_snapshots", "model_artifacts", "backups"}


def compose_configuration() -> dict[str, object]:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI absent")
    completed = subprocess.run(
        ["docker", "compose", "--profile", "*", "config", "--format", "json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return cast(dict[str, object], json.loads(completed.stdout))


@pytest.mark.integration
def test_compose_profiles_services_and_volumes() -> None:
    configuration = compose_configuration()
    services = cast(dict[str, dict[str, object]], configuration["services"])
    volumes = cast(dict[str, object], configuration["volumes"])

    assert services.keys() >= CORE_SERVICES
    assert FORBIDDEN_SERVICES.isdisjoint(services)
    assert volumes.keys() >= PERSISTENT_VOLUMES
    assert services["gateway"]["profiles"] == ["production", "object-store"]
    assert services["minio"]["profiles"] == ["object-store"]
    assert services["mock-mode-check"]["profiles"] == ["mock"]
    assert all("profiles" not in services[name] for name in CORE_SERVICES)


@pytest.mark.integration
def test_compose_applies_least_privilege_boundaries() -> None:
    services = cast(dict[str, dict[str, object]], compose_configuration()["services"])

    assert services["api"]["read_only"] is True
    assert services["worker"]["read_only"] is True
    assert services["web"]["read_only"] is True
    assert services["gateway"]["read_only"] is True
    assert services["volume-init"]["network_mode"] == "none"
    assert services["mock-mode-check"]["network_mode"] == "none"
    assert services["minio-volume-init"]["network_mode"] == "none"
