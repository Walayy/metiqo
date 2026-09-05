"""Promotion locale sûre d'un téléchargement transporté en streaming."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from metiquo.ingestion.source_errors import (
    AtomicPromotionFailed,
    ChecksumMismatch,
    SourceTimeout,
    SourceTransportError,
    UnexpectedContentType,
    UnexpectedHtmlResponse,
)
from metiquo.ingestion.transport import DownloadReceipt, SourceRef, SourceTransport

type Compression = Literal["none", "gzip", "zip"]

_SAMPLE_SIZE = 64 * 1024
_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class PhysicalFileProfile:
    content_type: str
    compression: Compression
    encoding: str | None
    delimiter: str | None


@dataclass(frozen=True, slots=True)
class SafeDownloadResult:
    source: SourceRef
    transport_receipt: DownloadReceipt
    final_path: Path
    byte_size: int
    sha256: str
    profile: PhysicalFileProfile


class SafeDownloader:
    """Isoler le ``.part``, vérifier le flux puis publier par rename atomique."""

    def __init__(self, *, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic

    def download(
        self,
        *,
        transport: SourceTransport,
        source: SourceRef,
        destination: Path,
        expected_sha256: str | None = None,
    ) -> SafeDownloadResult:
        if destination.name.endswith(".part"):
            raise ValueError("destination doit désigner le fichier final, pas un .part")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_root = destination.parent / ".metiquo-tmp"
        temporary_root.mkdir(mode=0o700, exist_ok=True)
        temporary_directory = temporary_root / uuid4().hex
        temporary_directory.mkdir(mode=0o700)
        part = temporary_directory / f"{destination.name}.part"
        started = self._monotonic()

        try:
            receipt = transport.download(source, part)
            elapsed = self._monotonic() - started
            if elapsed > transport.policy.download_timeout_seconds:
                raise self._error(
                    SourceTimeout,
                    transport,
                    source,
                    "durée totale de téléchargement dépassée",
                    retryable=True,
                )
            if receipt.destination != part:
                raise self._error(
                    AtomicPromotionFailed,
                    transport,
                    source,
                    "le transport a écrit hors du fichier temporaire réservé",
                )
            if receipt.source != source or receipt.transport != transport.name:
                raise self._error(
                    AtomicPromotionFailed,
                    transport,
                    source,
                    "le reçu ne correspond pas à la source ou au transport demandé",
                )
            os.chmod(part, 0o600)
            actual_size = part.stat().st_size
            actual_hash = _hash_file(part)
            if receipt.byte_size != actual_size or receipt.sha256 != actual_hash:
                raise self._error(
                    ChecksumMismatch,
                    transport,
                    source,
                    "empreinte ou taille du reçu de transport incohérente",
                )
            if expected_sha256 is not None and actual_hash != expected_sha256:
                raise self._error(
                    ChecksumMismatch,
                    transport,
                    source,
                    "empreinte téléchargée différente de l'empreinte attendue",
                )
            profile = _inspect_physical_file(part, receipt.content_type, transport, source)
            if destination.exists():
                raise self._error(
                    AtomicPromotionFailed,
                    transport,
                    source,
                    "la destination finale existe déjà",
                )
            try:
                part.rename(destination)
            except OSError as error:
                raise self._error(
                    AtomicPromotionFailed,
                    transport,
                    source,
                    "promotion atomique du téléchargement impossible",
                ) from error
            return SafeDownloadResult(
                source=source,
                transport_receipt=receipt,
                final_path=destination,
                byte_size=actual_size,
                sha256=actual_hash,
                profile=profile,
            )
        finally:
            shutil.rmtree(temporary_directory, ignore_errors=True)
            with suppress(OSError):
                temporary_root.rmdir()

    @staticmethod
    def _error(
        error_type: type[SourceTransportError],
        transport: SourceTransport,
        source: SourceRef,
        message: str,
        *,
        retryable: bool = False,
    ) -> SourceTransportError:
        return error_type(
            message,
            transport=transport.name,
            source_id=source.source_id,
            retryable=retryable,
        )


def _inspect_physical_file(
    path: Path,
    declared_content_type: str | None,
    transport: SourceTransport,
    source: SourceRef,
) -> PhysicalFileProfile:
    with path.open("rb") as stream:
        sample = stream.read(_SAMPLE_SIZE)
    prefix = sample.lstrip().lower()
    declared = (declared_content_type or "").partition(";")[0].strip().casefold()
    if not sample:
        raise UnexpectedContentType(
            "corps source vide",
            transport=transport.name,
            source_id=source.source_id,
            retryable=False,
            context={"rule": "EMPTY_BODY"},
        )
    if prefix.startswith((b"<!doctype html", b"<html")) or declared in {
        "text/html",
        "application/xhtml+xml",
    }:
        raise UnexpectedHtmlResponse(
            "contenu HTML refusé pendant la validation physique",
            transport=transport.name,
            source_id=source.source_id,
            retryable=False,
            context={"rule": "HTML_BODY"},
        )
    if prefix.startswith((b"{", b"[")):
        try:
            json.loads(sample)
        except json.JSONDecodeError:
            pass
        else:
            raise UnexpectedContentType(
                "corps JSON d'erreur refusé",
                transport=transport.name,
                source_id=source.source_id,
                retryable=False,
                context={"rule": "JSON_ERROR_BODY"},
            )
    if sample.startswith(b"\x1f\x8b"):
        if declared.startswith("text/"):
            raise UnexpectedContentType(
                "magic gzip incompatible avec le type de contenu déclaré",
                transport=transport.name,
                source_id=source.source_id,
                retryable=False,
                context={"rule": "MIME_MAGIC_MISMATCH"},
            )
        return PhysicalFileProfile("application/gzip", "gzip", None, None)
    if sample.startswith(b"PK\x03\x04"):
        if declared.startswith("text/"):
            raise UnexpectedContentType(
                "magic zip incompatible avec le type de contenu déclaré",
                transport=transport.name,
                source_id=source.source_id,
                retryable=False,
                context={"rule": "MIME_MAGIC_MISMATCH"},
            )
        return PhysicalFileProfile("application/zip", "zip", None, None)

    try:
        decoded = sample.decode("utf-8")
    except UnicodeDecodeError as error:
        raise UnexpectedContentType(
            "source ni archive reconnue ni texte UTF-8",
            transport=transport.name,
            source_id=source.source_id,
            retryable=False,
            context={"rule": "UNKNOWN_ENCODING"},
        ) from error
    first_line = decoded.splitlines()[0] if decoded.splitlines() else ""
    delimiter = _detect_delimiter(first_line)
    if delimiter is None:
        raise UnexpectedContentType(
            "délimiteur CSV non détecté sans ambiguïté",
            transport=transport.name,
            source_id=source.source_id,
            retryable=False,
            context={"rule": "DELIMITER_AMBIGUOUS"},
        )
    if declared and declared not in {
        "application/csv",
        "application/octet-stream",
        "text/csv",
        "text/plain",
    }:
        raise UnexpectedContentType(
            "type de contenu incompatible avec le CSV détecté",
            transport=transport.name,
            source_id=source.source_id,
            retryable=False,
            context={"rule": "MIME_CSV_MISMATCH"},
        )
    return PhysicalFileProfile("text/csv", "none", "utf-8", delimiter)


def _detect_delimiter(first_line: str) -> str | None:
    counts = {delimiter: first_line.count(delimiter) for delimiter in (",", ";", "\t")}
    best = max(counts.values(), default=0)
    winners = [delimiter for delimiter, count in counts.items() if count == best and count > 0]
    return winners[0] if len(winners) == 1 else None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
