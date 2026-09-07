"""Erreurs permanentes, reprises bornées et jitter reproductible."""

from uuid import UUID

from sqlalchemy.exc import OperationalError

from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.ingestion.sync import SyncFailed
from metiquo.worker.retry import RetryPolicy, classify_failure


def test_only_transient_errors_retry_with_bounded_delay() -> None:
    identity = UUID("e48f7c87-ec61-42f5-94d0-e74e9467399f")
    policy = RetryPolicy()
    for code, retry in (
        ("SOURCE_RATE_LIMITED", True),
        ("SOURCE_QUOTA_EXCEEDED", True),
        ("DATA_QUALITY_FAILED", False),
        ("ATOMIC_PROMOTION_FAILED", False),
    ):
        failure = classify_failure(SyncFailed("failure", error_code=code, run_id=identity))
        assert failure.code == code and failure.retryable is retry
    for attempt, base in ((1, 600), (2, 1800), (3, 7200), (20, 7200)):
        delay = policy.delay(identity, attempt).total_seconds()
        assert base <= delay <= base * 1.1
        assert policy.delay(identity, attempt).total_seconds() == delay
    assert classify_failure(ValueError("private payload")).retryable is False
    assert (
        classify_failure(BusinessError(ErrorCode.INVALID_INPUT, "bad", retryable=True)).retryable
        is False
    )
    assert (
        classify_failure(
            BusinessError(ErrorCode.DEPENDENCY_UNAVAILABLE, "offline", retryable=True)
        ).retryable
        is True
    )
    assert classify_failure(TimeoutError("private URL")).retryable is True
    assert (
        classify_failure(
            OperationalError(None, None, Exception("offline"), connection_invalidated=True)
        ).retryable
        is True
    )
