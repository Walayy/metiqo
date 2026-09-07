"""Audit des modes effectifs sans stocker de configuration privée."""

from uuid import UUID, uuid4

from sqlalchemy import Engine, insert, select, text

from metiquo.config import Settings
from metiquo.db.ops_models import AuditEventRecord
from metiquo.foundation.audit import current_audit_context
from metiquo.foundation.locks import resource_lock_key
from metiquo.foundation.time import Clock, SystemClock


def record_runtime_configuration(
    engine: Engine, settings: Settings, *, service: str, clock: Clock | None = None
) -> UUID:
    if service not in {"api", "worker", "cli"}:
        raise ValueError("Service d'audit inconnu")
    context = current_audit_context()
    after: dict[str, object] = {
        "appDataMode": settings.app_data_mode.value,
        "appEnv": settings.app_env.value,
        "authMode": str(getattr(settings, "auth_mode", "disabled")),
        "oddsProvider": settings.odds_provider.value,
        "objectStoreBackend": settings.object_store_backend.value,
    }
    with engine.begin() as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock)"),
            {"lock": resource_lock_key(f"audit:configuration:{service}")},
        )
        previous = connection.execute(
            select(AuditEventRecord.id, AuditEventRecord.after_refs)
            .where(
                AuditEventRecord.target_type == "runtime.configuration",
                AuditEventRecord.target_id == service,
            )
            .order_by(AuditEventRecord.occurred_at.desc(), AuditEventRecord.id.desc())
            .limit(1)
        ).one_or_none()
        if previous is not None and previous.after_refs == after:
            return UUID(str(previous.id))
        identity = uuid4()
        connection.execute(
            insert(AuditEventRecord).values(
                id=identity,
                actor=context.actor if context else f"system:{service}",
                action="runtime.configuration",
                target_type="runtime.configuration",
                target_id=service,
                before_refs=previous.after_refs if previous is not None else {},
                after_refs=after,
                trace_id=context.trace_id if context else uuid4(),
                occurred_at=(clock or SystemClock()).now().value,
            )
        )
        return identity
