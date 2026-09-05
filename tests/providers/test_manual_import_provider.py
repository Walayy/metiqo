"""Import manuel strict, atomique et idempotent de cotes CSV/JSON."""

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from metiquo.contracts.enums import GameTitle
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.providers import MANUAL_IMPORT_COLUMNS, ManualImportOddsProvider
from tests.providers.odds_provider_contract import (
    OddsProviderContractFixture,
    assert_odds_provider_contract,
)

_NOW = datetime(2026, 9, 5, 13, tzinfo=UTC)
_CAPTURED_AT = datetime(2026, 9, 5, 12, tzinfo=UTC)
_STARTS_AT = datetime(2026, 9, 6, 18, tzinfo=UTC)


def test_valid_csv_is_committed_atomically_and_passes_provider_contract() -> None:
    provider = _provider()
    payload = _csv_payload(_rows())

    result = provider.import_document(payload, document_format="csv")

    assert result.committed is True
    assert result.duplicate is False
    assert result.received_rows == 2
    assert result.imported_rows == 2
    assert result.issues == ()
    assert result.import_key.startswith("sha256:")
    assert_odds_provider_contract(
        OddsProviderContractFixture(
            provider=provider,
            starts_from=_STARTS_AT - timedelta(hours=1),
            starts_to=_STARTS_AT + timedelta(hours=1),
            game_title=GameTitle.LEAGUE_OF_LEGENDS,
        )
    )


def test_valid_json_uses_the_same_normalized_contract() -> None:
    provider = _provider()

    result = provider.import_document(_json_payload(_rows()), document_format="json")

    assert result.committed is True
    event = provider.list_events(
        _STARTS_AT - timedelta(hours=1),
        _STARTS_AT + timedelta(hours=1),
        GameTitle.LEAGUE_OF_LEGENDS,
    )[0]
    market = provider.get_event_markets(event.provider_event_id)[0]
    assert tuple(selection.provider_selection_id for selection in market.selections) == (
        "manual-team-a",
        "manual-team-b",
    )
    assert len(provider.capture_snapshot(event.provider_event_id).snapshots) == 2


def test_all_row_errors_abort_the_document_without_partial_state() -> None:
    provider = _provider()
    rows = _rows()
    rows[0]["decimal_odds"] = "0.50"
    rows[1]["provider"] = "another-provider"
    rows[1]["captured_at"] = (_NOW + timedelta(minutes=1)).isoformat()

    result = provider.import_document(_json_payload(rows), document_format="json")

    assert result.committed is False
    assert result.imported_rows == 0
    assert {issue.row_number for issue in result.issues} == {1, 2}
    assert {issue.code for issue in result.issues} >= {
        "GREATER_THAN_EQUAL",
        "PROVIDER_MISMATCH",
        "CAPTURE_IN_FUTURE",
    }
    assert provider.imported_document_count == 0
    assert provider.observation_count == 0
    assert (
        provider.list_events(
            _STARTS_AT - timedelta(hours=1),
            _STARTS_AT + timedelta(hours=1),
            GameTitle.LEAGUE_OF_LEGENDS,
        )
        == ()
    )


def test_exact_document_sha256_is_the_idempotence_key() -> None:
    provider = _provider()
    payload = _csv_payload(_rows())

    first = provider.import_document(payload, document_format="csv")
    second = provider.import_document(payload, document_format="csv")

    assert first.committed is True
    assert second.import_key == first.import_key
    assert second.committed is False
    assert second.duplicate is True
    assert second.imported_rows == 0
    assert provider.imported_document_count == 1
    assert provider.observation_count == 2


def test_unreliable_manual_timestamp_is_forced_to_informational_only() -> None:
    provider = _provider()
    rows = _rows()
    for row in rows:
        row["timestamp_reliable"] = False

    result = provider.import_document(_json_payload(rows), document_format="json")
    capture = provider.capture_snapshot("manual-event")

    assert result.committed is True
    assert capture.snapshots
    assert all(snapshot.informational_only for snapshot in capture.snapshots)


def test_csv_header_and_json_extra_fields_are_rejected_strictly() -> None:
    csv_provider = _provider()
    json_provider = _provider()
    invalid_csv = _csv_payload(_rows()).replace(b"provider,", b"unknown,", 1)
    rows = _rows()
    rows[0]["unexpected"] = "forbidden"

    csv_result = csv_provider.import_document(invalid_csv, document_format="csv")
    json_result = json_provider.import_document(_json_payload(rows), document_format="json")

    assert csv_result.issues[0].code == "CSV_HEADER_INVALID"
    assert any(issue.code == "EXTRA_FORBIDDEN" for issue in json_result.issues)
    assert csv_provider.observation_count == 0
    assert json_provider.observation_count == 0


def _provider() -> ManualImportOddsProvider:
    return ManualImportOddsProvider(
        "manual-lab",
        clock=FixedClock(UtcInstant(_NOW)),
    )


def _rows() -> list[dict[str, Any]]:
    common: dict[str, Any] = {
        "best_of": 3,
        "captured_at": _CAPTURED_AT.isoformat(),
        "competition": "Manual League",
        "event_status": "scheduled",
        "game_title": "lol",
        "line": None,
        "market_label": "Match Winner",
        "market_status": "open",
        "market_type": "MATCH_WINNER",
        "participant_a": "Manual Alpha",
        "participant_b": "Manual Beta",
        "period": "SERIES",
        "unit": "winner",
        "provider": "manual-lab",
        "provider_event_id": "manual-event",
        "provider_market_id": "manual-market",
        "settlement_rules_version": "match-winner-v1",
        "remake_policy": "void",
        "forfeit_policy": "settle",
        "cancelled_policy": "void",
        "starts_at": _STARTS_AT.isoformat(),
        "timestamp_reliable": True,
    }
    return [
        {
            **common,
            "decimal_odds": "1.80",
            "provenance_reference": "manual:test:team-a:v1",
            "provider_selection_id": "manual-team-a",
            "selection": "TEAM_A",
            "selection_label": "Manual Alpha",
        },
        {
            **common,
            "decimal_odds": "2.10",
            "provenance_reference": "manual:test:team-b:v1",
            "provider_selection_id": "manual-team-b",
            "selection": "TEAM_B",
            "selection_label": "Manual Beta",
        },
    ]


def _csv_payload(rows: list[dict[str, Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=MANUAL_IMPORT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def _json_payload(rows: list[dict[str, Any]]) -> bytes:
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode()
