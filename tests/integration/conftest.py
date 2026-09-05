"""Fixtures des tests d'intégration PostgreSQL."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


@pytest.fixture
def postgresql_url() -> Iterator[str]:
    """Fournir une base jetable remise à zéro avant chaque test."""

    value = os.environ.get("TEST_DATABASE_URL")
    if value is None:
        pytest.skip("TEST_DATABASE_URL absent : test PostgreSQL local non demandé")
    command.downgrade(_alembic_config(value), "base")
    yield value
