"""File transactionnelle et jetons de propriété renouvelables, sans broker externe."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import Engine, and_, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from metiquo.db.ops_models import JobRecord
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.locks import try_transaction_lock
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime
from metiquo.worker.retry import RetryPolicy


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
    rerun_of: UUID | None
    reason: str | None


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
        row.rerun_of,
        row.reason,
    )


class PostgresJobQueue:
    def __init__(
        self,
        engine: Engine,
        *,
        clock: Clock | None = None,
        lease_duration: timedelta = timedelta(seconds=60),
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        if lease_duration <= timedelta(0):
            raise ValueError("Le bail doit être positif")
        self.engine, self.clock, self.lease_duration = (
            engine,
            clock or SystemClock(),
            lease_duration,
        )
        self.retry_policy = retry_policy or RetryPolicy()

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
        rerun_of: UUID | None = None,
        reason: str | None = None,
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
            or (reason is not None and (not reason.strip() or len(reason) > 400))
            or (rerun_of is not None and reason is None)
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
                **({"reason": reason} if reason is not None else {}),
                **({"rerunOf": str(rerun_of), "reason": reason} if rerun_of is not None else {}),
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
                    rerun_of=rerun_of,
                    reason=reason,
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
                if row.cancel_requested:
                    row.status, row.finished_at, row.error_code = "cancelled", now, "CANCELLED"
                    row.owner, row.lease_token, row.lease_expires_at = None, None, None
                    session.flush()
                    continue
                if not try_transaction_lock(connection, row.scope):
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

    def request_cancel(self, job_id: UUID) -> StoredJob:
        with self.engine.begin() as connection, Session(bind=connection) as session:
            row = session.get(JobRecord, job_id, with_for_update=True)
            if row is None:
                raise BusinessError(ErrorCode.NOT_FOUND, "Job introuvable")
            if row.status in {"queued", "running"}:
                row.cancel_requested = True
                if row.status == "queued":
                    row.status, row.finished_at, row.error_code = (
                        "cancelled",
                        self.clock.now().value,
                        "CANCELLED",
                    )
                session.flush()
            return _stored(row)

    def acknowledge_cancel(self, job: StoredJob) -> bool:
        return self._owned_update(
            job,
            status="cancelled",
            cancel_requested=True,
            error_code="CANCELLED",
            finished_at=self.clock.now().value,
            owner=None,
            lease_token=None,
            lease_expires_at=None,
        )

    def rerun(self, job_id: UUID, *, key: str, actor: str, reason: str) -> StoredJob:
        previous = self.get(job_id)
        if previous.status not in {"failed", "dead", "cancelled"}:
            raise BusinessError(
                ErrorCode.CONFLICT, "Seul un job terminé sans succès peut être relancé"
            )
        return self.enqueue(
            previous.job_type,
            previous.payload,
            key=key,
            scope=previous.scope,
            actor=actor,
            max_attempts=previous.max_attempts,
            trace_id=previous.trace_id,
            rerun_of=job_id,
            reason=reason,
        )

    def release_unstarted(self, job: StoredJob) -> bool:
        """Rendre une prise dont le handler n'a pas commencé, sans consommer d'essai."""
        return self._owned_update(
            job,
            status="queued",
            attempt=job.attempt - 1,
            owner=None,
            lease_token=None,
            lease_expires_at=None,
        )

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

    def fail(self, job: StoredJob, error_code: str, *, retryable: bool = False) -> bool:
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error_code) is None:
            raise ValueError("Code d'erreur invalide")
        retry = retryable and job.attempt < job.max_attempts
        now = self.clock.now().value
        return self._owned_update(
            job,
            status="queued" if retry else "dead" if retryable else "failed",
            error_code=error_code,
            scheduled_at=now + self.retry_policy.delay(job.job_id, job.attempt)
            if retry
            else job.scheduled_at,
            finished_at=None if retry else now,
            owner=None,
            lease_token=None,
            lease_expires_at=None,
        )

    def _owned_update(self, job: StoredJob, **values: object) -> bool:
        if job.lease_token is None:
            return False
        with self.engine.begin() as connection, Session(bind=connection) as session:
            row = session.scalar(
                select(JobRecord)
                .where(
                    JobRecord.id == job.job_id,
                    JobRecord.status == "running",
                    JobRecord.owner == job.owner,
                    JobRecord.lease_token == job.lease_token,
                    JobRecord.lease_expires_at > self.clock.now().value,
                )
                .with_for_update()
            )
            if row is None:
                return False
            if row.cancel_requested and values.get("status") in {
                "queued",
                "succeeded",
                "failed",
                "dead",
            }:
                values.update(
                    status="cancelled", finished_at=self.clock.now().value, error_code="CANCELLED"
                )
            for name, value in values.items():
                setattr(row, name, value)
            session.flush()
            return True
