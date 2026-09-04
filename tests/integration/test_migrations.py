"""Tests des migrations sur une instance PostgreSQL jetable."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from metiquo.db.schemas import LOGICAL_SCHEMAS

ROOT = Path(__file__).resolve().parents[2]


def database_url() -> str:
    value = os.environ.get("TEST_DATABASE_URL")
    if value is None:
        pytest.skip("TEST_DATABASE_URL absent : test PostgreSQL local non demandé")
    return value


def alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


@pytest.mark.integration
def test_initial_migration_upgrade_downgrade_upgrade() -> None:
    url = database_url()
    config = alembic_config(url)

    command.upgrade(config, "head")

    engine = create_engine(url, connect_args={"options": "-c timezone=UTC"})
    with engine.connect() as connection:
        schema_names = set(inspect(connection).get_schema_names())
        assert set(LOGICAL_SCHEMAS) <= schema_names
        assert all(
            inspect(connection).get_table_names(schema=name) == [] for name in LOGICAL_SCHEMAS
        )
        assert connection.execute(text("SHOW TIME ZONE")).scalar_one() == "UTC"
    engine.dispose()

    command.downgrade(config, "base")

    verification_engine = create_engine(url)
    with verification_engine.connect() as connection:
        schema_names = set(inspect(connection).get_schema_names())
        assert set(LOGICAL_SCHEMAS).isdisjoint(schema_names)
    verification_engine.dispose()

    command.upgrade(config, "head")
