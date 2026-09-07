"""Exercer la commande packagée avec les frontières de volumes du worker."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine

from metiquo.ingestion.freshness import FreshnessPolicy
from metiquo.ingestion.sync import OracleElixirYearSync
from tests.integration.test_backfill import _seed_catalogs
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _settings


@pytest.mark.integration
def test_packaged_backup_runs_with_read_only_root(postgresql_url: str, tmp_path: Path) -> None:
    image, container = os.environ.get("TEST_BACKUP_IMAGE"), os.environ.get("TEST_PG_CONTAINER")
    if not image or not container:
        pytest.skip("TEST_BACKUP_IMAGE et TEST_PG_CONTAINER requis")
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    _seed_catalogs(engine, dataset="league_of_legends_match_data", years=range(2026, 2027))
    settings = _settings(postgresql_url, "mock").model_copy(update={"object_store_root": tmp_path})
    fixture = Path(__file__).resolve().parents[1] / "fixtures/oracles_elixir/dq_valid.csv"
    OracleElixirYearSync(engine=engine, settings=settings).sync_year(
        year=2026, policy=FreshnessPolicy(require_fresh=True), fixture_path=fixture
    )
    environment = {
        **os.environ,
        "DATABASE_URL": engine.url.set(host="127.0.0.1", port=5432).render_as_string(
            hide_password=False
        ),
    }
    arguments = [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--network",
        f"container:{container}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp",
        "-e",
        "DATABASE_URL",
        "-e",
        "APP_ENV=test",
        "-e",
        "ODDS_PROVIDER=disabled",
        "-e",
        "APP_DATA_MODE=real",
        "-e",
        "OBJECT_STORE_ROOT=/data",
        "-e",
        "BACKUP_ROOT=/data/backups",
    ]
    for name in ("raw", "models", "quarantine", "backups"):
        folder = tmp_path / name
        folder.mkdir(exist_ok=True)
        arguments.extend(["--mount", f"type=bind,source={folder},target=/data/{name}"])
    arguments.extend([image, "oe", "backup", "--json"])
    for expected_copy in (True, False):
        result = subprocess.run(
            arguments, env=environment, capture_output=True, text=True, timeout=120
        )
        assert result.returncode == 0, result.stdout + result.stderr
        response = json.loads(result.stdout)
        assert (response["copiedObjects"] > 0) is expected_copy
        assert (tmp_path / "backups/runs" / response["backupId"] / "index.json").is_file()
    engine.dispose()
