"""Téléchargement sûr, borné et promu atomiquement."""

import hashlib
import os
import stat
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path

import pytest

from metiquo.config import Settings
from metiquo.ingestion.safe_download import SafeDownloader
from metiquo.ingestion.source_errors import (
    AtomicPromotionFailed,
    ChecksumMismatch,
    SourceTimeout,
    UnexpectedContentType,
    UnexpectedHtmlResponse,
)
from metiquo.ingestion.transport import (
    DownloadReceipt,
    SourceMetadata,
    SourceRef,
    TransportPolicy,
)

NOW = datetime(2026, 9, 5, 19, tzinfo=UTC)
SOURCE = SourceRef(
    provider="oracles_elixir",
    year=2026,
    source_id="large-stream",
    locator="fixture://large-stream",
    source_name="large.csv",
    mutable=True,
)


def _policy(*, max_bytes: int = 64 * 1024 * 1024, timeout: float = 900) -> TransportPolicy:
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "mock",
            "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "odds_provider": "mock",
            "oe_max_download_bytes": max_bytes,
            "oe_download_timeout_seconds": timeout,
        }
    )
    return TransportPolicy.from_settings(settings)


class GeneratedCsvTransport:
    name = "generated-stream"

    def __init__(
        self,
        *,
        policy: TransportPolicy,
        total_size: int,
        interrupt_after_chunks: int | None = None,
        corrupt_receipt: bool = False,
    ) -> None:
        self._policy = policy
        self.total_size = total_size
        self.interrupt_after_chunks = interrupt_after_chunks
        self.corrupt_receipt = corrupt_receipt
        self.max_chunk_size = 0

    @property
    def policy(self) -> TransportPolicy:
        return self._policy

    def probe(self, source: SourceRef) -> SourceMetadata:
        return SourceMetadata(source, self.name, NOW, content_length=self.total_size)

    def download(self, source: SourceRef, destination: Path) -> DownloadReceipt:
        digest = hashlib.sha256()
        written = 0
        header = b"gameid,league\n"
        with destination.open("xb") as output:
            output.write(header)
            digest.update(header)
            written += len(header)
            chunks = 0
            while written < self.total_size:
                chunk = b"x" * min(64 * 1024, self.total_size - written)
                self.max_chunk_size = max(self.max_chunk_size, len(chunk))
                output.write(chunk)
                digest.update(chunk)
                written += len(chunk)
                chunks += 1
                if self.interrupt_after_chunks == chunks:
                    raise OSError("flux interrompu")
            output.flush()
            os.fsync(output.fileno())
        receipt_hash = "0" * 64 if self.corrupt_receipt else digest.hexdigest()
        return DownloadReceipt(
            source=source,
            transport=self.name,
            destination=destination,
            byte_size=written,
            sha256=receipt_hash,
            started_at=NOW,
            completed_at=NOW,
            content_type="text/csv",
        )


class BytesTransport(GeneratedCsvTransport):
    def __init__(self, payload: bytes, content_type: str) -> None:
        super().__init__(policy=_policy(), total_size=len(payload))
        self.payload = payload
        self.content_type = content_type

    def download(self, source: SourceRef, destination: Path) -> DownloadReceipt:
        destination.write_bytes(self.payload)
        return DownloadReceipt(
            source=source,
            transport=self.name,
            destination=destination,
            byte_size=len(self.payload),
            sha256=hashlib.sha256(self.payload).hexdigest(),
            started_at=NOW,
            completed_at=NOW,
            content_type=self.content_type,
        )


def test_large_stream_is_never_loaded_wholly_and_part_is_hidden(tmp_path: Path) -> None:
    total_size = 32 * 1024 * 1024
    transport = GeneratedCsvTransport(policy=_policy(), total_size=total_size)
    destination = tmp_path / "source.csv"
    tracemalloc.start()

    result = SafeDownloader().download(
        transport=transport,
        source=SOURCE,
        destination=destination,
    )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert result.byte_size == total_size
    assert result.profile.content_type == "text/csv"
    assert result.profile.delimiter == ","
    assert transport.max_chunk_size == 64 * 1024
    assert peak < 8 * 1024 * 1024
    assert not list(tmp_path.rglob("*.part"))
    assert not (tmp_path / ".metiquo-tmp").exists()
    if os.name != "nt":
        assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_interruption_removes_every_temporary(tmp_path: Path) -> None:
    transport = GeneratedCsvTransport(
        policy=_policy(),
        total_size=2 * 1024 * 1024,
        interrupt_after_chunks=2,
    )
    destination = tmp_path / "source.csv"

    with pytest.raises(OSError, match="flux interrompu"):
        SafeDownloader().download(
            transport=transport,
            source=SOURCE,
            destination=destination,
        )

    assert destination.exists() is False
    assert not list(tmp_path.rglob("*.part"))
    assert not (tmp_path / ".metiquo-tmp").exists()


def test_receipt_or_expected_checksum_mismatch_blocks_promotion(tmp_path: Path) -> None:
    corrupt = GeneratedCsvTransport(policy=_policy(), total_size=1024, corrupt_receipt=True)

    with pytest.raises(ChecksumMismatch):
        SafeDownloader().download(
            transport=corrupt,
            source=SOURCE,
            destination=tmp_path / "corrupt.csv",
        )

    valid = GeneratedCsvTransport(policy=_policy(), total_size=1024)
    with pytest.raises(ChecksumMismatch):
        SafeDownloader().download(
            transport=valid,
            source=SOURCE,
            destination=tmp_path / "unexpected.csv",
            expected_sha256="f" * 64,
        )

    assert not list(tmp_path.rglob("*.part"))


@pytest.mark.parametrize(
    ("payload", "content_type", "error_type"),
    [
        (b"<!doctype html><html>quota</html>", "application/octet-stream", UnexpectedHtmlResponse),
        (b"\x00\xff\x00\xff", "application/octet-stream", UnexpectedContentType),
        (b"plain text without delimiter", "text/plain", UnexpectedContentType),
    ],
)
def test_physical_content_is_detected_before_promotion(
    tmp_path: Path,
    payload: bytes,
    content_type: str,
    error_type: type[Exception],
) -> None:
    destination = tmp_path / "source.bin"

    with pytest.raises(error_type):
        SafeDownloader().download(
            transport=BytesTransport(payload, content_type),
            source=SOURCE,
            destination=destination,
        )

    assert destination.exists() is False


def test_gzip_magic_is_detected_without_decompression(tmp_path: Path) -> None:
    payload = b"\x1f\x8b" + b"compressed-placeholder"
    destination = tmp_path / "source.bin"

    result = SafeDownloader().download(
        transport=BytesTransport(payload, "application/octet-stream"),
        source=SOURCE,
        destination=destination,
    )

    assert result.profile.compression == "gzip"
    assert result.profile.content_type == "application/gzip"


def test_total_duration_and_existing_destination_block_promotion(tmp_path: Path) -> None:
    ticks = iter((0.0, 2.0))
    downloader = SafeDownloader(monotonic=lambda: next(ticks))
    slow = GeneratedCsvTransport(policy=_policy(timeout=1), total_size=1024)

    with pytest.raises(SourceTimeout):
        downloader.download(
            transport=slow,
            source=SOURCE,
            destination=tmp_path / "slow.csv",
        )

    destination = tmp_path / "existing.csv"
    destination.write_bytes(b"keep-me")
    with pytest.raises(AtomicPromotionFailed):
        SafeDownloader().download(
            transport=GeneratedCsvTransport(policy=_policy(), total_size=1024),
            source=SOURCE,
            destination=destination,
        )
    assert destination.read_bytes() == b"keep-me"
