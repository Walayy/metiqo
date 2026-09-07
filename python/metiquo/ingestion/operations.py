"""Opérations de catalogue et vérification partagées par CLI et planification."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from metiquo.config import Settings
from metiquo.contracts.enums import DataMode
from metiquo.db.raw_models import Snapshot
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock, SystemClock
from metiquo.ingestion.catalog import LandingPageFetcher, SourceCatalogRepository, reconcile_catalog
from metiquo.ingestion.fallback_catalog import CatalogDiscoveryService, VersionedFallbackCatalog
from metiquo.ingestion.object_store import FilesystemObjectStore


def refresh_catalog(
    settings: Settings, engine: Engine, *, clock: Clock | None = None
) -> dict[str, object]:
    clock = clock or SystemClock()
    fallback = VersionedFallbackCatalog.load(settings.oe_source_catalog_path)
    outage_reason: str | None
    if settings.app_data_mode is DataMode.MOCK:
        discovery = fallback.as_discovery(clock)
        used_fallback, outage_reason = True, "mock mode: external discovery disabled"
    else:
        resolution = CatalogDiscoveryService(
            LandingPageFetcher(clock=clock), fallback, clock=clock
        ).resolve()
        discovery, used_fallback, outage_reason = (
            resolution.discovery,
            resolution.used_fallback,
            resolution.outage_reason,
        )
    with engine.begin() as connection:
        repository = SourceCatalogRepository(connection)
        reconciliation = reconcile_catalog(discovery, repository.active_records())
        repository.apply(reconciliation)
    return {
        "ok": True,
        "command": "catalog.refresh",
        "origin": discovery.origin,
        "usedFallback": used_fallback,
        "outageReason": outage_reason,
        "decisions": [
            {
                "year": decision.year,
                "status": decision.status,
                "candidateIds": [candidate.drive_file_id for candidate in decision.candidates],
            }
            for decision in reconciliation.decisions
        ],
        "alerts": [
            {"kind": alert.kind, "year": alert.year, "message": alert.message}
            for alert in reconciliation.alerts
        ],
    }


def verify_snapshot(engine: Engine, settings: Settings, snapshot_id: UUID) -> dict[str, object]:
    with Session(engine) as session:
        row = session.scalar(select(Snapshot).where(Snapshot.id == snapshot_id))
        if row is None:
            raise BusinessError(ErrorCode.NOT_FOUND, "Snapshot introuvable")
        store = FilesystemObjectStore(settings.object_store_root / "raw" / "oracles_elixir")
        digest, size = hashlib.sha256(), 0
        with store.open_source(year=row.year, sha256=row.sha256) as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        manifest_path = (
            settings.object_store_root
            / "raw"
            / "oracles_elixir"
            / f"year={row.year}"
            / f"sha256={row.sha256}"
            / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = json.loads(manifest_path.with_name("schema.json").read_text(encoding="utf-8"))
        columns = schema.get("columns") if isinstance(schema, dict) else None
        schema_hash = hashlib.sha256(
            json.dumps(columns, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        if (
            row.status != "validated"
            or digest.hexdigest() != row.sha256
            or size != row.byte_size
            or manifest != row.manifest
            or not isinstance(columns, list)
            or schema_hash != row.manifest.get("schemaFingerprint")
            or schema_hash != schema.get("schemaFingerprint")
        ):
            raise BusinessError(
                ErrorCode.INVALID_STATE,
                "Le snapshot ou son manifeste ne correspond pas à la preuve validée",
            )
        return {"snapshotId": str(row.id), "sha256": row.sha256, "byteSize": size}
