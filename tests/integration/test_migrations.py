"""Tests des migrations sur une instance PostgreSQL jetable."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from metiquo.api.readiness import (
    MIGRATIONS_NOT_AT_HEAD,
    DatabaseReadinessProbe,
    ReadinessCheck,
)
from metiquo.db.schemas import ALL_SCHEMAS

ROOT = Path(__file__).resolve().parents[2]
RAW_TABLES = {
    "backfill_jobs",
    "backfill_years",
    "canonical_rows",
    "ingestion_runs",
    "quality_issues",
    "quarantine_items",
    "row_revisions",
    "snapshots",
    "source_catalog",
}
CORE_TABLES = {
    "canonical_entity_revisions",
    "canonical_entity_sources",
    "capability_evaluations",
    "competitions",
    "game_player_stats",
    "game_team_stats",
    "game_titles",
    "games",
    "patches",
    "players",
    "roster_observations",
    "series",
    "teams",
}


def alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


@pytest.mark.integration
def test_initial_migration_upgrade_downgrade_upgrade(postgresql_url: str) -> None:
    config = alembic_config(postgresql_url)

    command.upgrade(config, "head")


@pytest.mark.integration
def test_database_readiness_requires_migrations_at_head(postgresql_url: str) -> None:
    config = alembic_config(postgresql_url)
    probe = DatabaseReadinessProbe(postgresql_url, alembic_config=ROOT / "alembic.ini")

    command.downgrade(config, "base")
    unavailable = probe.check()

    assert unavailable.available is False
    assert unavailable.reason_code == MIGRATIONS_NOT_AT_HEAD

    command.upgrade(config, "head")

    assert probe.check() == ReadinessCheck(available=True)

    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    with engine.connect() as connection:
        schema_names = set(inspect(connection).get_schema_names())
        assert set(ALL_SCHEMAS) <= schema_names
        assert set(inspect(connection).get_table_names(schema="raw")) == RAW_TABLES
        assert set(inspect(connection).get_table_names(schema="core")) == CORE_TABLES
        assert set(inspect(connection).get_table_names(schema="features")) == {
            "feature_definitions",
            "feature_snapshots",
            "feature_set_members",
            "feature_sets",
            "invalidations",
        }
        assert set(inspect(connection).get_table_names(schema="ml")) == {
            "baseline_predictions",
            "baseline_runs",
            "dataset_examples",
            "datasets",
            "rating_artifacts",
            "tabular_benchmark_predictions",
            "tabular_benchmark_runs",
        }
        assert all(
            inspect(connection).get_table_names(schema=name) == []
            for name in ALL_SCHEMAS
            if name not in {"raw", "core", "features", "ml"}
        )
        assert connection.execute(text("SHOW TIME ZONE")).scalar_one() == "UTC"
    engine.dispose()

    command.downgrade(config, "base")

    verification_engine = create_engine(postgresql_url)
    with verification_engine.connect() as connection:
        schema_names = set(inspect(connection).get_schema_names())
        assert set(ALL_SCHEMAS).isdisjoint(schema_names)
    verification_engine.dispose()

    command.upgrade(config, "head")
