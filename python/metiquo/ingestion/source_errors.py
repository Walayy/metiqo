"""Erreurs sûres et structurées des transports de sources."""

from __future__ import annotations

from enum import StrEnum


class SourceErrorCode(StrEnum):
    NOT_FOUND = "SOURCE_NOT_FOUND"
    PERMISSION_DENIED = "SOURCE_PERMISSION_DENIED"
    QUOTA_EXCEEDED = "SOURCE_QUOTA_EXCEEDED"
    RATE_LIMITED = "SOURCE_RATE_LIMITED"
    TIMEOUT = "SOURCE_TIMEOUT"
    TOO_LARGE = "SOURCE_TOO_LARGE"
    INVALID_RESPONSE = "SOURCE_INVALID_RESPONSE"
    UNEXPECTED_HTML = "UNEXPECTED_HTML_RESPONSE"
    UNAVAILABLE = "SOURCE_UNAVAILABLE"


class SourceTransportError(RuntimeError):
    """Erreur transport sérialisable sans URL ni credential."""

    code: SourceErrorCode

    def __init__(
        self,
        message: str,
        *,
        transport: str,
        source_id: str,
        retryable: bool,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.transport = transport
        self.source_id = source_id
        self.retryable = retryable
        self.http_status = http_status

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": self.message,
            "transport": self.transport,
            "sourceId": self.source_id,
            "retryable": self.retryable,
            "httpStatus": self.http_status,
        }


class SourceNotFound(SourceTransportError):
    code = SourceErrorCode.NOT_FOUND


class SourcePermissionDenied(SourceTransportError):
    code = SourceErrorCode.PERMISSION_DENIED


class SourceQuotaExceeded(SourceTransportError):
    code = SourceErrorCode.QUOTA_EXCEEDED


class SourceRateLimited(SourceTransportError):
    code = SourceErrorCode.RATE_LIMITED


class SourceTimeout(SourceTransportError):
    code = SourceErrorCode.TIMEOUT


class SourceTooLarge(SourceTransportError):
    code = SourceErrorCode.TOO_LARGE


class SourceInvalidResponse(SourceTransportError):
    code = SourceErrorCode.INVALID_RESPONSE


class UnexpectedHtmlResponse(SourceTransportError):
    code = SourceErrorCode.UNEXPECTED_HTML


class SourceUnavailable(SourceTransportError):
    code = SourceErrorCode.UNAVAILABLE
