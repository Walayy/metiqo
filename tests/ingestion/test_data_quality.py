"""Règles métier et comparaison au snapshot précédent."""

import csv
from datetime import UTC, datetime
from pathlib import Path

import pytest

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.data_quality import (
    DataQualityValidator,
    PreviousQualitySummary,
    QualityCode,
    QualityReport,
)
from metiquo.ingestion.source_errors import DataQualityFailed

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "oracles_elixir"
CLOCK = FixedClock(UtcInstant(datetime(2026, 9, 5, 21, tzinfo=UTC)))


def _rows(name: str = "dq_valid.csv") -> list[dict[str, str]]:
    with (FIXTURES / name).open(newline="") as stream:
        return list(csv.DictReader(stream))


def _codes(report: QualityReport) -> set[QualityCode]:
    return {issue.code for issue in report.issues}


def test_valid_team_and_player_structure_passes() -> None:
    report = DataQualityValidator(clock=CLOCK).validate(_rows())

    assert report.status == "passed"
    assert report.blocking is False
    assert report.row_count == 12
    assert report.game_count == 1
    assert report.min_event_date == "2026-01-10"
    assert report.max_event_date == "2026-01-10"
    assert report.issues == ()
    assert len(report.natural_keys) == 12


def test_problematic_fixture_emits_stable_blocking_capability_and_warning_codes() -> None:
    report = DataQualityValidator(clock=CLOCK).validate(_rows("dq_problematic.csv"))

    assert report.status == "failed"
    assert {
        QualityCode.DATE_INVALID,
        QualityCode.NATURAL_KEY_DUPLICATE,
        QualityCode.TEAMS_NOT_DISTINCT,
        QualityCode.NUMERIC_OUT_OF_RANGE,
        QualityCode.RESULT_INCONSISTENT,
        QualityCode.INCOMPLETE_GAME,
        QualityCode.REMAKE_DETECTED,
        QualityCode.FORFEIT_DETECTED,
    } <= _codes(report)
    severities = {issue.severity for issue in report.issues}
    assert severities == {"blocking", "capability-only", "warning"}


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("gameid", "", QualityCode.MISSING_GAME_ID),
        ("participantid", "", QualityCode.MISSING_PARTICIPANT_ID),
        ("date", "2010-01-01", QualityCode.DATE_IMPLAUSIBLE),
        ("date", "invalid", QualityCode.DATE_INVALID),
        ("side", "Green", QualityCode.SIDE_INVALID),
        ("kills", "not-a-number", QualityCode.NUMERIC_INVALID),
        ("kills", "-0.01", QualityCode.NUMERIC_OUT_OF_RANGE),
        ("kills", "200.01", QualityCode.NUMERIC_OUT_OF_RANGE),
        ("result", "2", QualityCode.NUMERIC_OUT_OF_RANGE),
    ],
)
def test_row_property_ranges_have_stable_codes(
    field: str, value: str, expected: QualityCode
) -> None:
    rows = _rows()
    rows[0][field] = value

    report = DataQualityValidator(clock=CLOCK).validate(rows)

    assert expected in _codes(report)


def test_incomplete_game_disables_only_market_capability() -> None:
    rows = _rows()
    for row in rows:
        row["datacompleteness"] = "partial"

    report = DataQualityValidator(clock=CLOCK).validate(rows)

    assert report.status == "capability-only"
    assert report.disabled_capabilities == ("market.match_winner",)
    assert _codes(report) == {QualityCode.INCOMPLETE_GAME}


def test_missing_player_row_disables_player_feature_without_blocking_raw() -> None:
    rows = _rows()
    del rows[0]

    report = DataQualityValidator(clock=CLOCK).validate(rows)

    assert report.status == "capability-only"
    assert QualityCode.PLAYER_ROW_STRUCTURE in _codes(report)
    assert report.disabled_capabilities == ("feature.player_form",)


def test_mass_deletion_is_blocked_unless_explicitly_approved() -> None:
    rows = _rows()
    previous = PreviousQualitySummary(
        row_count=120,
        natural_keys=frozenset({f"previous:{index}" for index in range(120)}),
    )
    validator = DataQualityValidator(clock=CLOCK, mass_deletion_ratio=0.8)

    blocked = validator.validate(rows, previous=previous)
    approved = validator.validate(rows, previous=previous, approve_mass_deletion=True)

    assert QualityCode.MASS_DELETION_DETECTED in _codes(blocked)
    assert blocked.blocking is True
    assert QualityCode.MASS_DELETION_DETECTED not in _codes(approved)
    assert approved.status == "passed"


def test_blocking_report_raises_structured_error_and_serializes() -> None:
    report = DataQualityValidator(clock=CLOCK).validate(_rows("dq_problematic.csv"))

    with pytest.raises(DataQualityFailed) as captured:
        DataQualityValidator.require_pass(
            report,
            transport="local-fixture",
            source_id="dq-problematic",
        )

    assert captured.value.context["rule"] == "DATA_QUALITY_BLOCKING"
    assert "NATURAL_KEY_DUPLICATE" in str(captured.value.context["blockingCodes"])
    document = report.to_dict()
    assert document["status"] == "failed"
    assert document["rowCount"] == 2
    assert isinstance(document["issues"], list)
