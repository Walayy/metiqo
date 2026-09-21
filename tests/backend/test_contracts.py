from datetime import UTC, datetime
from decimal import Decimal

import pytest
from metiquo_api.main import _LEAGUE_CONTRACT_FIELDS, _catalog_record
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


def test_catalog_projection_keeps_source_metadata_private():
    stored = {
        "id": "sofascore:tournament:90739",
        "slug": "vcs",
        "name": "VCS",
        "region": "INTERNATIONAL",
        "image": "",
        "sourceImage": "https://example.com/vcs.png",
        "tier": "international",
        "sourceId": "90739",
    }

    projected = _catalog_record(stored, _LEAGUE_CONTRACT_FIELDS)

    assert projected == {key: value for key, value in stored.items() if key != "sourceId"}
