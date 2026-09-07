"""Contrats des futurs handlers de jobs."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from threading import Event
from typing import Protocol

from metiquo.foundation.cancellation import OperationCancelled
from metiquo.foundation.identifiers import CorrelationId, JobId, TraceId
from metiquo.foundation.time import Clock, UtcInstant


class JobCancelled(OperationCancelled):
    """Le handler s'arrête à une frontière atomique."""


class CancellationToken:
    """Signal d'annulation coopérative partageable avec un handler."""

    def __init__(self) -> None:
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def wait(self, timeout_seconds: float) -> bool:
        return self._event.wait(timeout_seconds)

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise JobCancelled()


@dataclass(frozen=True, slots=True)
class JobContext:
    """Contexte explicite et déterministe fourni à chaque handler."""

    job_id: JobId
    trace_id: TraceId
    correlation_id: CorrelationId
    started_at: UtcInstant
    clock: Clock
    cancellation: CancellationToken
    payload: Mapping[str, object] = field(default_factory=dict)
    attempt: int = 1


class JobHandler(Protocol):
    """Interface minimale d'un traitement métier synchrone."""

    def handle(self, context: JobContext) -> dict[str, object] | None: ...
