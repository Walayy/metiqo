"""Projections admin paginées des jobs et de l'audit, sans exposer les payloads."""

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Engine, text

from metiquo.contracts import AuditEntry, JobSummary
from metiquo.contracts.base import ContractModel

_JOBS = """
    SELECT id, coalesce(started_at, created_at) AS sort_at, jsonb_build_object(
      'jobId', id, 'name', job_type, 'status', status,
      'lastRunAt', coalesce(finished_at, started_at),
      'dataMode', 'real', 'scope', scope, 'attempt', attempt, 'maxAttempts', max_attempts,
      'scheduledAt', scheduled_at, 'heartbeatAt', heartbeat_at, 'leaseExpiresAt', lease_expires_at,
      'errorCode', error_code, 'cancelRequested', cancel_requested, 'traceId', trace_id,
      'runId', result->>'runId'
    ) AS document FROM ops.jobs
    UNION ALL
    SELECT id, updated_at, jsonb_build_object('jobId', id, 'name', name, 'status', status,
      'lastRunAt', coalesce(finished_at, updated_at), 'dataMode', 'real') FROM ml.model_action_jobs
    UNION ALL
    SELECT id, updated_at, jsonb_build_object('jobId', id,
      'name', concat('oe-backfill-', from_year, '-', to_year), 'status', status,
      'lastRunAt', coalesce(finished_at, updated_at), 'dataMode', 'real') FROM raw.backfill_jobs
"""

_AUDITS = """
    SELECT a.id, coalesce(m.occurred_at, r.occurred_at, a.occurred_at) AS sort_at,
    jsonb_build_object(
      'auditId', coalesce(m.id, r.id, a.id), 'action', coalesce(m.action, r.action, a.action),
      'resourceId', coalesce(m.resource_id, r.resource_id, a.target_id),
      'idempotencyFingerprint', coalesce(a.after_refs->>'idempotency_fingerprint',
        encode(sha256(convert_to(a.id::text, 'UTF8')), 'hex')),
      'occurredAt', coalesce(m.occurred_at, r.occurred_at, a.occurred_at),
      'dataMode', 'real', 'actor', a.actor, 'reason', r.reason,
      'impact', coalesce(r.impact, '{}'::jsonb) || jsonb_build_object(
        'traceId', a.trace_id, 'targetType', a.target_type,
        'beforeRefs', a.before_refs, 'afterRefs', a.after_refs, 'recordedAt', a.occurred_at)
    ) AS document FROM ops.audit_events a
    LEFT JOIN ml.model_action_audits m ON a.target_type = 'ml.model_action_audits'
      AND a.target_id = m.id::text
    LEFT JOIN odds.mapping_audits r ON a.target_type = 'odds.mapping_audits'
      AND a.target_id = r.id::text
    UNION ALL
    SELECT m.id, m.occurred_at, jsonb_build_object('auditId', m.id, 'action', m.action,
      'resourceId', m.resource_id, 'idempotencyFingerprint', m.idempotency_fingerprint,
      'occurredAt', m.occurred_at, 'dataMode', 'real') FROM ml.model_action_audits m
    WHERE NOT EXISTS (SELECT 1 FROM ops.audit_events a
      WHERE a.target_type = 'ml.model_action_audits' AND a.target_id = m.id::text)
    UNION ALL
    SELECT r.id, r.occurred_at, jsonb_build_object('auditId', r.id, 'action', r.action,
      'resourceId', r.resource_id, 'idempotencyFingerprint', r.idempotency_fingerprint,
      'occurredAt', r.occurred_at, 'dataMode', 'real', 'actor', r.actor, 'reason', r.reason,
      'impact', r.impact) FROM odds.mapping_audits r
    WHERE NOT EXISTS (SELECT 1 FROM ops.audit_events a
      WHERE a.target_type = 'odds.mapping_audits' AND a.target_id = r.id::text)
"""


@dataclass(frozen=True, slots=True)
class OperationalPage[T]:
    items: tuple[T, ...]
    total: int


class PostgresOperationsRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def job(self, identity: UUID) -> JobSummary | None:
        with self.engine.connect() as connection:
            document = connection.scalar(
                text(f"WITH entries AS ({_JOBS}) SELECT document FROM entries WHERE id = :id"),
                {"id": identity},
            )
        return (
            JobSummary.model_validate_json(json.dumps(document)) if document is not None else None
        )

    def jobs(
        self, *, offset: int = 0, limit: int = 20, status: str | None = None
    ) -> OperationalPage[JobSummary]:
        return self._page(_JOBS, JobSummary, offset, limit, status=status)

    def audits(self, *, offset: int = 0, limit: int = 20) -> OperationalPage[AuditEntry]:
        return self._page(_AUDITS, AuditEntry, offset, limit)

    def _page[T: ContractModel](
        self, source: str, model: type[T], offset: int, limit: int, *, status: str | None = None
    ) -> OperationalPage[T]:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Pagination hors limites")
        prefix = (
            f"WITH entries AS ({source}), filtered AS (SELECT * FROM entries "
            "WHERE CAST(:status AS text) IS NULL OR document->>'status' = :status) "
        )
        parameters = {"offset": offset, "limit": limit, "status": status}
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            total = connection.scalar(text(prefix + "SELECT count(*) FROM filtered"), parameters)
            rows = connection.scalars(
                text(
                    prefix + "SELECT document FROM filtered ORDER BY sort_at DESC, id DESC "
                    "LIMIT :limit OFFSET :offset"
                ),
                parameters,
            )
            return OperationalPage(
                tuple(model.model_validate_json(json.dumps(row)) for row in rows), int(total or 0)
            )
