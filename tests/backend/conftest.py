import os

import pytest
from alembic import command
from alembic.config import Config
from metiquo_core.config import Settings
from metiquo_core.db import create_db
from sqlalchemy import text
from sqlalchemy.engine import make_url


@pytest.fixture
def database(monkeypatch, tmp_path):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL database ending in _test")
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        pytest.fail("Refusing to reset a database whose name does not end with _test")
    monkeypatch.setenv("METIQUO_DATABASE_URL", url)
    monkeypatch.setenv("METIQUO_AUTH_SECRET", "isolated-test-key-that-is-at-least-32-characters")
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(artifact_dir=tmp_path / "artifacts")
    engine = create_db(settings)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE oracle_rows, dataset_versions, datasets, ingestion_runs, "
                "odds_observations, probability_estimates, markets, matches, teams, leagues, "
                "catalog_metadata, app_users, auth_challenges, auth_sessions, auth_rate_limits "
                "CASCADE"
            )
        )
    yield engine, settings
    engine.dispose()
