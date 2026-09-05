"""Publication transactionnelle d'un snapshot déjà validé et stocké."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, Table, insert, select, update

from metiquo.db.raw_models import IngestionRun, Snapshot, SourceCatalog
from metiquo.foundation.time import Clock, SystemClock
from metiquo.ingestion.manifest import SnapshotManifest
from metiquo.ingestion.object_store import ObjectStore, StoredObject
from metiquo.ingestion.source_errors import AtomicPromotionFailed

type BeforeCommitHook = Callable[[Connection], None]

_READ_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class PromotionResult:
    snapshot_id: UUID
    source_catalog_id: UUID
    run_id: UUID
    previous_snapshot_id: UUID | None
    object_key: str
    sha256: str
    committed_at: datetime
    reused: bool


class SnapshotPromotionService:
    """Déplacer le pointeur courant et clôturer le run dans un commit unique."""

    def __init__(
        self,
        *,
        engine: Engine,
        object_store: ObjectStore,
        clock: Clock | None = None,
        before_commit: BeforeCommitHook | None = None,
    ) -> None:
        self._engine = engine
        self._object_store = object_store
        self._clock = clock or SystemClock()
        self._before_commit = before_commit
        self._catalog = cast(Table, SourceCatalog.__table__)
        self._snapshots = cast(Table, Snapshot.__table__)
        self._runs = cast(Table, IngestionRun.__table__)

    def promote(
        self,
        *,
        source_catalog_id: UUID,
        run_id: UUID,
        stored: StoredObject,
        manifest: SnapshotManifest,
    ) -> PromotionResult:
        """Vérifier l'objet, publier son pointeur et ne rendre qu'après commit."""

        self._verify_stored_object(stored=stored, manifest=manifest)
        committed_at = self._clock.now().value
        try:
            with self._engine.begin() as connection:
                result = self._promote_in_transaction(
                    connection=connection,
                    source_catalog_id=source_catalog_id,
                    run_id=run_id,
                    stored=stored,
                    manifest=manifest,
                    committed_at=committed_at,
                )
                if self._before_commit is not None:
                    self._before_commit(connection)
        except AtomicPromotionFailed:
            raise
        except Exception as error:
            raise self._failure(
                manifest,
                "transaction",
                "la transaction de promotion a échoué",
                error,
            ) from error
        return result

    def _promote_in_transaction(
        self,
        *,
        connection: Connection,
        source_catalog_id: UUID,
        run_id: UUID,
        stored: StoredObject,
        manifest: SnapshotManifest,
        committed_at: datetime,
    ) -> PromotionResult:
        catalog = (
            connection.execute(
                select(self._catalog)
                .where(self._catalog.c.id == source_catalog_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if catalog is None:
            raise LookupError("entrée de catalogue introuvable")
        if (
            catalog["provider"] != manifest.provider
            or int(catalog["season_year"]) != manifest.season_year
            or catalog["drive_file_id"] != manifest.drive_file_id
        ):
            raise ValueError("le manifeste ne correspond pas au catalogue")

        run = (
            connection.execute(
                select(self._runs).where(self._runs.c.id == run_id).with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if run is None or run["source_catalog_id"] != source_catalog_id:
            raise LookupError("run de promotion introuvable")
        if run["status"] != "running" or run["finished_at"] is not None:
            raise ValueError("le run de promotion doit être running")

        existing = (
            connection.execute(
                select(self._snapshots).where(
                    self._snapshots.c.source_catalog_id == source_catalog_id,
                    self._snapshots.c.sha256 == manifest.sha256,
                )
            )
            .mappings()
            .one_or_none()
        )
        reused = existing is not None
        if existing is not None:
            if existing["status"] != "validated":
                raise ValueError("le contenu existe dans un état non publiable")
            snapshot_id = cast(UUID, existing["id"])
        else:
            snapshot_id = uuid4()
            connection.execute(
                insert(self._snapshots).values(
                    id=snapshot_id,
                    source_catalog_id=source_catalog_id,
                    year=manifest.season_year,
                    source_file_id=manifest.drive_file_id,
                    status="validated",
                    sha256=manifest.sha256,
                    byte_size=manifest.byte_size,
                    content_type=manifest.content_type_observed,
                    object_key=stored.object_key,
                    received_at=manifest.downloaded_at,
                    validated_at=committed_at,
                    failure_reason=None,
                    manifest=manifest.to_dict(),
                    created_at=committed_at,
                )
            )

        previous_snapshot_id = cast(UUID | None, catalog["current_snapshot_id"])
        connection.execute(
            update(self._catalog)
            .where(self._catalog.c.id == source_catalog_id)
            .values(current_snapshot_id=snapshot_id, updated_at=committed_at)
        )
        counters = dict(cast(dict[str, Any], run["counters"]))
        counters.update(
            {
                "snapshotPromoted": 0 if reused else 1,
                "snapshotReused": 1 if reused else 0,
            }
        )
        updated = connection.execute(
            update(self._runs)
            .where(self._runs.c.id == run_id, self._runs.c.status == "running")
            .values(
                snapshot_id=snapshot_id,
                status="succeeded",
                finished_at=committed_at,
                error_code=None,
                error_detail=None,
                counters=counters,
            )
        )
        if updated.rowcount != 1:
            raise RuntimeError("le run n'a pas pu être clôturé")
        return PromotionResult(
            snapshot_id=snapshot_id,
            source_catalog_id=source_catalog_id,
            run_id=run_id,
            previous_snapshot_id=previous_snapshot_id,
            object_key=stored.object_key,
            sha256=stored.sha256,
            committed_at=committed_at,
            reused=reused,
        )

    def _verify_stored_object(
        self,
        *,
        stored: StoredObject,
        manifest: SnapshotManifest,
    ) -> None:
        if manifest.quality_status == "failed":
            raise self._failure(
                manifest,
                "quality",
                "un rapport qualité bloquant ne peut pas être promu",
            )
        try:
            stored_size = stored.source_path.stat().st_size
        except OSError as error:
            raise self._failure(
                manifest,
                "object-metadata",
                "les métadonnées de l'objet stocké sont indisponibles",
                error,
            ) from error
        if (
            stored.year != manifest.season_year
            or stored.sha256 != manifest.sha256
            or stored_size != manifest.byte_size
        ):
            raise self._failure(
                manifest,
                "object-metadata",
                "l'objet stocké ne correspond pas au manifeste",
            )
        try:
            with self._object_store.open_source(
                year=stored.year,
                sha256=stored.sha256,
            ) as stream:
                digest = hashlib.sha256()
                while chunk := stream.read(_READ_CHUNK_SIZE):
                    digest.update(chunk)
        except Exception as error:
            raise self._failure(
                manifest,
                "object-read",
                "l'objet stocké ne peut pas être relu",
                error,
            ) from error
        if digest.hexdigest() != manifest.sha256:
            raise self._failure(
                manifest,
                "object-hash",
                "l'objet stocké a changé avant la promotion",
            )

    @staticmethod
    def _failure(
        manifest: SnapshotManifest,
        operation: str,
        message: str,
        error: Exception | None = None,
    ) -> AtomicPromotionFailed:
        context: dict[str, str] = {"operation": operation}
        if error is not None:
            context["errorType"] = type(error).__name__
        return AtomicPromotionFailed(
            message,
            transport=manifest.transport,
            source_id=manifest.drive_file_id,
            retryable=False,
            context=context,
        )
