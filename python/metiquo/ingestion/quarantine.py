"""Conservation et résolution auditée des snapshots invalides."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Table, insert, select, update
from sqlalchemy.engine import RowMapping

from metiquo.db.raw_models import QuarantineItem, Snapshot, SourceCatalog
from metiquo.foundation.time import Clock, SystemClock
from metiquo.ingestion.object_store import ObjectStore, SourceKind

type QuarantineDecision = Literal["accepted", "rejected"]

_READ_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class SnapshotRecord:
    id: UUID
    source_catalog_id: UUID
    year: int
    status: str
    sha256: str
    object_key: str
    validated_at: datetime | None


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    item_id: UUID
    snapshot_id: UUID
    run_id: UUID
    reason_code: str
    object_key: str
    sha256: str
    status: str


@dataclass(frozen=True, slots=True)
class QuarantineAuditEvent:
    action: str
    item_id: UUID
    snapshot_id: UUID
    actor: str
    reason: str
    occurred_at: datetime


class QuarantineAuditSink(Protocol):
    def record(self, event: QuarantineAuditEvent) -> None: ...


class SnapshotReader:
    """Lecture qui exclut structurellement received, failed et quarantined."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._table = cast(Table, Snapshot.__table__)
        self._catalog = cast(Table, SourceCatalog.__table__)

    def current(self, source_catalog_id: UUID) -> SnapshotRecord | None:
        """Lire uniquement le snapshot explicitement publié et encore validé."""

        row = (
            self._connection.execute(
                select(self._table)
                .join(
                    self._catalog,
                    self._catalog.c.current_snapshot_id == self._table.c.id,
                )
                .where(
                    self._catalog.c.id == source_catalog_id,
                    self._table.c.source_catalog_id == source_catalog_id,
                    self._table.c.status == "validated",
                )
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        return self._to_record(row) if row is not None else None

    def latest_validated(self, source_catalog_id: UUID) -> SnapshotRecord | None:
        row = (
            self._connection.execute(
                select(self._table)
                .where(
                    self._table.c.source_catalog_id == source_catalog_id,
                    self._table.c.status == "validated",
                )
                .order_by(self._table.c.validated_at.desc(), self._table.c.created_at.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return self._to_record(row)

    @staticmethod
    def _to_record(row: RowMapping) -> SnapshotRecord:
        return SnapshotRecord(
            id=row["id"],
            source_catalog_id=row["source_catalog_id"],
            year=int(row["year"]),
            status=str(row["status"]),
            sha256=str(row["sha256"]),
            object_key=str(row["object_key"]),
            validated_at=row["validated_at"],
        )


class QuarantineService:
    """Écrire le contenu invalide sans promouvoir ni remplacer le validé actif."""

    def __init__(
        self,
        *,
        connection: Connection,
        object_store: ObjectStore,
        clock: Clock | None = None,
    ) -> None:
        self._connection = connection
        self._object_store = object_store
        self._clock = clock or SystemClock()
        self._snapshots = cast(Table, Snapshot.__table__)
        self._items = cast(Table, QuarantineItem.__table__)

    def capture(
        self,
        *,
        source_catalog_id: UUID,
        run_id: UUID,
        year: int,
        source_file_id: str,
        payload_path: Path,
        reason_code: str,
        diagnostic: Mapping[str, object],
        source_kind: SourceKind = "bin",
        content_type: str | None = None,
    ) -> QuarantineRecord:
        if not reason_code.strip():
            raise ValueError("reason_code de quarantaine requis")
        observed_at = self._clock.now().value
        stored = self._object_store.put_source(
            year=year,
            chunks=_file_chunks(payload_path),
            source_kind=source_kind,
            manifest={
                "status": "quarantined",
                "reasonCode": reason_code,
                "sourceFileId": source_file_id,
                "capturedAt": observed_at.isoformat().replace("+00:00", "Z"),
            },
            quality_report=diagnostic,
        )
        snapshot_id = uuid4()
        item_id = uuid4()
        object_key = f"quarantine/{stored.object_key}"
        manifest: dict[str, Any] = {
            "quarantined": True,
            "reasonCode": reason_code,
            "diagnostic": dict(diagnostic),
        }
        self._connection.execute(
            insert(self._snapshots).values(
                id=snapshot_id,
                source_catalog_id=source_catalog_id,
                year=year,
                source_file_id=source_file_id,
                status="quarantined",
                sha256=stored.sha256,
                byte_size=stored.source_path.stat().st_size,
                content_type=content_type,
                object_key=object_key,
                received_at=observed_at,
                validated_at=None,
                failure_reason=reason_code,
                manifest=manifest,
                created_at=observed_at,
            )
        )
        self._connection.execute(
            insert(self._items).values(
                id=item_id,
                snapshot_id=snapshot_id,
                run_id=run_id,
                reason_code=reason_code,
                object_key=object_key,
                payload_sha256=stored.sha256,
                diagnostic=dict(diagnostic),
                status="pending",
                quarantined_at=observed_at,
            )
        )
        return QuarantineRecord(
            item_id=item_id,
            snapshot_id=snapshot_id,
            run_id=run_id,
            reason_code=reason_code,
            object_key=object_key,
            sha256=stored.sha256,
            status="pending",
        )

    def resolve(
        self,
        *,
        item_id: UUID,
        decision: QuarantineDecision,
        actor: str,
        reason: str,
        audit_sink: QuarantineAuditSink,
    ) -> QuarantineAuditEvent:
        if decision not in {"accepted", "rejected"}:
            raise ValueError("décision de quarantaine invalide")
        if not actor.strip() or not reason.strip():
            raise ValueError("acteur et motif explicites requis")
        row = (
            self._connection.execute(
                select(self._items).where(self._items.c.id == item_id).with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise LookupError("quarantaine introuvable")
        if row["status"] != "pending":
            raise ValueError("quarantaine déjà résolue")
        occurred_at = self._clock.now().value
        self._connection.execute(
            update(self._items)
            .where(self._items.c.id == item_id)
            .values(
                status=decision,
                resolved_at=occurred_at,
                resolved_by=actor,
                resolution_reason=reason,
            )
        )
        event = QuarantineAuditEvent(
            action=f"quarantine.{decision}",
            item_id=item_id,
            snapshot_id=row["snapshot_id"],
            actor=actor,
            reason=reason,
            occurred_at=occurred_at,
        )
        audit_sink.record(event)
        return event


def _file_chunks(path: Path) -> Iterable[bytes]:
    with path.open("rb") as stream:
        while chunk := stream.read(_READ_CHUNK_SIZE):
            yield chunk
