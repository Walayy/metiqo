"""Retry exponentiel borné, réservé aux erreurs source transitoires."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

from metiquo.ingestion.source_errors import (
    SourceQuotaExceeded,
    SourceRateLimited,
    SourceTimeout,
    SourceTransportError,
    SourceUnavailable,
)
from metiquo.ingestion.transport import RetryPolicy

T = TypeVar("T")

_TRANSIENT_ERRORS = (
    SourceQuotaExceeded,
    SourceRateLimited,
    SourceTimeout,
    SourceUnavailable,
)


class RetryExecutor:
    """Exécuter une opération sans jamais rejouer une erreur permanente."""

    def __init__(
        self,
        *,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._sleep = sleep
        self._jitter = jitter

    def execute(self, operation: Callable[[], T], *, policy: RetryPolicy) -> T:
        for attempt in range(1, policy.max_attempts + 1):
            try:
                return operation()
            except SourceTransportError as error:
                error.record_attempts(attempt)
                can_retry = isinstance(error, _TRANSIENT_ERRORS) and error.retryable
                if not can_retry or attempt == policy.max_attempts:
                    raise
                jitter = self._jitter()
                if not 0 <= jitter <= 1:
                    raise ValueError("le jitter doit être compris entre 0 et 1") from None
                exponential = policy.base_delay_seconds * (2 ** (attempt - 1))
                capped = min(exponential, policy.max_delay_seconds)
                self._sleep(capped * (0.5 + jitter / 2))
        raise AssertionError("boucle de retry terminée sans résultat")
