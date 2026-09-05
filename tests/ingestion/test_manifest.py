"""Manifeste, schéma et vérification post-stockage d'un snapshot."""

import io
import json
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

import pytest

from metiquo.config import Settings
from metiquo.contracts.enums import DataMode
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.local_transports import LocalFixtureTransport
from metiquo.ingestion.manifest import (
    ColumnDefinition,
    SchemaDocument,
    SnapshotManifest,
    build_snapshot_manifest,
    store_snapshot,
)
from metiquo.ingestion.object_store import FilesystemObjectStore, SourceKind, StoredObject
from metiquo.ingestion.safe_download import SafeDownloader, SafeDownloadResult
from metiquo.ingestion.source_errors import ChecksumMismatch
from metiquo.ingestion.transport import SourceRef, TransportPolicy

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "oracles_elixir" / "sample_2026.csv"
REQUESTED_AT = datetime(2026, 9, 5, 18, tzinfo=UTC)
MIN_EVENT_AT = datetime(2026, 1, 10, 12, tzinfo=UTC)
MAX_EVENT_AT = datetime(2026, 1, 10, 13, tzinfo=UTC)
CLOCK = FixedClock(UtcInstant(REQUESTED_AT))
SOURCE = SourceRef(
    provider="oracles_elixir",
    year=2026,
    source_id="drive-file-2026",
    locator="fixture://sample-2026",
    source_name="sample_2026.csv",
    mutable=True,
)
SCHEMA = SchemaDocument(
    (
        ColumnDefinition(0, "gameid", "string", False),
        ColumnDefinition(1, "league", "string", False),
        ColumnDefinition(2, "side", "string", False),
        ColumnDefinition(3, "result", "integer", False),
    )
)


def _transport() -> LocalFixtureTransport:
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "mock",
            "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "odds_provider": "mock",
        }
    )
    return LocalFixtureTransport(
        policy=TransportPolicy.from_settings(settings),
        fixtures={SOURCE.source_id: FIXTURE},
        data_mode=DataMode.MOCK,
        clock=CLOCK,
    )


def _manifest(tmp_path: Path) -> tuple[SnapshotManifest, SafeDownloadResult]:
    transport = _transport()
    metadata = transport.probe(SOURCE)
    download = SafeDownloader().download(
        transport=transport,
        source=SOURCE,
        destination=tmp_path / "downloaded.csv",
    )
    manifest = build_snapshot_manifest(
        source=SOURCE,
        metadata=metadata,
        download=download,
        schema=SCHEMA,
        row_count=1,
        min_event_date=MIN_EVENT_AT,
        max_event_date=MAX_EVENT_AT,
        quality_status="passed",
        quality={"blocking": 0, "warnings": 0},
        ingestion_code_version="test-commit",
    )
    return manifest, download


def test_manifest_roundtrip_identifies_exact_consumed_dataset(tmp_path: Path) -> None:
    manifest, _ = _manifest(tmp_path)

    restored = SnapshotManifest.from_json_bytes(manifest.to_json_bytes())

    assert restored == manifest
    document = json.loads(manifest.to_json_bytes())
    assert document["provider"] == "oracles_elixir"
    assert document["seasonYear"] == 2026
    assert document["driveFileId"] == SOURCE.source_id
    assert document["byteSize"] == FIXTURE.stat().st_size
    assert document["schemaFingerprint"] == SCHEMA.fingerprint
    assert document["rowCount"] == 1
    assert document["minEventDate"] == "2026-01-10T12:00:00Z"
    assert document["maxEventDate"] == "2026-01-10T13:00:00Z"
    assert document["qualityStatus"] == "passed"
    assert document["ingestionCodeVersion"] == "test-commit"


def test_schema_fingerprint_is_stable_and_sensitive() -> None:
    same = SchemaDocument(tuple(SCHEMA.columns))
    changed = SchemaDocument((*SCHEMA.columns[:-1], ColumnDefinition(3, "result", "float", False)))

    assert same.fingerprint == SCHEMA.fingerprint
    assert changed.fingerprint != SCHEMA.fingerprint


def test_snapshot_documents_are_stored_and_hash_is_reread(tmp_path: Path) -> None:
    manifest, download = _manifest(tmp_path)
    store = FilesystemObjectStore(tmp_path / "object-store")

    stored = store_snapshot(
        object_store=store,
        download=download,
        manifest=manifest,
        schema=SCHEMA,
    )

    assert stored.sha256 == manifest.sha256
    assert stored.object_key.endswith("/source.csv")
    assert (stored.object_directory / "manifest.json").read_bytes() == manifest.to_json_bytes()
    schema_document = json.loads((stored.object_directory / "schema.json").read_bytes())
    assert schema_document["schemaFingerprint"] == SCHEMA.fingerprint
    quality = json.loads((stored.object_directory / "quality-report.json").read_bytes())
    assert quality == {"blocking": 0, "status": "passed", "warnings": 0}


def test_manifest_mismatch_blocks_storage(tmp_path: Path) -> None:
    manifest, download = _manifest(tmp_path)
    store = FilesystemObjectStore(tmp_path / "object-store")

    with pytest.raises(ChecksumMismatch, match="manifeste incohérent"):
        store_snapshot(
            object_store=store,
            download=download,
            manifest=replace(manifest, sha256="f" * 64),
            schema=SCHEMA,
        )

    assert list((tmp_path / "object-store").glob("**/source.*")) == []


class LyingObjectStore:
    def put_source(
        self,
        *,
        year: int,
        chunks: Iterable[bytes],
        source_kind: SourceKind = "bin",
        manifest: Mapping[str, object] | None = None,
        schema: Mapping[str, object] | None = None,
        quality_report: Mapping[str, object] | None = None,
    ) -> StoredObject:
        del chunks, manifest, schema, quality_report
        return StoredObject(year, "0" * 64, source_kind, Path("source.bin"), False)

    def open_source(self, *, year: int, sha256: str) -> BinaryIO:
        del year, sha256
        return io.BytesIO(b"corrupted after promotion")


def test_hash_incoherent_after_storage_blocks_snapshot(tmp_path: Path) -> None:
    manifest, download = _manifest(tmp_path)

    with pytest.raises(ChecksumMismatch, match="après stockage"):
        store_snapshot(
            object_store=LyingObjectStore(),
            download=download,
            manifest=manifest,
            schema=SCHEMA,
        )
