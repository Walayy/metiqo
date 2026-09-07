"""Contexte d'audit transmis aux transactions PostgreSQL sans payload métier."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Connection, Engine, event, text


@dataclass(frozen=True, slots=True)
class AuditContext:
    actor: str
    trace_id: UUID


_CONTEXT: ContextVar[AuditContext | None] = ContextVar("audit_context", default=None)


def current_audit_context() -> AuditContext | None:
    return _CONTEXT.get()


def mutation_actor(fallback: str) -> str:
    """L'identité authentifiée prévaut sur une attribution déclarée dans un payload."""
    context = current_audit_context()
    return context.actor if context is not None and context.actor.startswith("owner:") else fallback


@contextmanager
def audit_context(*, actor: str, trace_id: UUID) -> Iterator[None]:
    if not actor.strip() or len(actor) > 255:
        raise ValueError("Acteur d'audit invalide")
    token = _CONTEXT.set(AuditContext(actor, trace_id))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


@event.listens_for(Engine, "begin")
def _bind_transaction_context(connection: Connection) -> None:
    context = _CONTEXT.get()
    if context is not None and connection.dialect.name == "postgresql":
        connection.execute(
            text(
                "SELECT set_config('metiquo.audit_actor', :actor, true), "
                "set_config('metiquo.audit_trace', :trace, true)"
            ),
            {"actor": context.actor, "trace": str(context.trace_id)},
        )
