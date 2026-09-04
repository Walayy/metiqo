"""Fixtures des tests d'intégration PostgreSQL."""

import os

import pytest


@pytest.fixture
def postgresql_url() -> str:
    """Exiger explicitement l'instance jetable fournie par l'appelant."""

    value = os.environ.get("TEST_DATABASE_URL")
    if value is None:
        pytest.skip("TEST_DATABASE_URL absent : test PostgreSQL local non demandé")
    return value
