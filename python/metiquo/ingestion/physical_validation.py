"""Validation physique en flux des CSV et archives téléchargés."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import zipfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TextIO, cast

from metiquo.ingestion.safe_download import SafeDownloadResult
from metiquo.ingestion.source_errors import (
    ArchiveCorrupted,
    ChecksumMismatch,
    DataQualityFailed,
    SchemaIncompatible,
    SourceTransportError,
    UnexpectedContentType,
)

_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class PhysicalValidationReport:
    byte_size: int
    sha256: str
    compression: str
    encoding: str
    delimiter: str
    header: tuple[str, ...]
    column_count: int
    row_count: int


class PhysicalValidator:
    """Refuser tout fichier structurellement impropre avant l'ObjectStore."""

    def __init__(self, *, min_size_ratio: float = 0.5) -> None:
        if not 0 < min_size_ratio <= 1:
            raise ValueError("min_size_ratio doit être dans ]0, 1]")
        self._min_size_ratio = min_size_ratio

    def validate(
        self,
        download: SafeDownloadResult,
        *,
        previous_validated_size: int | None = None,
        approve_size_drop: bool = False,
    ) -> PhysicalValidationReport:
        path = download.final_path
        actual_size = path.stat().st_size
        if actual_size == 0:
            raise self._error(UnexpectedContentType, download, "EMPTY_BODY", "corps source vide")
        actual_hash = _hash_file(path)
        if actual_hash != download.sha256 or actual_size != download.byte_size:
            raise self._error(
                ChecksumMismatch,
                download,
                "CHECKSUM_REREAD_MISMATCH",
                "checksum ou taille modifié depuis le téléchargement",
            )
        if (
            previous_validated_size is not None
            and previous_validated_size > 0
            and actual_size < previous_validated_size * self._min_size_ratio
            and not approve_size_drop
        ):
            raise self._error(
                DataQualityFailed,
                download,
                "IMPLAUSIBLE_SIZE_DROP",
                "chute de taille source non approuvée",
                {
                    "previousByteSize": previous_validated_size,
                    "currentByteSize": actual_size,
                    "minimumRatio": self._min_size_ratio,
                },
            )

        with ExitStack() as stack:
            binary = self._open_payload(stack, download)
            sample = binary.read(64 * 1024)
            binary.seek(0)
            encoding = _detect_encoding(sample, download)
            try:
                text_stream = stack.enter_context(
                    io.TextIOWrapper(binary, encoding=encoding, newline="")
                )
                delimiter = _detect_delimiter(sample.decode(encoding), download)
                header, row_count = _scan_csv(text_stream, delimiter, download)
            except UnicodeDecodeError as error:
                raise self._error(
                    UnexpectedContentType,
                    download,
                    "ENCODING_CHANGED",
                    "encodage incohérent pendant le scan CSV",
                ) from error
        return PhysicalValidationReport(
            byte_size=actual_size,
            sha256=actual_hash,
            compression=download.profile.compression,
            encoding=encoding,
            delimiter=delimiter,
            header=header,
            column_count=len(header),
            row_count=row_count,
        )

    def _open_payload(self, stack: ExitStack, download: SafeDownloadResult) -> BinaryIO:
        path = download.final_path
        try:
            if download.profile.compression == "gzip":
                stream = stack.enter_context(gzip.GzipFile(filename=path, mode="rb"))
                stream.peek(1)
                return cast(BinaryIO, stream)
            if download.profile.compression == "zip":
                archive = stack.enter_context(zipfile.ZipFile(path))
                members = [info for info in archive.infolist() if not info.is_dir()]
                if len(members) != 1 or not members[0].filename.casefold().endswith(".csv"):
                    raise self._error(
                        ArchiveCorrupted,
                        download,
                        "ARCHIVE_LAYOUT_INVALID",
                        "l'archive doit contenir un unique CSV",
                    )
                return cast(BinaryIO, stack.enter_context(archive.open(members[0], "r")))
            return stack.enter_context(path.open("rb"))
        except (gzip.BadGzipFile, zipfile.BadZipFile, EOFError, OSError) as error:
            raise self._error(
                ArchiveCorrupted,
                download,
                "ARCHIVE_CORRUPTED",
                "archive source illisible",
            ) from error

    @staticmethod
    def _error(
        error_type: type[SourceTransportError],
        download: SafeDownloadResult,
        rule: str,
        message: str,
        context: dict[str, str | int | float | bool | None] | None = None,
    ) -> SourceTransportError:
        return error_type(
            message,
            transport=download.transport_receipt.transport,
            source_id=download.source.source_id,
            retryable=False,
            context={"rule": rule, **(context or {})},
        )


def _detect_encoding(sample: bytes, download: SafeDownloadResult) -> str:
    encoding = "utf-8-sig" if sample.startswith(b"\xef\xbb\xbf") else "utf-8"
    try:
        sample.decode(encoding)
    except UnicodeDecodeError as error:
        raise UnexpectedContentType(
            "encodage source non reconnu sans correction",
            transport=download.transport_receipt.transport,
            source_id=download.source.source_id,
            retryable=False,
            context={"rule": "ENCODING_UNSUPPORTED"},
        ) from error
    return encoding


def _detect_delimiter(sample: str, download: SafeDownloadResult) -> str:
    first_line = sample.splitlines()[0] if sample.splitlines() else ""
    counts = {delimiter: first_line.count(delimiter) for delimiter in (",", ";", "\t")}
    maximum = max(counts.values(), default=0)
    winners = [delimiter for delimiter, count in counts.items() if count == maximum and count > 0]
    if len(winners) != 1:
        raise SchemaIncompatible(
            "délimiteur CSV absent ou ambigu",
            transport=download.transport_receipt.transport,
            source_id=download.source.source_id,
            retryable=False,
            context={"rule": "CSV_DELIMITER_INVALID"},
        )
    return winners[0]


def _scan_csv(
    stream: TextIO, delimiter: str, download: SafeDownloadResult
) -> tuple[tuple[str, ...], int]:
    reader = csv.reader(stream, delimiter=delimiter, strict=True)
    try:
        header = tuple(next(reader))
    except (StopIteration, csv.Error) as error:
        raise SchemaIncompatible(
            "en-tête CSV absent",
            transport=download.transport_receipt.transport,
            source_id=download.source.source_id,
            retryable=False,
            context={"rule": "CSV_HEADER_MISSING"},
        ) from error
    normalized = [name.strip() for name in header]
    if (
        len(header) < 2
        or any(not name for name in normalized)
        or len(set(normalized)) != len(normalized)
        or all(name.replace(".", "", 1).isdigit() for name in normalized)
    ):
        raise SchemaIncompatible(
            "en-tête CSV absent ou invalide",
            transport=download.transport_receipt.transport,
            source_id=download.source.source_id,
            retryable=False,
            context={"rule": "CSV_HEADER_INVALID"},
        )
    row_count = 0
    try:
        for line_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise SchemaIncompatible(
                    "nombre de colonnes CSV incohérent",
                    transport=download.transport_receipt.transport,
                    source_id=download.source.source_id,
                    retryable=False,
                    context={
                        "rule": "CSV_COLUMN_COUNT_MISMATCH",
                        "line": line_number,
                        "expected": len(header),
                        "actual": len(row),
                    },
                )
            row_count += 1
    except csv.Error as error:
        raise SchemaIncompatible(
            "syntaxe CSV invalide",
            transport=download.transport_receipt.transport,
            source_id=download.source.source_id,
            retryable=False,
            context={"rule": "CSV_PARSE_ERROR"},
        ) from error
    return tuple(normalized), row_count


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
