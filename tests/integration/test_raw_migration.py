"""Contraintes PostgreSQL du modèle raw de provenance."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

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


def alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


@pytest.mark.integration
def test_raw_model_has_expected_tables_and_provenance(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)

    with engine.connect() as connection:
        inspector = inspect(connection)
        assert set(inspector.get_table_names(schema="raw")) == RAW_TABLES
        catalog_foreign_keys = inspector.get_foreign_keys("source_catalog", schema="raw")
        assert {
            (
                tuple(fk["constrained_columns"]),
                fk["referred_schema"],
                fk["referred_table"],
                tuple(fk["referred_columns"]),
            )
            for fk in catalog_foreign_keys
        } == {
            (
                ("current_snapshot_id", "id"),
                "raw",
                "snapshots",
                ("id", "source_catalog_id"),
            )
        }
        snapshot_foreign_keys = inspector.get_foreign_keys("snapshots", schema="raw")
        assert {(fk["referred_schema"], fk["referred_table"]) for fk in snapshot_foreign_keys} == {
            ("raw", "source_catalog")
        }
        run_foreign_keys = inspector.get_foreign_keys("ingestion_runs", schema="raw")
        assert {(fk["referred_schema"], fk["referred_table"]) for fk in run_foreign_keys} == {
            ("raw", "source_catalog"),
            ("raw", "snapshots"),
        }

    engine.dispose()


@pytest.mark.integration
def test_only_one_active_catalog_source_exists_per_year(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    discovered_at = datetime(2026, 9, 5, tzinfo=UTC)
    provider = f"oracles-elixir-{uuid4().hex}"
    insert_catalog = text(
        """
        INSERT INTO raw.source_catalog (
          id, provider, dataset, season_year, landing_page, drive_file_id, source_name,
          origin, status, discovered_at
        ) VALUES (
          :id, :provider, 'league-of-legends', 2026, :landing_page, :source_file_id,
          :source_name, 'discovered', 'active', :discovered_at
        )
        """
    )

    with engine.begin() as connection:
        connection.execute(
            insert_catalog,
            {
                "id": uuid4(),
                "provider": provider,
                "landing_page": "https://oracleselixir.com/tools/downloads",
                "source_file_id": "drive-file-a",
                "source_name": "2026_LoL_esports_match_data_from_OraclesElixir.gzip",
                "discovered_at": discovered_at,
            },
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert_catalog,
            {
                "id": uuid4(),
                "provider": provider,
                "landing_page": "https://oracleselixir.com/tools/downloads",
                "source_file_id": "drive-file-b",
                "source_name": "2026_LoL_esports_match_data_from_OraclesElixir.gzip",
                "discovered_at": discovered_at,
            },
        )

    engine.dispose()


@pytest.mark.integration
def test_validated_snapshot_cannot_be_updated_or_deleted(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    catalog_id = uuid4()
    snapshot_id = uuid4()
    instant = datetime(2026, 9, 5, tzinfo=UTC)
    provider = f"oracles-elixir-{catalog_id.hex}"
    source_file_id = f"drive-{catalog_id.hex}"

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO raw.source_catalog (
                  id, provider, dataset, season_year, landing_page, drive_file_id,
                  source_name, origin, status, discovered_at
                ) VALUES (
                  :id, :provider, 'league-of-legends', 2025,
                  'https://oracleselixir.com/tools/downloads', :source_file_id,
                  '2025_LoL_esports_match_data_from_OraclesElixir.gzip',
                  'discovered', 'active', :instant
                )
                """
            ),
            {
                "id": catalog_id,
                "provider": provider,
                "source_file_id": source_file_id,
                "instant": instant,
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO raw.snapshots (
                  id, source_catalog_id, year, source_file_id, status, sha256,
                  byte_size, object_key, received_at, validated_at
                ) VALUES (
                  :id, :catalog_id, 2025, :source_file_id, 'validated', :sha256,
                  42, :object_key, :instant, :instant
                )
                """
            ),
            {
                "id": snapshot_id,
                "catalog_id": catalog_id,
                "source_file_id": source_file_id,
                "sha256": "a" * 64,
                "object_key": f"year=2025/sha256={snapshot_id.hex}/source.bin",
                "instant": instant,
            },
        )

    with (
        pytest.raises(DBAPIError, match=r"validated snapshot .* is immutable"),
        engine.begin() as connection,
    ):
        connection.execute(
            text("UPDATE raw.snapshots SET byte_size = 43 WHERE id = :id"),
            {"id": snapshot_id},
        )

    with (
        pytest.raises(DBAPIError, match=r"validated snapshot .* is immutable"),
        engine.begin() as connection,
    ):
        connection.execute(text("DELETE FROM raw.snapshots WHERE id = :id"), {"id": snapshot_id})

    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT byte_size FROM raw.snapshots WHERE id = :id"), {"id": snapshot_id}
            ).scalar_one()
            == 42
        )

    engine.dispose()
