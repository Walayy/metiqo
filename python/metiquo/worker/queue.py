"""File transactionnelle et jetons de propriété renouvelables, sans broker externe."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import Engine, and_, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from metiquo.db.ops_models import JobRecord
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime


@dataclass(frozen=True, slots=True)
class StoredJob:
    job_id: UUID
    job_type: str
    scope: str
    payload: dict[str, object]
    actor: str
    trace_id: UUID
    status: str
    attempt: int
    max_attempts: int
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    owner: str | None
    lease_token: UUID | None
    cancel_requested: bool
    error_code: str | None
    result: dict[str, object]


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def job_lock_id(job_id: UUID) -> int:
    return int.from_bytes(hashlib.sha256(f"job:{job_id}".encode()).digest()[:8], signed=True)


def _stored(row: JobRecord) -> StoredJob:
    return StoredJob(
        row.id,
        row.job_type,
        row.scope,
        row.payload,
        row.actor,
        row.trace_id,
        row.status,
        row.attempt,
        row.max_attempts,
        row.scheduled_at,
        row.started_at,
        row.finished_at,
        row.heartbeat_at,
        row.lease_expires_at,
        row.owner,
        row.lease_token,
        row.cancel_requested,
        row.error_code,
        row.result,
    )


class PostgresJobQueue:
    def __init__(
        self,
        engine: Engine,
        *,
        clock: Clock | None = None,
        lease_duration: timedelta = timedelta(seconds=60),
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("Le bail doit être positif")
        self.engine, self.clock, self.lease_duration = (
            engine,
            clock or SystemClock(),
            lease_duration,
        )

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, object],
        *,
        key: str,
        scope: str,
        actor: str = "worker",
        scheduled_at: datetime | None = None,
        max_attempts: int = 3,
        trace_id: UUID | None = None,
    ) -> StoredJob:
        if (
            re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", job_type) is None
            or not key.strip()
            or len(key) > 255
            or not scope.strip()
            or len(scope) > 255
            or not actor.strip()
            or len(actor) > 255
            or not 1 <= max_attempts <= 20
        ):
            raise BusinessError(ErrorCode.INVALID_INPUT, "Requête de job invalide")
        now = self.clock.now().value
        scheduled = normalize_utc_datetime(scheduled_at) if scheduled_at else now
        identity = _fingerprint({"key": key})
        request = _fingerprint(
            {
                "type": job_type,
                "payload": payload,
                "scope": scope,
                "actor": actor,
                "scheduledAt": scheduled_at.isoformat() if scheduled_at else None,
                "maxAttempts": max_attempts,
            }
        )
        with self.engine.begin() as connection, Session(bind=connection) as session:
            connection.execute(
                insert(JobRecord)
                .values(
                    id=uuid5(NAMESPACE_URL, f"metiquo:job:{identity}"),
                    job_type=job_type,
                    scope=scope,
                    payload=payload,
                    actor=actor,
                    trace_id=trace_id or uuid4(),
                    idempotency_fingerprint=identity,
                    request_fingerprint=request,
                    status="queued",
                    attempt=0,
                    max_attempts=max_attempts,
                    created_at=now,
                    scheduled_at=scheduled,
                    cancel_requested=False,
                    result={},
                )
                .on_conflict_do_nothing(index_elements=["idempotency_fingerprint"])
            )
            row = session.scalar(
                select(JobRecord).where(JobRecord.idempotency_fingerprint == identity)
            )
            assert row is not None
            if row.request_fingerprint != request:
                raise BusinessError(ErrorCode.CONFLICT, "La clé désigne un autre job")
            return _stored(row)

    def get(self, job_id: UUID) -> StoredJob:
        with Session(self.engine) as session:
            row = session.get(JobRecord, job_id)
            if row is None:
                raise BusinessError(ErrorCode.NOT_FOUND, "Job introuvable")
            return _stored(row)

    def claim(self, owner: str) -> StoredJob | None:
        if not owner.strip() or len(owner) > 255:
            raise ValueError("Worker invalide")
        now = self.clock.now().value
        with self.engine.begin() as connection, Session(bind=connection) as session:
            skipped: list[UUID] = []
            for _ in range(32):
                row = session.scalar(
                    select(JobRecord)
                    .where(
                        JobRecord.id.not_in(skipped),
                        JobRecord.cancel_requested.is_(False),
                        or_(
                            and_(JobRecord.status == "queued", JobRecord.scheduled_at <= now),
                            and_(JobRecord.status == "running", JobRecord.lease_expires_at <= now),
                        ),
                    )
                    .order_by(JobRecord.scheduled_at, JobRecord.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if row is None:
                    return None
                skipped.append(row.id)
                if not connection.scalar(
                    text("SELECT pg_try_advisory_xact_lock(:lock)"), {"lock": job_lock_id(row.id)}
                ):
                    continue
                if row.attempt >= row.max_attempts:
                    row.status, row.finished_at, row.error_code = "dead", now, "LEASE_EXHAUSTED"
                    row.owner, row.lease_token, row.lease_expires_at = None, None, None
                    session.flush()
                    continue
                break
            else:
                return None
            row.status, row.owner, row.lease_token = "running", owner, uuid4()
            row.attempt += 1
            row.started_at, row.heartbeat_at, row.lease_expires_at = (
                now,
                now,
                now + self.lease_duration,
            )
            row.error_code = None
            session.flush()
            return _stored(row)

    def heartbeat(self, job: StoredJob) -> bool:
        now = self.clock.now().value
        return self._owned_update(job, heartbeat_at=now, lease_expires_at=now + self.lease_duration)

    def complete(self, job: StoredJob, result: dict[str, object]) -> bool:
        _fingerprint(result)
        return self._owned_update(
            job,
            status="succeeded",
            result=result,
            finished_at=self.clock.now().value,
            owner=None,
            lease_token=None,
            lease_expires_at=None,
        )

    def fail(self, job: StoredJob, error_code: str) -> bool:
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error_code) is None:
            raise ValueError("Code d'erreur invalide")
        return self._owned_update(
            job,
            status="failed",
            error_code=error_code,
            finished_at=self.clock.now().value,
            owner=None,
            lease_token=None,
            lease_expires_at=None,
        )

    def _owned_update(self, job: StoredJob, **values: object) -> bool:
        if job.lease_token is None:
            return False
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(JobRecord)
                .where(
                    JobRecord.id == job.job_id,
                    JobRecord.status == "running",
                    JobRecord.owner == job.owner,
                    JobRecord.lease_token == job.lease_token,
                    JobRecord.lease_expires_at > self.clock.now().value,
                )
                .values(**values)
                .returning(JobRecord.id)
            ).scalar_one_or_none()
            return changed is not None
