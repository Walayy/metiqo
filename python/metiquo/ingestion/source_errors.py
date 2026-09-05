"""Erreurs sûres et structurées des transports de sources."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType

from metiquo.foundation.time import normalize_utc_datetime

type SourceErrorContextValue = str | int | float | bool | None


class SourceErrorCode(StrEnum):
    NOT_FOUND = "SOURCE_NOT_FOUND"
    PERMISSION_DENIED = "SOURCE_PERMISSION_DENIED"
    QUOTA_EXCEEDED = "SOURCE_QUOTA_EXCEEDED"
    RATE_LIMITED = "SOURCE_RATE_LIMITED"
    TIMEOUT = "SOURCE_TIMEOUT"
    TOO_LARGE = "SOURCE_TOO_LARGE"
    INVALID_RESPONSE = "SOURCE_INVALID_RESPONSE"
    UNEXPECTED_HTML = "UNEXPECTED_HTML_RESPONSE"
    UNEXPECTED_CONTENT_TYPE = "UNEXPECTED_CONTENT_TYPE"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    ATOMIC_PROMOTION_FAILED = "ATOMIC_PROMOTION_FAILED"
    ARCHIVE_CORRUPTED = "ARCHIVE_CORRUPTED"
    SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"
    DATA_QUALITY_FAILED = "DATA_QUALITY_FAILED"
    UNAVAILABLE = "SOURCE_UNAVAILABLE"


class SourceTransportError(RuntimeError):
    """Erreur transport sérialisable sans URL ni credential."""

    code: SourceErrorCode
    default_retryable = False

    def __init__(
        self,
        message: str,
        *,
        transport: str,
        source_id: str,
        retryable: bool | None = None,
        http_status: int | None = None,
        attempts: int = 1,
        occurred_at: datetime | None = None,
        context: Mapping[str, SourceErrorContextValue] | None = None,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts doit être supérieur ou égal à 1")
        super().__init__(message)
        self.message = message
        self.transport = transport
        self.source_id = source_id
        self.retryable = self.default_retryable if retryable is None else retryable
        self.http_status = http_status
        self.attempts = attempts
        self.occurred_at = normalize_utc_datetime(occurred_at or datetime.now(UTC))
        self.context: Mapping[str, SourceErrorContextValue] = MappingProxyType(dict(context or {}))

    def record_attempts(self, attempts: int) -> None:
        if attempts < 1:
            raise ValueError("attempts doit être supérieur ou égal à 1")
        self.attempts = attempts

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": self.message,
            "transport": self.transport,
            "sourceId": self.source_id,
            "retryable": self.retryable,
            "httpStatus": self.http_status,
            "attempts": self.attempts,
            "occurredAt": self.occurred_at.isoformat().replace("+00:00", "Z"),
            "context": dict(self.context),
        }


class SourceNotFound(SourceTransportError):
    code = SourceErrorCode.NOT_FOUND


class SourcePermissionDenied(SourceTransportError):
    code = SourceErrorCode.PERMISSION_DENIED


class SourceQuotaExceeded(SourceTransportError):
    code = SourceErrorCode.QUOTA_EXCEEDED
    default_retryable = True


class SourceRateLimited(SourceTransportError):
    code = SourceErrorCode.RATE_LIMITED
    default_retryable = True


class SourceTimeout(SourceTransportError):
    code = SourceErrorCode.TIMEOUT
    default_retryable = True


class SourceTooLarge(SourceTransportError):
    code = SourceErrorCode.TOO_LARGE


class SourceInvalidResponse(SourceTransportError):
    code = SourceErrorCode.INVALID_RESPONSE


class UnexpectedHtmlResponse(SourceTransportError):
    code = SourceErrorCode.UNEXPECTED_HTML


class UnexpectedContentType(SourceTransportError):
    code = SourceErrorCode.UNEXPECTED_CONTENT_TYPE


class ChecksumMismatch(SourceTransportError):
    code = SourceErrorCode.CHECKSUM_MISMATCH


class AtomicPromotionFailed(SourceTransportError):
    code = SourceErrorCode.ATOMIC_PROMOTION_FAILED


class ArchiveCorrupted(SourceTransportError):
    code = SourceErrorCode.ARCHIVE_CORRUPTED


class SchemaIncompatible(SourceTransportError):
    code = SourceErrorCode.SCHEMA_INCOMPATIBLE


class DataQualityFailed(SourceTransportError):
    code = SourceErrorCode.DATA_QUALITY_FAILED


class SourceUnavailable(SourceTransportError):
    code = SourceErrorCode.UNAVAILABLE
    default_retryable = True
