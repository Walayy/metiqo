from datetime import UTC, datetime
from decimal import Decimal

import pytest
from metiquo_core.contracts import Quote, value_percent
from pydantic import ValidationError


def test_decimal_value_has_no_premature_rounding():
    assert value_percent(Decimal("0.6"), Decimal("1.8")) == Decimal("8.00")
    assert value_percent(Decimal("0.5"), Decimal("1.9")) == Decimal("-5.00")


@pytest.mark.parametrize("odds", [1, 0, -2, float("nan"), float("inf")])
def test_invalid_odds_rejected(odds):
    with pytest.raises(ValidationError):
        Quote(recorded_at=datetime.now(UTC), odds=odds)


def test_quote_requires_timezone():
    with pytest.raises(ValidationError):
        Quote(recorded_at=datetime(2026, 9, 15), odds=2)
