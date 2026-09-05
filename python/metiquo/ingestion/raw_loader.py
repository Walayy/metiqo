"""Staging transactionnel et merge idempotent des lignes source."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, Table, select, text, update

from metiquo.db.raw_models import IngestionRun, Snapshot, SourceCatalog
from metiquo.foundation.time import Clock, SystemClock

_BATCH_SIZE = 1_000


class RawLoadError(RuntimeError):
    """Le snapshot publié ne peut pas être chargé sans supposition."""


@dataclass(frozen=True, slots=True)
class NaturalKeyStrategy:
    preferred_fields: tuple[str, ...] = ("gameid", "participantid")
    fallback_fields: tuple[str, ...] | None = None

    def resolve(self, header: Sequence[str]) -> tuple[tuple[str, ...], bool]:
        available = set(header)
        if self.preferred_fields and set(self.preferred_fields) <= available:
            return self.preferred_fields, False
        if self.fallback_fields and set(self.fallback_fields) <= available:
            return self.fallback_fields, True
        raise RawLoadError(
            "aucune stratégie de clé naturelle explicitement configurée ne correspond au schéma"
        )


@dataclass(frozen=True, slots=True)
class RawLoadStatistics:
    inserted: int
    updated: int
    unchanged: int
    quarantined: int
    total: int

    def to_dict(self) -> dict[str, int]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "quarantined": self.quarantined,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class RawLoadResult:
    run_id: UUID
    snapshot_id: UUID
    staging_table: str
    natural_key_fields: tuple[str, ...]
    fallback_key_used: bool
    statistics: RawLoadStatistics
    committed_at: datetime


@dataclass(frozen=True, slots=True)
class _StagedRow:
    candidate_id: UUID
    ordinal: int
    natural_key: str | None
    row_hash: str | None
    payload_json: str
    event_date: date | None
    reason_code: str | None

    def parameters(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "ordinal": self.ordinal,
            "natural_key": self.natural_key,
            "row_hash": self.row_hash,
            "payload": self.payload_json,
            "event_date": self.event_date,
            "reason_code": self.reason_code,
        }


class RawTabularLoader:
    """Charger un CSV publié via une table temporaire propre au run."""

    def __init__(
        self,
        *,
        engine: Engine,
        clock: Clock | None = None,
        key_strategy: NaturalKeyStrategy | None = None,
        batch_size: int = _BATCH_SIZE,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size doit être supérieur ou égal à 1")
        self._engine = engine
        self._clock = clock or SystemClock()
        self._key_strategy = key_strategy or NaturalKeyStrategy()
        self._batch_size = batch_size
        self._catalog = cast(Table, SourceCatalog.__table__)
        self._snapshots = cast(Table, Snapshot.__table__)
        self._runs = cast(Table, IngestionRun.__table__)

    def load(
        self,
        *,
        source_catalog_id: UUID,
        snapshot_id: UUID,
        run_id: UUID,
        csv_path: Path,
        encoding: str = "utf-8",
        delimiter: str = ",",
    ) -> RawLoadResult:
        if len(delimiter) != 1:
            raise ValueError("delimiter doit contenir exactement un caractère")
        committed_at = self._clock.now().value
        staging_table = f"oe_staging_{run_id.hex}"
        with self._engine.begin() as connection:
            provider, dataset = self._lock_and_validate_context(
                connection=connection,
                source_catalog_id=source_catalog_id,
                snapshot_id=snapshot_id,
                run_id=run_id,
            )
            self._create_staging(connection, staging_table)
            header, key_fields, fallback_used, total = self._stage_csv(
                connection=connection,
                staging_table=staging_table,
                csv_path=csv_path,
                encoding=encoding,
                delimiter=delimiter,
            )
            del header
            statistics = self._classify(
                connection=connection,
                staging_table=staging_table,
                provider=provider,
                dataset=dataset,
                total=total,
            )
            self._merge(
                connection=connection,
                staging_table=staging_table,
                provider=provider,
                dataset=dataset,
                snapshot_id=snapshot_id,
                run_id=run_id,
                committed_at=committed_at,
            )
            updated = connection.execute(
                update(self._runs)
                .where(self._runs.c.id == run_id, self._runs.c.status == "running")
                .values(
                    status="succeeded",
                    finished_at=committed_at,
                    counters=statistics.to_dict(),
                    error_code=None,
                    error_detail=None,
                )
            )
            if updated.rowcount != 1:
                raise RawLoadError("le run de chargement n'a pas pu être clôturé")
        return RawLoadResult(
            run_id=run_id,
            snapshot_id=snapshot_id,
            staging_table=staging_table,
            natural_key_fields=key_fields,
            fallback_key_used=fallback_used,
            statistics=statistics,
            committed_at=committed_at,
        )

    def _lock_and_validate_context(
        self,
        *,
        connection: Connection,
        source_catalog_id: UUID,
        snapshot_id: UUID,
        run_id: UUID,
    ) -> tuple[str, str]:
        catalog = (
            connection.execute(
                select(self._catalog)
                .where(self._catalog.c.id == source_catalog_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if catalog is None or catalog["current_snapshot_id"] != snapshot_id:
            raise RawLoadError("le snapshot demandé n'est pas le snapshot courant")
        snapshot_status = connection.execute(
            select(self._snapshots.c.status).where(
                self._snapshots.c.id == snapshot_id,
                self._snapshots.c.source_catalog_id == source_catalog_id,
            )
        ).scalar_one_or_none()
        if snapshot_status != "validated":
            raise RawLoadError("le snapshot demandé n'est pas validé")
        run = (
            connection.execute(
                select(self._runs).where(self._runs.c.id == run_id).with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if (
            run is None
            or run["source_catalog_id"] != source_catalog_id
            or run["snapshot_id"] != snapshot_id
            or run["run_kind"] != "load"
            or run["status"] != "running"
        ):
            raise RawLoadError("le run de chargement est invalide")
        return str(catalog["provider"]), str(catalog["dataset"])

    @staticmethod
    def _create_staging(connection: Connection, staging_table: str) -> None:
        connection.execute(
            text(
                f"""
                CREATE TEMP TABLE {staging_table} (
                  candidate_id uuid NOT NULL,
                  ordinal bigint NOT NULL,
                  natural_key text,
                  row_hash varchar(64),
                  payload jsonb NOT NULL,
                  event_date date,
                  reason_code varchar(128)
                ) ON COMMIT DROP
                """
            )
        )

    def _stage_csv(
        self,
        *,
        connection: Connection,
        staging_table: str,
        csv_path: Path,
        encoding: str,
        delimiter: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...], bool, int]:
        with csv_path.open("r", encoding=encoding, newline="") as stream:
            reader = csv.DictReader(stream, delimiter=delimiter)
            if reader.fieldnames is None:
                raise RawLoadError("en-tête CSV absent")
            header = tuple(reader.fieldnames)
            key_fields, fallback_used = self._key_strategy.resolve(header)
            total = self._insert_batches(
                connection,
                staging_table,
                self._rows(reader, key_fields),
            )
        return header, key_fields, fallback_used, total

    def _insert_batches(
        self,
        connection: Connection,
        staging_table: str,
        rows: Iterator[_StagedRow],
    ) -> int:
        statement = text(
            f"""
            INSERT INTO {staging_table} (
              candidate_id, ordinal, natural_key, row_hash, payload, event_date, reason_code
            ) VALUES (
              :candidate_id, :ordinal, :natural_key, :row_hash,
              CAST(:payload AS jsonb), :event_date, :reason_code
            )
            """
        )
        batch: list[dict[str, object]] = []
        total = 0
        for row in rows:
            batch.append(row.parameters())
            if len(batch) == self._batch_size:
                connection.execute(statement, batch)
                total += len(batch)
                batch.clear()
        if batch:
            connection.execute(statement, batch)
            total += len(batch)
        return total

    @staticmethod
    def _rows(
        reader: csv.DictReader[str],
        key_fields: tuple[str, ...],
    ) -> Iterator[_StagedRow]:
        for ordinal, source_row in enumerate(reader, start=1):
            malformed = None in source_row or any(value is None for value in source_row.values())
            payload = {
                str(name): value
                for name, value in source_row.items()
                if name is not None and value is not None
            }
            key_values = tuple(payload.get(field, "").strip() for field in key_fields)
            missing_key = any(not value for value in key_values)
            reason_code = (
                "ROW_WIDTH_INVALID" if malformed else "NATURAL_KEY_MISSING" if missing_key else None
            )
            natural_key = None if missing_key else _canonical_json(key_values)
            payload_json = _canonical_json(payload)
            yield _StagedRow(
                candidate_id=uuid4(),
                ordinal=ordinal,
                natural_key=natural_key,
                row_hash=None
                if reason_code is not None
                else hashlib.sha256(payload_json.encode()).hexdigest(),
                payload_json=payload_json,
                event_date=_event_date(payload),
                reason_code=reason_code,
            )

    @staticmethod
    def _classify(
        *,
        connection: Connection,
        staging_table: str,
        provider: str,
        dataset: str,
        total: int,
    ) -> RawLoadStatistics:
        counts = (
            connection.execute(
                text(
                    f"""
                WITH staged AS (
                  SELECT source.*,
                         count(*) OVER (PARTITION BY natural_key) AS key_count
                  FROM {staging_table} AS source
                  WHERE reason_code IS NULL
                ), unique_staged AS (
                  SELECT * FROM staged WHERE key_count = 1
                )
                SELECT
                  count(*) FILTER (WHERE canonical.id IS NULL) AS inserted,
                  count(*) FILTER (
                    WHERE canonical.id IS NOT NULL
                      AND canonical.row_hash IS DISTINCT FROM source.row_hash
                  ) AS updated,
                  count(*) FILTER (
                    WHERE canonical.id IS NOT NULL
                      AND canonical.row_hash = source.row_hash
                  ) AS unchanged,
                  (SELECT count(*) FROM {staging_table} WHERE reason_code IS NOT NULL)
                    + (SELECT count(*) FROM staged WHERE key_count > 1) AS quarantined
                FROM unique_staged AS source
                LEFT JOIN raw.canonical_rows AS canonical
                  ON canonical.provider = :provider
                 AND canonical.dataset = :dataset
                 AND canonical.natural_key = source.natural_key
                """
                ),
                {"provider": provider, "dataset": dataset},
            )
            .mappings()
            .one()
        )
        return RawLoadStatistics(
            inserted=int(counts["inserted"]),
            updated=int(counts["updated"]),
            unchanged=int(counts["unchanged"]),
            quarantined=int(counts["quarantined"]),
            total=total,
        )

    @staticmethod
    def _merge(
        *,
        connection: Connection,
        staging_table: str,
        provider: str,
        dataset: str,
        snapshot_id: UUID,
        run_id: UUID,
        committed_at: datetime,
    ) -> None:
        connection.execute(
            text(
                f"""
                INSERT INTO raw.canonical_rows (
                  id, provider, dataset, natural_key, row_hash, payload, event_date,
                  source_snapshot_id, source_run_id, revision, created_at, updated_at
                )
                SELECT source.candidate_id, :provider, :dataset, source.natural_key,
                       source.row_hash, source.payload, source.event_date,
                       :snapshot_id, :run_id, 1, :committed_at, :committed_at
                FROM (
                  SELECT staged.*,
                         count(*) OVER (PARTITION BY natural_key) AS key_count
                  FROM {staging_table} AS staged
                  WHERE reason_code IS NULL
                ) AS source
                WHERE source.key_count = 1
                ON CONFLICT ON CONSTRAINT uq_canonical_rows_natural_key DO UPDATE SET
                  row_hash = EXCLUDED.row_hash,
                  payload = EXCLUDED.payload,
                  event_date = EXCLUDED.event_date,
                  source_snapshot_id = EXCLUDED.source_snapshot_id,
                  source_run_id = EXCLUDED.source_run_id,
                  revision = raw.canonical_rows.revision + 1,
                  updated_at = EXCLUDED.updated_at
                WHERE raw.canonical_rows.row_hash IS DISTINCT FROM EXCLUDED.row_hash
                """
            ),
            {
                "provider": provider,
                "dataset": dataset,
                "snapshot_id": snapshot_id,
                "run_id": run_id,
                "committed_at": committed_at,
            },
        )


def _canonical_json(value: Mapping[str, Any] | Sequence[str]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_date(payload: Mapping[str, str]) -> date | None:
    candidate = payload.get("date", "").strip()[:10]
    if not candidate:
        return None
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        return None
