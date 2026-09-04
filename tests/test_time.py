"""Tests des instants UTC et horloges injectables."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from metiquo.foundation.time import Clock, FixedClock, UtcInstant


def read_current_time(clock: Clock) -> UtcInstant:
    return clock.now()


def test_instant_is_normalized_to_utc() -> None:
    source = datetime(2026, 9, 4, 18, 45, tzinfo=timezone(timedelta(hours=2)))

    instant = UtcInstant(source)

    assert instant.value == datetime(2026, 9, 4, 16, 45, tzinfo=UTC)
    assert instant.isoformat() == "2026-09-04T16:45:00Z"


def test_naive_instant_is_rejected() -> None:
    with pytest.raises(ValueError, match="conscient de son fuseau"):
        UtcInstant(datetime(2026, 9, 4, 16, 45))


def test_fixed_clock_is_deterministic() -> None:
    expected = UtcInstant.parse("2026-09-04T16:45:00Z")
    clock = FixedClock(expected)

    assert read_current_time(clock) is expected
    assert read_current_time(clock) is expected


def test_utc_instants_have_chronological_ordering() -> None:
    earlier = UtcInstant.parse("2026-09-04T16:44:59Z")
    later = UtcInstant.parse("2026-09-04T16:45:00Z")

    assert earlier < later
