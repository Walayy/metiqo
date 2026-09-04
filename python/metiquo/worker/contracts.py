"""Contrats des futurs handlers de jobs."""

from dataclasses import dataclass
from threading import Event
from typing import Protocol

from metiquo.foundation.identifiers import CorrelationId, JobId, TraceId
from metiquo.foundation.time import Clock, UtcInstant


class CancellationToken:
    """Signal d'annulation coopérative partageable avec un handler."""

    def __init__(self) -> None:
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


@dataclass(frozen=True, slots=True)
class JobContext:
    """Contexte explicite et déterministe fourni à chaque handler."""

    job_id: JobId
    trace_id: TraceId
    correlation_id: CorrelationId
    started_at: UtcInstant
    clock: Clock
    cancellation: CancellationToken


class JobHandler(Protocol):
    """Interface minimale d'un traitement métier synchrone."""

    def handle(self, context: JobContext) -> None: ...
