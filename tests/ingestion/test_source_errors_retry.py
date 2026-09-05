"""Taxonomie sûre et politique de retry des sources."""

from datetime import UTC, datetime

import pytest

from metiquo.ingestion.retry import RetryExecutor
from metiquo.ingestion.source_errors import (
    ArchiveCorrupted,
    AtomicPromotionFailed,
    ChecksumMismatch,
    DataQualityFailed,
    SchemaIncompatible,
    SourceNotFound,
    SourcePermissionDenied,
    SourceQuotaExceeded,
    SourceRateLimited,
    SourceTimeout,
    SourceTransportError,
    UnexpectedContentType,
    UnexpectedHtmlResponse,
)
from metiquo.ingestion.transport import RetryPolicy

NOW = datetime(2026, 9, 5, 20, tzinfo=UTC)


@pytest.mark.parametrize(
    ("error_type", "code", "retryable"),
    [
        (SourceNotFound, "SOURCE_NOT_FOUND", False),
        (SourcePermissionDenied, "SOURCE_PERMISSION_DENIED", False),
        (SourceQuotaExceeded, "SOURCE_QUOTA_EXCEEDED", True),
        (SourceRateLimited, "SOURCE_RATE_LIMITED", True),
        (SourceTimeout, "SOURCE_TIMEOUT", True),
        (UnexpectedHtmlResponse, "UNEXPECTED_HTML_RESPONSE", False),
        (UnexpectedContentType, "UNEXPECTED_CONTENT_TYPE", False),
        (ChecksumMismatch, "CHECKSUM_MISMATCH", False),
        (ArchiveCorrupted, "ARCHIVE_CORRUPTED", False),
        (SchemaIncompatible, "SCHEMA_INCOMPATIBLE", False),
        (DataQualityFailed, "DATA_QUALITY_FAILED", False),
        (AtomicPromotionFailed, "ATOMIC_PROMOTION_FAILED", False),
    ],
)
def test_every_required_error_has_stable_safe_context(
    error_type: type[SourceTransportError], code: str, retryable: bool
) -> None:
    error = error_type(
        "message sûr",
        transport="test-transport",
        source_id="source-2026",
        occurred_at=NOW,
        context={"year": 2026, "phase": "download"},
    )

    assert error.code.value == code
    assert error.retryable is retryable
    assert error.attempts == 1
    assert error.to_dict() == {
        "code": code,
        "message": "message sûr",
        "transport": "test-transport",
        "sourceId": "source-2026",
        "retryable": retryable,
        "httpStatus": None,
        "attempts": 1,
        "occurredAt": "2026-09-05T20:00:00Z",
        "context": {"year": 2026, "phase": "download"},
    }


def test_transient_error_uses_exponential_capped_jitter() -> None:
    attempts = 0
    delays: list[float] = []
    jitters = iter((0.0, 1.0, 0.5))

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise SourceRateLimited(
                "rate limited",
                transport="drive-api",
                source_id="source-2026",
                occurred_at=NOW,
            )
        return "downloaded"

    result = RetryExecutor(sleep=delays.append, jitter=lambda: next(jitters)).execute(
        operation,
        policy=RetryPolicy(max_attempts=4, base_delay_seconds=2, max_delay_seconds=5),
    )

    assert result == "downloaded"
    assert attempts == 4
    assert delays == [1.0, 4.0, 3.75]


def test_last_transient_error_records_total_attempts() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise SourceTimeout(
            "timeout",
            transport="drive-public",
            source_id="source-2026",
            occurred_at=NOW,
        )

    with pytest.raises(SourceTimeout) as captured:
        RetryExecutor(sleep=lambda delay: None, jitter=lambda: 0).execute(
            operation,
            policy=RetryPolicy(max_attempts=3, base_delay_seconds=1, max_delay_seconds=10),
        )

    assert attempts == 3
    assert captured.value.attempts == 3


def test_permanent_error_is_never_retried_even_if_mislabelled() -> None:
    attempts = 0
    delays: list[float] = []

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise SourcePermissionDenied(
            "permission",
            transport="drive-api",
            source_id="source-2026",
            retryable=True,
            occurred_at=NOW,
        )

    with pytest.raises(SourcePermissionDenied):
        RetryExecutor(sleep=delays.append).execute(
            operation,
            policy=RetryPolicy(max_attempts=4, base_delay_seconds=1, max_delay_seconds=10),
        )

    assert attempts == 1
    assert delays == []
