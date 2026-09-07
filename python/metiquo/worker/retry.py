"""Politique de reprise bornée sans exposer les messages techniques des dépendances."""

import hashlib
import re
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy.exc import DBAPIError

from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.ingestion.sync import SyncFailed


@dataclass(frozen=True, slots=True)
class JobFailure:
    code: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    delays_seconds: tuple[int, ...] = (600, 1800, 7200)
    jitter_fraction: float = 0.1

    def __post_init__(self) -> None:
        if not self.delays_seconds or any(not 1 <= delay <= 86400 for delay in self.delays_seconds):
            raise ValueError("Délais de reprise hors limites")
        if not 0 <= self.jitter_fraction <= 0.5:
            raise ValueError("Jitter hors limites")

    def delay(self, job_id: UUID, attempt: int) -> timedelta:
        if attempt < 1:
            raise ValueError("Tentative positive requise")
        base = self.delays_seconds[min(attempt - 1, len(self.delays_seconds) - 1)]
        jitter = int.from_bytes(hashlib.sha256(f"{job_id}:{attempt}".encode()).digest()[:8]) / (
            2**64 - 1
        )
        return timedelta(seconds=base * (1 + self.jitter_fraction * jitter))


def classify_failure(error: Exception) -> JobFailure:
    if isinstance(error, SyncFailed):
        code = (
            error.error_code
            if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error.error_code)
            else "SOURCE_SYNC_FAILED"
        )
        return JobFailure(
            code,
            code
            in {
                "SOURCE_TIMEOUT",
                "SOURCE_UNAVAILABLE",
                "SOURCE_RATE_LIMITED",
                "SOURCE_QUOTA_EXCEEDED",
            },
        )
    if isinstance(error, BusinessError):
        permanent = error.code in {
            ErrorCode.INVALID_INPUT,
            ErrorCode.INVALID_STATE,
            ErrorCode.NOT_FOUND,
        }
        return JobFailure(error.code.value, error.retryable and not permanent)
    if isinstance(error, DBAPIError):
        state = str(getattr(error.orig, "sqlstate", "") or "")
        transient = (
            error.connection_invalidated
            or state.startswith("08")
            or state in {"40001", "40P01", "55P03", "57P01"}
        )
        return JobFailure("DATABASE_UNAVAILABLE" if transient else "DATABASE_ERROR", transient)
    if isinstance(error, (TimeoutError, ConnectionError)):
        return JobFailure("DEPENDENCY_UNAVAILABLE", True)
    if isinstance(error, ValueError):
        return JobFailure("INVALID_INPUT", False)
    return JobFailure("UNEXPECTED_ERROR", False)
