"""Orchestration durable et concurrente des synchronisations multi-années."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, Table, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.raw_models import BackfillJob, BackfillYear
from metiquo.foundation.time import Clock, SystemClock


@dataclass(frozen=True, slots=True)
class YearSyncResult:
    run_id: UUID


class YearSyncProcessor(Protocol):
    def sync_year(
        self,
        *,
        provider: str,
        dataset: str,
        year: int,
        job_id: UUID,
        attempt: int,
    ) -> YearSyncResult: ...


@dataclass(frozen=True, slots=True)
class BackfillYearState:
    year: int
    status: str
    attempts: int
    last_run_id: UUID | None
    error_code: str | None


@dataclass(frozen=True, slots=True)
class BackfillResult:
    job_id: UUID
    provider: str
    dataset: str
    from_year: int
    to_year: int
    status: str
    years: tuple[BackfillYearState, ...]


class BackfillOrchestrator:
    """Reprendre les années non terminées sous verrou advisory de session."""

    def __init__(
        self,
        *,
        engine: Engine,
        processor: YearSyncProcessor,
        clock: Clock | None = None,
    ) -> None:
        self._engine = engine
        self._processor = processor
        self._clock = clock or SystemClock()
        self._jobs = cast(Table, BackfillJob.__table__)
        self._years = cast(Table, BackfillYear.__table__)

    def run(
        self,
        *,
        provider: str,
        dataset: str,
        from_year: int,
        to_year: int,
    ) -> BackfillResult:
        if not provider.strip() or not dataset.strip():
            raise ValueError("provider et dataset sont requis")
        if not 2014 <= from_year <= to_year <= 2200:
            raise ValueError("plage d'années de backfill invalide")
        job_id = self._ensure_job(
            provider=provider,
            dataset=dataset,
            from_year=from_year,
            to_year=to_year,
        )
        for year_state in self._year_states(job_id):
            if year_state.status == "succeeded":
                continue
            self._run_year_with_lock(
                job_id=job_id,
                provider=provider,
                dataset=dataset,
                year=year_state.year,
            )
        self._refresh_job_status(job_id)
        return self._result(job_id)

    def _ensure_job(
        self,
        *,
        provider: str,
        dataset: str,
        from_year: int,
        to_year: int,
    ) -> UUID:
        now = self._clock.now().value
        request_key_hash = hashlib.sha256(
            f"{provider}\0{dataset}\0{from_year}\0{to_year}".encode()
        ).hexdigest()
        proposed_job_id = uuid4()
        with self._engine.begin() as connection:
            connection.execute(
                insert(self._jobs)
                .values(
                    id=proposed_job_id,
                    provider=provider,
                    dataset=dataset,
                    from_year=from_year,
                    to_year=to_year,
                    request_key_hash=request_key_hash,
                    status="running",
                    finished_at=None,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=[self._jobs.c.request_key_hash])
            )
            job_id = connection.execute(
                select(self._jobs.c.id).where(self._jobs.c.request_key_hash == request_key_hash)
            ).scalar_one()
            connection.execute(
                insert(self._years)
                .values(
                    [
                        {
                            "id": uuid4(),
                            "job_id": job_id,
                            "year": year,
                            "status": "pending",
                            "attempts": 0,
                            "created_at": now,
                            "updated_at": now,
                        }
                        for year in range(from_year, to_year + 1)
                    ]
                )
                .on_conflict_do_nothing(index_elements=[self._years.c.job_id, self._years.c.year])
            )
            incomplete = connection.execute(
                select(func.count())
                .select_from(self._years)
                .where(
                    self._years.c.job_id == job_id,
                    self._years.c.status != "succeeded",
                )
            ).scalar_one()
            if incomplete:
                connection.execute(
                    update(self._jobs)
                    .where(self._jobs.c.id == job_id)
                    .values(status="running", finished_at=None, updated_at=now)
                )
        return cast(UUID, job_id)

    def _run_year_with_lock(
        self,
        *,
        job_id: UUID,
        provider: str,
        dataset: str,
        year: int,
    ) -> None:
        lock_key = _advisory_lock_key(provider, year)
        with self._engine.connect() as connection:
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": lock_key},
                ).scalar_one()
            )
            connection.commit()
            if not acquired:
                return
            try:
                attempt = self._mark_running(connection, job_id, year)
                try:
                    result = self._processor.sync_year(
                        provider=provider,
                        dataset=dataset,
                        year=year,
                        job_id=job_id,
                        attempt=attempt,
                    )
                except Exception as error:
                    self._mark_failed(connection, job_id, year, error)
                else:
                    self._mark_succeeded(connection, job_id, year, result)
            finally:
                if connection.in_transaction():
                    connection.rollback()
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": lock_key},
                )
                connection.commit()

    def _mark_running(self, connection: Connection, job_id: UUID, year: int) -> int:
        now = self._clock.now().value
        with connection.begin():
            row = connection.execute(
                update(self._years)
                .where(
                    self._years.c.job_id == job_id,
                    self._years.c.year == year,
                    self._years.c.status != "succeeded",
                )
                .values(
                    status="running",
                    attempts=self._years.c.attempts + 1,
                    started_at=now,
                    finished_at=None,
                    error_code=None,
                    updated_at=now,
                )
                .returning(self._years.c.attempts)
            ).one_or_none()
            if row is None:
                raise RuntimeError("checkpoint annuel absent ou déjà terminé")
            return int(row[0])

    def _mark_succeeded(
        self,
        connection: Connection,
        job_id: UUID,
        year: int,
        result: YearSyncResult,
    ) -> None:
        now = self._clock.now().value
        with connection.begin():
            connection.execute(
                update(self._years)
                .where(self._years.c.job_id == job_id, self._years.c.year == year)
                .values(
                    status="succeeded",
                    last_run_id=result.run_id,
                    error_code=None,
                    finished_at=now,
                    updated_at=now,
                )
            )

    def _mark_failed(
        self,
        connection: Connection,
        job_id: UUID,
        year: int,
        error: Exception,
    ) -> None:
        now = self._clock.now().value
        code = getattr(error, "code", None)
        error_code = str(code) if code is not None else type(error).__name__.upper()
        with connection.begin():
            connection.execute(
                update(self._years)
                .where(self._years.c.job_id == job_id, self._years.c.year == year)
                .values(
                    status="failed",
                    error_code=error_code[:128],
                    finished_at=now,
                    updated_at=now,
                )
            )

    def _refresh_job_status(self, job_id: UUID) -> None:
        now = self._clock.now().value
        with self._engine.begin() as connection:
            statuses = tuple(
                connection.execute(
                    select(self._years.c.status).where(self._years.c.job_id == job_id)
                ).scalars()
            )
            if statuses and all(status == "succeeded" for status in statuses):
                status = "succeeded"
                finished_at: datetime | None = now
            elif any(status == "failed" for status in statuses):
                status = "failed"
                finished_at = now
            else:
                status = "running"
                finished_at = None
            connection.execute(
                update(self._jobs)
                .where(self._jobs.c.id == job_id)
                .values(status=status, finished_at=finished_at, updated_at=now)
            )

    def _year_states(self, job_id: UUID) -> tuple[BackfillYearState, ...]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(self._years)
                    .where(self._years.c.job_id == job_id)
                    .order_by(self._years.c.year)
                )
                .mappings()
                .all()
            )
        return tuple(
            BackfillYearState(
                year=int(row["year"]),
                status=str(row["status"]),
                attempts=int(row["attempts"]),
                last_run_id=row["last_run_id"],
                error_code=(str(row["error_code"]) if row["error_code"] is not None else None),
            )
            for row in rows
        )

    def _result(self, job_id: UUID) -> BackfillResult:
        with self._engine.connect() as connection:
            job = (
                connection.execute(select(self._jobs).where(self._jobs.c.id == job_id))
                .mappings()
                .one()
            )
        return BackfillResult(
            job_id=job_id,
            provider=str(job["provider"]),
            dataset=str(job["dataset"]),
            from_year=int(job["from_year"]),
            to_year=int(job["to_year"]),
            status=str(job["status"]),
            years=self._year_states(job_id),
        )


def _advisory_lock_key(provider: str, year: int) -> int:
    digest = hashlib.sha256(f"{provider}\0{year}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)
