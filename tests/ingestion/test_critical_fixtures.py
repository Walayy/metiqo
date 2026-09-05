"""Couverture exécutable de chaque fixture Oracle's Elixir exigée par la SFG."""

from __future__ import annotations

import base64
import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.data_quality import DataQualityValidator, QualityCode
from metiquo.ingestion.physical_validation import PhysicalValidator
from metiquo.ingestion.safe_download import SafeDownloader, SafeDownloadResult
from metiquo.ingestion.schema_contract import ORACLES_ELIXIR_SCHEMA_V1
from metiquo.ingestion.source_errors import (
    ArchiveCorrupted,
    SchemaIncompatible,
    UnexpectedHtmlResponse,
)
from tests.ingestion.test_safe_download import SOURCE, BytesTransport

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "oracles_elixir"
CLOCK = FixedClock(UtcInstant(datetime(2026, 9, 5, 21, tzinfo=UTC)))


def _rows(name: str) -> list[dict[str, str]]:
    with (FIXTURES / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _download(tmp_path: Path, payload: bytes, name: str = "source.bin") -> SafeDownloadResult:
    return SafeDownloader().download(
        transport=BytesTransport(payload, "application/octet-stream"),
        source=SOURCE,
        destination=tmp_path / name,
    )


def test_fixture_inventory_and_synthetic_origin_are_explicit() -> None:
    expected = {
        "dq_valid.csv",
        "schema_additive.csv",
        "schema_missing_core.csv",
        "duplicate.csv",
        "incomplete_game.csv",
        "remake.csv",
        "retro_before.csv",
        "retro_after.csv",
        "truncated.csv",
        "quota.html",
        "encoding_delimiter_surprise.csv.base64",
        "corrupted_archive.gzip.base64",
        "historical_observation.json",
    }
    assert expected <= {path.name for path in FIXTURES.iterdir()}
    documentation = (FIXTURES / "README.md").read_text(encoding="utf-8")
    assert "synthétiques" in documentation
    assert "ne recopient aucune ligne" in documentation


def test_valid_additive_and_missing_core_fixtures_have_distinct_outcomes(
    tmp_path: Path,
) -> None:
    valid_download = _download(tmp_path, (FIXTURES / "dq_valid.csv").read_bytes(), "valid.csv")
    physical = PhysicalValidator().validate(valid_download)
    valid = ORACLES_ELIXIR_SCHEMA_V1.assess(physical.header)
    assert valid.blocking is False
    assert DataQualityValidator(clock=CLOCK).validate(_rows("dq_valid.csv")).status == "passed"

    with (FIXTURES / "schema_additive.csv").open(encoding="utf-8", newline="") as stream:
        additive_header = next(csv.reader(stream))
    additive = ORACLES_ELIXIR_SCHEMA_V1.assess(additive_header)
    assert additive.blocking is False
    assert additive.additive_columns == ("vendor_metric",)

    with (FIXTURES / "schema_missing_core.csv").open(encoding="utf-8", newline="") as stream:
        missing_header = next(csv.reader(stream))
    missing = ORACLES_ELIXIR_SCHEMA_V1.assess(missing_header)
    assert missing.blocking is True
    assert missing.missing_core_columns == ("gameid",)


def test_duplicate_incomplete_and_remake_are_classified_independently() -> None:
    validator = DataQualityValidator(clock=CLOCK)
    duplicate = validator.validate(_rows("duplicate.csv"))
    incomplete = validator.validate(_rows("incomplete_game.csv"))
    remake = validator.validate(_rows("remake.csv"))

    assert QualityCode.NATURAL_KEY_DUPLICATE in {issue.code for issue in duplicate.issues}
    assert duplicate.blocking is True
    assert incomplete.status == "capability-only"
    assert {issue.code for issue in incomplete.issues} == {QualityCode.INCOMPLETE_GAME}
    assert incomplete.disabled_capabilities == ("market.match_winner",)
    assert remake.status == "passed"
    assert {issue.code for issue in remake.issues} == {QualityCode.REMAKE_DETECTED}
    assert all(issue.severity == "warning" for issue in remake.issues)


def test_retroactive_fixture_keeps_keys_but_changes_auditable_content() -> None:
    before_path = FIXTURES / "retro_before.csv"
    after_path = FIXTURES / "retro_after.csv"
    before = DataQualityValidator(clock=CLOCK).validate(_rows(before_path.name))
    after = DataQualityValidator(clock=CLOCK).validate(_rows(after_path.name))

    assert before.status == after.status == "passed"
    assert before.natural_keys == after.natural_keys
    assert (
        hashlib.sha256(before_path.read_bytes()).digest()
        != hashlib.sha256(after_path.read_bytes()).digest()
    )


def test_truncated_quota_and_corrupted_archive_are_never_csv(
    tmp_path: Path,
) -> None:
    truncated = _download(
        tmp_path,
        (FIXTURES / "truncated.csv").read_bytes(),
        "truncated.csv",
    )
    with pytest.raises(SchemaIncompatible) as truncated_error:
        PhysicalValidator().validate(truncated)
    assert truncated_error.value.context["rule"] == "CSV_COLUMN_COUNT_MISMATCH"

    with pytest.raises(UnexpectedHtmlResponse):
        _download(tmp_path, (FIXTURES / "quota.html").read_bytes(), "quota.bin")

    corrupted_payload = base64.b64decode(
        (FIXTURES / "corrupted_archive.gzip.base64").read_text(encoding="ascii")
    )
    corrupted = _download(tmp_path, corrupted_payload, "corrupted.gzip")
    with pytest.raises(ArchiveCorrupted) as archive_error:
        PhysicalValidator().validate(corrupted)
    assert archive_error.value.context["rule"] == "ARCHIVE_CORRUPTED"


def test_bom_and_semicolon_are_detected_without_guessing(tmp_path: Path) -> None:
    payload = base64.b64decode(
        (FIXTURES / "encoding_delimiter_surprise.csv.base64").read_text(encoding="ascii")
    )
    download = _download(tmp_path, payload, "surprise.csv")
    report = PhysicalValidator().validate(download)

    assert report.encoding == "utf-8-sig"
    assert report.delimiter == ";"
    assert report.row_count == 2
    assert (
        DataQualityValidator(clock=CLOCK)
        .validate(list(csv.DictReader(payload.decode("utf-8-sig").splitlines(), delimiter=";")))
        .status
        == "passed"
    )


def test_historical_hash_is_evidence_not_current_download_expectation(
    tmp_path: Path,
) -> None:
    observation = json.loads((FIXTURES / "historical_observation.json").read_text(encoding="utf-8"))
    historical_payload = (FIXTURES / str(observation["fixture"])).read_bytes()
    assert len(historical_payload) == observation["observedByteSize"]
    assert hashlib.sha256(historical_payload).hexdigest() == observation["observedSha256"]

    current_payload = historical_payload + b"\n"
    current = _download(tmp_path, current_payload, "current.csv")
    assert current.sha256 != observation["observedSha256"]
    assert current.byte_size == len(current_payload)
