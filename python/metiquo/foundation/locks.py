"""Verrous de portée partagés par les appels opérateur, le backfill et les workers."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic, sleep

from sqlalchemy import Connection, Engine, text

from metiquo.foundation.errors import BusinessError, ErrorCode

_HELD: ContextVar[dict[tuple[str, int, str, int], Connection] | None] = ContextVar(
    "resource_locks", default=None
)


class ResourceBusy(BusinessError):
    def __init__(self, scope: str) -> None:
        super().__init__(
            ErrorCode.CONFLICT,
            "Une opération détient déjà cette ressource",
            context={"scope": scope},
            retryable=True,
        )


def oe_scope(provider: str, year: int) -> str:
    return f"oe:{provider}:{year}"


def resource_lock_key(scope: str) -> int:
    if not scope.strip() or len(scope) > 255:
        raise ValueError("Portée de verrou invalide")
    parts = scope.split(":")
    # Conserver la clé historique du backfill afin de coordonner les deux chemins.
    identity = (
        f"{parts[1]}\0{parts[2]}" if len(parts) == 3 and parts[0] == "oe" else f"resource:{scope}"
    )
    return int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big", signed=True)


def _identity(engine: Engine, scope: str) -> tuple[str, int, str, int]:
    return (
        engine.url.host or "",
        engine.url.port or 5432,
        engine.url.database or "",
        resource_lock_key(scope),
    )


def try_transaction_lock(connection: Connection, scope: str) -> bool:
    held = (_HELD.get() or {}).get(_identity(connection.engine, scope))
    if held is not None:
        held.execute(text("SELECT 1"))
        return True
    return bool(
        connection.scalar(
            text("SELECT pg_try_advisory_xact_lock(:lock)"), {"lock": resource_lock_key(scope)}
        )
    )


@contextmanager
def resource_lock(engine: Engine, scope: str, *, timeout_seconds: float = 0) -> Iterator[None]:
    if not 0 <= timeout_seconds <= 120:
        raise ValueError("Délai de verrou hors limites")
    identity = _identity(engine, scope)
    held = _HELD.get() or {}
    if identity in held:
        held[identity].execute(text("SELECT 1"))
        yield
        return
    deadline = monotonic() + timeout_seconds
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        while not connection.scalar(
            text("SELECT pg_try_advisory_lock(:lock)"), {"lock": identity[-1]}
        ):
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise ResourceBusy(scope)
            sleep(min(0.02, remaining))
        token = _HELD.set({**held, identity: connection})
        try:
            yield
        finally:
            _HELD.reset(token)
            try:
                connection.execute(text("SELECT pg_advisory_unlock(:lock)"), {"lock": identity[-1]})
            except Exception:
                connection.invalidate()
