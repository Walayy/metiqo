"""Contrats communs à tous les transports de sources Oracle's Elixir."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from metiquo.foundation.time import normalize_utc_datetime

if TYPE_CHECKING:
    from metiquo.config import Settings


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts doit être compris entre 1 et 10")
        if self.base_delay_seconds <= 0 or self.max_delay_seconds <= 0:
            raise ValueError("les délais de retry doivent être positifs")
        if self.base_delay_seconds > self.max_delay_seconds:
            raise ValueError("base_delay_seconds ne peut pas dépasser max_delay_seconds")


@dataclass(frozen=True, slots=True)
class TransportPolicy:
    connect_timeout_seconds: float
    read_timeout_seconds: float
    max_download_bytes: int
    max_redirects: int
    retry: RetryPolicy

    def __post_init__(self) -> None:
        if self.connect_timeout_seconds <= 0 or self.read_timeout_seconds <= 0:
            raise ValueError("les timeouts transport doivent être positifs")
        if self.max_download_bytes <= 0:
            raise ValueError("max_download_bytes doit être positif")
        if not 0 <= self.max_redirects <= 10:
            raise ValueError("max_redirects doit être compris entre 0 et 10")

    @classmethod
    def from_settings(cls, settings: Settings) -> TransportPolicy:
        return cls(
            connect_timeout_seconds=settings.oe_connect_timeout_seconds,
            read_timeout_seconds=settings.oe_read_timeout_seconds,
            max_download_bytes=settings.oe_max_download_bytes,
            max_redirects=settings.oe_max_redirects,
            retry=RetryPolicy(
                max_attempts=settings.oe_retry_max_attempts,
                base_delay_seconds=settings.oe_retry_base_seconds,
                max_delay_seconds=settings.oe_retry_max_seconds,
            ),
        )


@dataclass(frozen=True, slots=True)
class SourceRef:
    provider: str
    year: int
    source_id: str
    locator: str
    source_name: str
    mutable: bool

    def __post_init__(self) -> None:
        if self.provider != "oracles_elixir":
            raise ValueError("le transport LoL accepte uniquement oracles_elixir")
        if not 2014 <= self.year <= 9999:
            raise ValueError("year doit être compris entre 2014 et 9999")
        if not self.source_id.strip() or not self.locator.strip() or not self.source_name.strip():
            raise ValueError("source_id, locator et source_name sont requis")


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source: SourceRef
    transport: str
    probed_at: datetime
    content_length: int | None = None
    content_type: str | None = None
    etag: str | None = None
    last_modified_at: datetime | None = None
    checksum_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.transport.strip():
            raise ValueError("transport est requis")
        object.__setattr__(self, "probed_at", normalize_utc_datetime(self.probed_at))
        if self.last_modified_at is not None:
            object.__setattr__(
                self,
                "last_modified_at",
                normalize_utc_datetime(self.last_modified_at),
            )
        if self.content_length is not None and self.content_length < 0:
            raise ValueError("content_length ne peut pas être négatif")
        _validate_optional_sha256(self.checksum_sha256)


@dataclass(frozen=True, slots=True)
class DownloadReceipt:
    source: SourceRef
    transport: str
    destination: Path
    byte_size: int
    sha256: str
    started_at: datetime
    completed_at: datetime
    content_type: str | None = None
    etag: str | None = None

    def __post_init__(self) -> None:
        if not self.transport.strip():
            raise ValueError("transport est requis")
        if self.byte_size < 0:
            raise ValueError("byte_size ne peut pas être négatif")
        _validate_sha256(self.sha256)
        started_at = normalize_utc_datetime(self.started_at)
        completed_at = normalize_utc_datetime(self.completed_at)
        if completed_at < started_at:
            raise ValueError("completed_at doit être postérieur ou égal à started_at")
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "completed_at", completed_at)


@runtime_checkable
class SourceTransport(Protocol):
    """Sonde et télécharge une source selon une politique entièrement injectée."""

    @property
    def name(self) -> str: ...

    @property
    def policy(self) -> TransportPolicy: ...

    def probe(self, source: SourceRef) -> SourceMetadata: ...

    def download(self, source: SourceRef, destination: Path) -> DownloadReceipt: ...


def _validate_optional_sha256(value: str | None) -> None:
    if value is not None:
        _validate_sha256(value)


def _validate_sha256(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("SHA-256 doit être un digest hexadécimal minuscule de 64 caractères")
