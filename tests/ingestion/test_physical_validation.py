"""Rejets physiques diagnostiqués avant toute promotion de snapshot."""

import gzip
import io
import zipfile
from pathlib import Path

import pytest

from metiquo.ingestion.physical_validation import PhysicalValidator
from metiquo.ingestion.safe_download import SafeDownloader, SafeDownloadResult
from metiquo.ingestion.source_errors import (
    ArchiveCorrupted,
    ChecksumMismatch,
    DataQualityFailed,
    SchemaIncompatible,
    SourceTransportError,
    UnexpectedContentType,
    UnexpectedHtmlResponse,
)
from tests.ingestion.test_safe_download import SOURCE, BytesTransport

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "oracles_elixir"


def _download(
    tmp_path: Path, payload: bytes, content_type: str, name: str = "source.bin"
) -> SafeDownloadResult:
    return SafeDownloader().download(
        transport=BytesTransport(payload, content_type),
        source=SOURCE,
        destination=tmp_path / name,
    )


@pytest.mark.parametrize(
    ("payload", "content_type", "error_type", "rule"),
    [
        (b"", "text/csv", UnexpectedContentType, "EMPTY_BODY"),
        (
            (FIXTURES / "quota.html").read_bytes(),
            "application/octet-stream",
            UnexpectedHtmlResponse,
            "HTML_BODY",
        ),
        (
            (FIXTURES / "physical_error.json").read_bytes(),
            "application/octet-stream",
            UnexpectedContentType,
            "JSON_ERROR_BODY",
        ),
        (
            b"\xff\xfe\x00\x00",
            "application/octet-stream",
            UnexpectedContentType,
            "UNKNOWN_ENCODING",
        ),
    ],
)
def test_early_invalid_bodies_have_diagnostic_and_no_final_file(
    tmp_path: Path,
    payload: bytes,
    content_type: str,
    error_type: type[SourceTransportError],
    rule: str,
) -> None:
    destination = tmp_path / "source.bin"

    with pytest.raises(error_type) as captured:
        _download(tmp_path, payload, content_type)

    assert captured.value.context["rule"] == rule
    assert destination.exists() is False
    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.parametrize(
    ("fixture", "rule"),
    [
        ("physical_missing_header.csv", "CSV_HEADER_INVALID"),
        ("physical_inconsistent.csv", "CSV_COLUMN_COUNT_MISMATCH"),
    ],
)
def test_invalid_csv_structure_is_diagnosed(tmp_path: Path, fixture: str, rule: str) -> None:
    download = _download(tmp_path, (FIXTURES / fixture).read_bytes(), "text/csv", "source.csv")

    with pytest.raises(SchemaIncompatible) as captured:
        PhysicalValidator().validate(download)

    assert captured.value.context["rule"] == rule


def test_corrupted_archive_is_rejected(tmp_path: Path) -> None:
    download = _download(
        tmp_path,
        b"\x1f\x8bnot-a-valid-gzip-stream",
        "application/octet-stream",
    )

    with pytest.raises(ArchiveCorrupted) as captured:
        PhysicalValidator().validate(download)

    assert captured.value.context["rule"] == "ARCHIVE_CORRUPTED"


@pytest.mark.parametrize("compression", ["gzip", "zip"])
def test_valid_archive_detects_encoding_delimiter_and_rows(
    tmp_path: Path, compression: str
) -> None:
    csv_payload = b"gameid,league\nOE-001,LCK\nOE-002,LEC\n"
    if compression == "gzip":
        payload = gzip.compress(csv_payload)
    else:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("source.csv", csv_payload)
        payload = buffer.getvalue()
    download = _download(tmp_path, payload, "application/octet-stream")

    report = PhysicalValidator().validate(download)

    assert report.compression == compression
    assert report.encoding == "utf-8"
    assert report.delimiter == ","
    assert report.header == ("gameid", "league")
    assert report.column_count == 2
    assert report.row_count == 2


def test_checksum_change_since_download_is_rejected(tmp_path: Path) -> None:
    download = _download(tmp_path, b"gameid,league\nOE-001,LCK\n", "text/csv", "source.csv")
    download.final_path.write_bytes(b"gameid,league\nOE-002,LEC\n")

    with pytest.raises(ChecksumMismatch) as captured:
        PhysicalValidator().validate(download)

    assert captured.value.context["rule"] == "CHECKSUM_REREAD_MISMATCH"


def test_implausible_size_drop_requires_explicit_approval(tmp_path: Path) -> None:
    download = _download(tmp_path, b"gameid,league\nOE-001,LCK\n", "text/csv", "source.csv")
    previous_size = download.byte_size * 10

    with pytest.raises(DataQualityFailed) as captured:
        PhysicalValidator(min_size_ratio=0.5).validate(
            download,
            previous_validated_size=previous_size,
        )

    assert captured.value.context["rule"] == "IMPLAUSIBLE_SIZE_DROP"
    report = PhysicalValidator(min_size_ratio=0.5).validate(
        download,
        previous_validated_size=previous_size,
        approve_size_drop=True,
    )
    assert report.row_count == 1
