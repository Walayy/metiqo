"""Tests des identifiants opaques par domaine."""

import pytest

from metiquo.foundation.identifiers import EventId, SnapshotId

UUID_TEXT = "5fe6e084-7b43-4a65-920f-62d49fc49a5e"


def values_equal(left: object, right: object) -> bool:
    return left == right


def test_identifier_round_trip_is_canonical() -> None:
    identifier = EventId.parse(UUID_TEXT.upper())

    assert str(identifier) == UUID_TEXT
    assert EventId.parse(str(identifier)) == identifier


def test_identical_uuid_in_two_domains_is_not_equal() -> None:
    assert not values_equal(EventId.parse(UUID_TEXT), SnapshotId.parse(UUID_TEXT))


def test_invalid_identifier_is_rejected_with_domain_name() -> None:
    with pytest.raises(ValueError, match="EventId invalide"):
        EventId.parse("not-an-id")
