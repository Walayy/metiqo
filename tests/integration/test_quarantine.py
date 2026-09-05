"""Quarantaine durable et lecture sûre du dernier snapshot validé."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.ingestion.quarantine import (
    QuarantineAuditEvent,
    QuarantineService,
    SnapshotReader,
)

ROOT = Path(__file__).resolve().parents[2]
INSTANT = datetime(2026, 9, 5, 22, tzinfo=UTC)


def alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


class RecordingAuditSink:
    def __init__(self) -> None:
        self.events: list[QuarantineAuditEvent] = []

    def record(self, event: QuarantineAuditEvent) -> None:
        self.events.append(event)


def _seed_catalog_run_and_validated_snapshot(
    connection: Connection,
) -> tuple[UUID, UUID, UUID]:
    catalog_id = uuid4()
    run_id = uuid4()
    validated_snapshot_id = uuid4()
    unique = catalog_id.hex
    connection.execute(
        text(
            """
            INSERT INTO raw.source_catalog (
              id, provider, dataset, season_year, landing_page, drive_file_id,
              source_name, origin, status, discovered_at
            ) VALUES (
              :catalog_id, :provider, 'league-of-legends', 2026,
              'https://oracleselixir.com/tools/downloads', :source_file_id,
              '2026_LoL_esports_match_data_from_OraclesElixir.csv',
              'discovered', 'active', :instant
            )
            """
        ),
        {
            "catalog_id": catalog_id,
            "provider": f"oracles-elixir-{unique}",
            "source_file_id": f"drive-{unique}",
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
              :snapshot_id, :catalog_id, 2026, :source_file_id, 'validated', :sha256,
              42, 'text/csv', :object_key, :instant, :instant
            )
            """
        ),
        {
            "snapshot_id": validated_snapshot_id,
            "catalog_id": catalog_id,
            "source_file_id": f"drive-{unique}",
            "sha256": unique * 2,
            "object_key": f"year=2026/sha256={unique * 2}/source.csv",
            "instant": INSTANT,
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO raw.ingestion_runs (
              id, source_catalog_id, run_kind, status, attempt, correlation_id, started_at
            ) VALUES (
              :run_id, :catalog_id, 'sync', 'running', 1, :correlation_id, :instant
            )
            """
        ),
        {
            "run_id": run_id,
            "catalog_id": catalog_id,
            "correlation_id": f"quarantine-{unique}",
            "instant": INSTANT,
        },
    )
    return catalog_id, run_id, validated_snapshot_id


@pytest.mark.integration
def test_quarantine_preserves_current_snapshot_and_requires_audited_resolution(
    postgresql_url: str, tmp_path: Path
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    payload = tmp_path / "invalid.csv"
    payload.write_bytes(b"gameid,side\nbroken,unknown\n")
    store_root = tmp_path / "quarantine-store"
    audit_sink = RecordingAuditSink()
    clock = FixedClock(UtcInstant(INSTANT))

    with engine.begin() as connection:
        catalog_id, run_id, validated_snapshot_id = _seed_catalog_run_and_validated_snapshot(
            connection
        )
        service = QuarantineService(
            connection=connection,
            object_store=FilesystemObjectStore(store_root),
            clock=clock,
        )
        quarantined = service.capture(
            source_catalog_id=catalog_id,
            run_id=run_id,
            year=2026,
            source_file_id="drive-invalid",
            payload_path=payload,
            reason_code="DATA_QUALITY_BLOCKING",
            diagnostic={"blockingCodes": ["SIDE_INVALID"], "rowCount": 1},
            source_kind="csv",
            content_type="text/csv",
        )

        current = SnapshotReader(connection).latest_validated(catalog_id)
        assert current is not None
        assert current.id == validated_snapshot_id
        assert current.status == "validated"

        snapshot_row = (
            connection.execute(
                text("SELECT status, failure_reason, object_key FROM raw.snapshots WHERE id = :id"),
                {"id": quarantined.snapshot_id},
            )
            .mappings()
            .one()
        )
        assert snapshot_row["status"] == "quarantined"
        assert snapshot_row["failure_reason"] == "DATA_QUALITY_BLOCKING"
        assert str(snapshot_row["object_key"]).startswith("quarantine/")

        item_row = (
            connection.execute(
                text(
                    "SELECT status, reason_code, diagnostic "
                    "FROM raw.quarantine_items WHERE id = :id"
                ),
                {"id": quarantined.item_id},
            )
            .mappings()
            .one()
        )
        assert item_row["status"] == "pending"
        assert item_row["reason_code"] == "DATA_QUALITY_BLOCKING"
        assert item_row["diagnostic"] == {
            "blockingCodes": ["SIDE_INVALID"],
            "rowCount": 1,
        }

        with pytest.raises(ValueError, match="acteur et motif"):
            service.resolve(
                item_id=quarantined.item_id,
                decision="accepted",
                actor="",
                reason="",
                audit_sink=audit_sink,
            )

        event = service.resolve(
            item_id=quarantined.item_id,
            decision="rejected",
            actor="operator@example.test",
            reason="Structure invalide confirmée",
            audit_sink=audit_sink,
        )
        assert event.action == "quarantine.rejected"
        assert event.snapshot_id == quarantined.snapshot_id
        assert audit_sink.events == [event]

        resolved_row = (
            connection.execute(
                text(
                    """
                SELECT status, resolved_by, resolution_reason
                FROM raw.quarantine_items WHERE id = :id
                """
                ),
                {"id": quarantined.item_id},
            )
            .mappings()
            .one()
        )
        assert resolved_row["status"] == "rejected"
        assert resolved_row["resolved_by"] == "operator@example.test"
        assert resolved_row["resolution_reason"] == "Structure invalide confirmée"

        snapshot_status = connection.execute(
            text("SELECT status FROM raw.snapshots WHERE id = :id"),
            {"id": quarantined.snapshot_id},
        ).scalar_one()
        assert snapshot_status == "quarantined"
        current_after_resolution = SnapshotReader(connection).latest_validated(catalog_id)
        assert current_after_resolution is not None
        assert current_after_resolution.id == validated_snapshot_id

    object_directory = store_root / "year=2026" / f"sha256={quarantined.sha256}"
    assert (object_directory / "source.csv").read_bytes() == payload.read_bytes()
    assert json.loads((object_directory / "manifest.json").read_text()) == {
        "capturedAt": "2026-09-05T22:00:00Z",
        "reasonCode": "DATA_QUALITY_BLOCKING",
        "sourceFileId": "drive-invalid",
        "status": "quarantined",
    }
    assert json.loads((object_directory / "quality-report.json").read_text()) == {
        "blockingCodes": ["SIDE_INVALID"],
        "rowCount": 1,
    }
    engine.dispose()
