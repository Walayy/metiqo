"""Staging éphémère et double chargement idempotent du raw tabulaire."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.raw_loader import RawTabularLoader

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "oracles_elixir" / "dq_valid.csv"
INSTANT = datetime(2026, 9, 5, 23, 30, tzinfo=UTC)


def alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


def _seed_published_snapshot_and_load_runs(
    connection: Connection,
) -> tuple[UUID, UUID, UUID, UUID]:
    catalog_id = uuid4()
    snapshot_id = uuid4()
    first_run_id = uuid4()
    second_run_id = uuid4()
    unique = catalog_id.hex
    connection.execute(
        text(
            """
            INSERT INTO raw.source_catalog (
              id, provider, dataset, season_year, landing_page, drive_file_id,
              source_name, origin, status, discovered_at
            ) VALUES (
              :catalog_id, 'oracles_elixir', :dataset, 2026,
              'https://oracleselixir.com/tools/downloads', :drive_file_id,
              '2026_LoL_esports_match_data_from_OraclesElixir.csv',
              'discovered', 'active', :instant
            )
            """
        ),
        {
            "catalog_id": catalog_id,
            "dataset": f"league-of-legends-{unique}",
            "drive_file_id": f"drive-{unique}",
            "instant": INSTANT,
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO raw.snapshots (
              id, source_catalog_id, year, source_file_id, status, sha256,
              byte_size, content_type, object_key, received_at, validated_at
            ) VALUES (
              :snapshot_id, :catalog_id, 2026, :drive_file_id, 'validated', :sha256,
              :byte_size, 'text/csv', :object_key, :instant, :instant
            )
            """
        ),
        {
            "snapshot_id": snapshot_id,
            "catalog_id": catalog_id,
            "drive_file_id": f"drive-{unique}",
            "sha256": unique * 2,
            "byte_size": FIXTURE.stat().st_size,
            "object_key": f"year=2026/sha256={unique * 2}/source.csv",
            "instant": INSTANT,
        },
    )
    connection.execute(
        text(
            "UPDATE raw.source_catalog SET current_snapshot_id = :snapshot_id "
            "WHERE id = :catalog_id"
        ),
        {"snapshot_id": snapshot_id, "catalog_id": catalog_id},
    )
    for run_id in (first_run_id, second_run_id):
        connection.execute(
            text(
                """
                INSERT INTO raw.ingestion_runs (
                  id, source_catalog_id, snapshot_id, run_kind, status,
                  attempt, transport, correlation_id, started_at
                ) VALUES (
                  :run_id, :catalog_id, :snapshot_id, 'load', 'running',
                  1, 'filesystem', :correlation_id, :instant
                )
                """
            ),
            {
                "run_id": run_id,
                "catalog_id": catalog_id,
                "snapshot_id": snapshot_id,
                "correlation_id": f"load-{run_id.hex}",
                "instant": INSTANT,
            },
        )
    return catalog_id, snapshot_id, first_run_id, second_run_id


@pytest.mark.integration
def test_double_load_is_idempotent_and_drops_each_staging_table(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with engine.begin() as connection:
        catalog_id, snapshot_id, first_run_id, second_run_id = (
            _seed_published_snapshot_and_load_runs(connection)
        )

    loader = RawTabularLoader(
        engine=engine,
        clock=FixedClock(UtcInstant(INSTANT)),
        batch_size=3,
    )
    first = loader.load(
        source_catalog_id=catalog_id,
        snapshot_id=snapshot_id,
        run_id=first_run_id,
        csv_path=FIXTURE,
    )
    second = loader.load(
        source_catalog_id=catalog_id,
        snapshot_id=snapshot_id,
        run_id=second_run_id,
        csv_path=FIXTURE,
    )

    assert first.natural_key_fields == ("gameid", "participantid")
    assert first.fallback_key_used is False
    assert first.statistics.to_dict() == {
        "inserted": 12,
        "updated": 0,
        "unchanged": 0,
        "quarantined": 0,
        "total": 12,
    }
    assert second.statistics.to_dict() == {
        "inserted": 0,
        "updated": 0,
        "unchanged": 12,
        "quarantined": 0,
        "total": 12,
    }

    with engine.connect() as connection:
        canonical_count = connection.execute(
            text("SELECT count(*) FROM raw.canonical_rows WHERE source_snapshot_id = :snapshot_id"),
            {"snapshot_id": snapshot_id},
        ).scalar_one()
        sample = (
            connection.execute(
                text(
                    """
                SELECT natural_key, payload, revision
                FROM raw.canonical_rows
                WHERE source_snapshot_id = :snapshot_id
                ORDER BY natural_key
                LIMIT 1
                """
                ),
                {"snapshot_id": snapshot_id},
            )
            .mappings()
            .one()
        )
        run_counters = (
            connection.execute(
                text(
                    "SELECT id, status, counters FROM raw.ingestion_runs "
                    "WHERE id IN (:first_run_id, :second_run_id)"
                ),
                {"first_run_id": first_run_id, "second_run_id": second_run_id},
            )
            .mappings()
            .all()
        )
        first_staging = connection.execute(
            text("SELECT to_regclass(:name)"),
            {"name": f"pg_temp.{first.staging_table}"},
        ).scalar_one()
        second_staging = connection.execute(
            text("SELECT to_regclass(:name)"),
            {"name": f"pg_temp.{second.staging_table}"},
        ).scalar_one()
        revision_count = connection.execute(
            text("SELECT count(*) FROM raw.row_revisions WHERE snapshot_id = :snapshot_id"),
            {"snapshot_id": snapshot_id},
        ).scalar_one()

    assert canonical_count == 12
    assert sample["revision"] == 1
    assert sample["natural_key"].startswith('["OE-001",')
    assert set(sample["payload"]) == {
        "gameid",
        "date",
        "participantid",
        "side",
        "position",
        "teamname",
        "league",
        "result",
        "datacompleteness",
        "kills",
        "gamelength",
        "forfeit",
    }
    assert {row["status"] for row in run_counters} == {"succeeded"}
    counters_by_id = {row["id"]: row["counters"] for row in run_counters}
    assert counters_by_id[first_run_id] == first.statistics.to_dict()
    assert counters_by_id[second_run_id] == second.statistics.to_dict()
    assert first_staging is None
    assert second_staging is None
    assert revision_count == 12
    engine.dispose()


@pytest.mark.integration
def test_retroactive_change_creates_linked_revision_without_deleting_absent_rows(
    postgresql_url: str,
    tmp_path: Path,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    with engine.begin() as connection:
        catalog_id, first_snapshot_id, first_run_id, second_run_id = (
            _seed_published_snapshot_and_load_runs(connection)
        )

    loader = RawTabularLoader(
        engine=engine,
        clock=FixedClock(UtcInstant(INSTANT)),
    )
    first = loader.load(
        source_catalog_id=catalog_id,
        snapshot_id=first_snapshot_id,
        run_id=first_run_id,
        csv_path=FIXTURE,
    )
    assert first.statistics.inserted == 12

    corrected_path = tmp_path / "corrected.csv"
    lines = FIXTURE.read_text().splitlines()
    lines[1] = lines[1].replace(
        ",complete,2,1800,false",
        ",complete,99,1800,false",
    )
    corrected_path.write_text("\n".join(lines[:-1]) + "\n")
    second_snapshot_id = uuid4()
    with engine.begin() as connection:
        catalog = (
            connection.execute(
                text("SELECT drive_file_id, dataset FROM raw.source_catalog WHERE id = :id"),
                {"id": catalog_id},
            )
            .mappings()
            .one()
        )
        drive_file_id = catalog["drive_file_id"]
        dataset = catalog["dataset"]
        connection.execute(
            text(
                """
                INSERT INTO raw.snapshots (
                  id, source_catalog_id, year, source_file_id, status, sha256,
                  byte_size, content_type, object_key, received_at, validated_at
                ) VALUES (
                  :snapshot_id, :catalog_id, 2026, :drive_file_id, 'validated', :sha256,
                  :byte_size, 'text/csv', :object_key, :instant, :instant
                )
                """
            ),
            {
                "snapshot_id": second_snapshot_id,
                "catalog_id": catalog_id,
                "drive_file_id": drive_file_id,
                "sha256": second_snapshot_id.hex * 2,
                "byte_size": corrected_path.stat().st_size,
                "object_key": (f"year=2026/sha256={second_snapshot_id.hex * 2}/source.csv"),
                "instant": INSTANT,
            },
        )
        connection.execute(
            text(
                "UPDATE raw.source_catalog SET current_snapshot_id = :snapshot_id "
                "WHERE id = :catalog_id"
            ),
            {"snapshot_id": second_snapshot_id, "catalog_id": catalog_id},
        )
        connection.execute(
            text("UPDATE raw.ingestion_runs SET snapshot_id = :snapshot_id WHERE id = :run_id"),
            {"snapshot_id": second_snapshot_id, "run_id": second_run_id},
        )

    second = loader.load(
        source_catalog_id=catalog_id,
        snapshot_id=second_snapshot_id,
        run_id=second_run_id,
        csv_path=corrected_path,
    )
    assert second.statistics.to_dict() == {
        "inserted": 0,
        "updated": 1,
        "unchanged": 10,
        "quarantined": 0,
        "total": 11,
    }

    changed_key = '["OE-001","1"]'
    unchanged_key = '["OE-001","2"]'
    with engine.connect() as connection:
        canonical_count = connection.execute(
            text(
                "SELECT count(*) FROM raw.canonical_rows "
                "WHERE provider = 'oracles_elixir' AND dataset = :dataset"
            ),
            {"dataset": dataset},
        ).scalar_one()
        canonical = (
            connection.execute(
                text(
                    """
                SELECT revision, payload, source_snapshot_id, source_run_id
                FROM raw.canonical_rows
                WHERE dataset = :dataset AND natural_key = :natural_key
                """
                ),
                {"dataset": dataset, "natural_key": changed_key},
            )
            .mappings()
            .one()
        )
        revisions = (
            connection.execute(
                text(
                    """
                SELECT id, revision, operation, previous_revision_id, payload,
                       snapshot_id, run_id, event_date
                FROM raw.row_revisions
                WHERE dataset = :dataset AND natural_key = :natural_key
                ORDER BY revision
                """
                ),
                {"dataset": dataset, "natural_key": changed_key},
            )
            .mappings()
            .all()
        )
        unchanged_revisions = connection.execute(
            text(
                "SELECT count(*) FROM raw.row_revisions "
                "WHERE dataset = :dataset AND natural_key = :natural_key"
            ),
            {"dataset": dataset, "natural_key": unchanged_key},
        ).scalar_one()

    assert canonical_count == 12
    assert canonical["revision"] == 2
    assert canonical["payload"]["kills"] == "99"
    assert canonical["source_snapshot_id"] == second_snapshot_id
    assert canonical["source_run_id"] == second_run_id
    assert [row["revision"] for row in revisions] == [1, 2]
    assert [row["operation"] for row in revisions] == ["inserted", "updated"]
    assert revisions[0]["previous_revision_id"] is None
    assert revisions[1]["previous_revision_id"] == revisions[0]["id"]
    assert revisions[0]["payload"]["kills"] == "2"
    assert revisions[1]["payload"]["kills"] == "99"
    assert revisions[1]["snapshot_id"] == second_snapshot_id
    assert revisions[1]["run_id"] == second_run_id
    assert str(revisions[1]["event_date"]) == "2026-01-10"
    assert unchanged_revisions == 1

    with (
        pytest.raises(DBAPIError, match=r"row revision .* is append-only"),
        engine.begin() as connection,
    ):
        connection.execute(
            text("UPDATE raw.row_revisions SET operation = 'inserted' WHERE id = :id"),
            {"id": revisions[1]["id"]},
        )
    with (
        pytest.raises(DBAPIError, match=r"row revision .* is append-only"),
        engine.begin() as connection,
    ):
        connection.execute(
            text("DELETE FROM raw.row_revisions WHERE id = :id"),
            {"id": revisions[1]["id"]},
        )
    engine.dispose()
