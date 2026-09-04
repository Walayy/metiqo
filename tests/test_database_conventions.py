"""Tests unitaires des conventions de persistance."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.engine.default import DefaultDialect

from metiquo.db.base import UtcDateTime


def test_aware_datetime_is_normalized_to_utc() -> None:
    column_type = UtcDateTime()
    source = datetime(2026, 9, 4, 14, 30, tzinfo=timezone(timedelta(hours=2)))

    normalized = column_type.process_bind_param(source, DefaultDialect())

    assert normalized == datetime(2026, 9, 4, 12, 30, tzinfo=UTC)
    assert normalized is not None
    assert normalized.tzinfo is UTC


def test_naive_datetime_is_rejected() -> None:
    column_type = UtcDateTime()

    with pytest.raises(ValueError, match="conscient de son fuseau"):
        column_type.process_bind_param(datetime(2026, 9, 4, 12, 30), DefaultDialect())
