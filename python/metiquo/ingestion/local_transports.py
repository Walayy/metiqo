"""Transports locaux contrôlés : miroir validé et fixtures de test."""

from __future__ import annotations

import hashlib
import mimetypes
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Protocol

from metiquo.contracts.enums import DataMode
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime
from metiquo.ingestion.object_store import ObjectStore
from metiquo.ingestion.source_errors import SourceInvalidResponse, SourceNotFound
from metiquo.ingestion.transport import (
    DownloadReceipt,
    SourceMetadata,
    SourceRef,
    SourceTransport,
    TransportPolicy,
)

_COPY_CHUNK_SIZE = 256 * 1024


@dataclass(frozen=True, slots=True)
class MirrorSnapshot:
    year: int
    sha256: str
    byte_size: int
    content_type: str | None
    validated_at: datetime
    source_confirmed_at: datetime | None

    def __post_init__(self) -> None:
        if self.byte_size < 0:
            raise ValueError("byte_size miroir ne peut pas être négatif")
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("sha256 miroir invalide")
        object.__setattr__(self, "validated_at", normalize_utc_datetime(self.validated_at))
        if self.source_confirmed_at is not None:
            object.__setattr__(
                self,
                "source_confirmed_at",
                normalize_utc_datetime(self.source_confirmed_at),
            )


class MirrorSnapshotResolver(Protocol):
    def latest_validated(self, source: SourceRef) -> MirrorSnapshot | None: ...


class MirrorTransport:
    """Copier seulement le dernier snapshot privé déjà validé."""

    def __init__(
        self,
        *,
        policy: TransportPolicy,
        object_store: ObjectStore,
        resolver: MirrorSnapshotResolver,
        clock: Clock | None = None,
    ) -> None:
        self._policy = policy
        self._object_store = object_store
        self._resolver = resolver
        self._clock = clock or SystemClock()

    @property
    def name(self) -> str:
        return "validated-private-mirror"

    @property
    def policy(self) -> TransportPolicy:
        return self._policy

    def probe(self, source: SourceRef) -> SourceMetadata:
        snapshot = self._snapshot(source)
        with self._object_store.open_source(year=snapshot.year, sha256=snapshot.sha256) as stream:
            size = _stream_size(stream)
        if size != snapshot.byte_size:
            raise SourceInvalidResponse(
                "taille du miroir validé divergente",
                transport=self.name,
                source_id=source.source_id,
                retryable=False,
            )
        return SourceMetadata(
            source=source,
            transport=self.name,
            probed_at=self._clock.now().value,
            content_length=size,
            content_type=snapshot.content_type,
            last_modified_at=snapshot.validated_at,
            source_confirmed_at=snapshot.source_confirmed_at,
            checksum_sha256=snapshot.sha256,
        )

    def download(self, source: SourceRef, destination: Path) -> DownloadReceipt:
        snapshot = self._snapshot(source)
        started_at = self._clock.now().value
        with self._object_store.open_source(
            year=snapshot.year, sha256=snapshot.sha256
        ) as source_stream:
            byte_size, digest = _copy_exclusive(
                source_stream,
                destination,
                max_bytes=self.policy.max_download_bytes,
            )
        if byte_size != snapshot.byte_size or digest != snapshot.sha256:
            destination.unlink(missing_ok=True)
            raise SourceInvalidResponse(
                "contenu du miroir validé divergent",
                transport=self.name,
                source_id=source.source_id,
                retryable=False,
            )
        return DownloadReceipt(
            source=source,
            transport=self.name,
            destination=destination,
            byte_size=byte_size,
            sha256=digest,
            started_at=started_at,
            completed_at=self._clock.now().value,
            content_type=snapshot.content_type,
        )

    def _snapshot(self, source: SourceRef) -> MirrorSnapshot:
        snapshot = self._resolver.latest_validated(source)
        if snapshot is None:
            raise SourceNotFound(
                "aucun snapshot miroir validé",
                transport=self.name,
                source_id=source.source_id,
                retryable=False,
            )
        if snapshot.year != source.year:
            raise SourceInvalidResponse(
                "année du miroir validé divergente",
                transport=self.name,
                source_id=source.source_id,
                retryable=False,
            )
        return snapshot


class LocalFixtureTransport:
    """Transport déterministe réservé au mode mock et aux tests."""

    def __init__(
        self,
        *,
        policy: TransportPolicy,
        fixtures: Mapping[str, Path],
        data_mode: DataMode,
        clock: Clock | None = None,
    ) -> None:
        if data_mode is not DataMode.MOCK:
            raise ValueError("LocalFixtureTransport est interdit comme source en mode real")
        self._policy = policy
        self._fixtures = dict(fixtures)
        self._clock = clock or SystemClock()

    @property
    def name(self) -> str:
        return "local-fixture"

    @property
    def policy(self) -> TransportPolicy:
        return self._policy

    def probe(self, source: SourceRef) -> SourceMetadata:
        fixture = self._fixture(source)
        stat = fixture.stat()
        return SourceMetadata(
            source=source,
            transport=self.name,
            probed_at=self._clock.now().value,
            content_length=stat.st_size,
            content_type=mimetypes.guess_type(fixture.name)[0],
            last_modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
            source_confirmed_at=self._clock.now().value,
            checksum_sha256=_hash_file(fixture),
        )

    def download(self, source: SourceRef, destination: Path) -> DownloadReceipt:
        fixture = self._fixture(source)
        started_at = self._clock.now().value
        with fixture.open("rb") as source_stream:
            byte_size, digest = _copy_exclusive(
                source_stream,
                destination,
                max_bytes=self.policy.max_download_bytes,
            )
        return DownloadReceipt(
            source=source,
            transport=self.name,
            destination=destination,
            byte_size=byte_size,
            sha256=digest,
            started_at=started_at,
            completed_at=self._clock.now().value,
            content_type=mimetypes.guess_type(fixture.name)[0],
        )

    def _fixture(self, source: SourceRef) -> Path:
        fixture = self._fixtures.get(source.source_id)
        if fixture is None or not fixture.is_file():
            raise SourceNotFound(
                "fixture locale absente",
                transport=self.name,
                source_id=source.source_id,
                retryable=False,
            )
        return fixture


def prioritized_transports(
    *,
    data_mode: DataMode,
    api: SourceTransport | None,
    public_http: SourceTransport,
    mirror: SourceTransport,
    fixture: SourceTransport | None = None,
) -> Sequence[SourceTransport]:
    """Construire l'ordre explicite sans laisser une fixture entrer en mode réel."""

    if data_mode is DataMode.MOCK:
        if fixture is None or fixture.name != "local-fixture":
            raise ValueError("le mode mock exige LocalFixtureTransport")
        return (fixture,)
    if fixture is not None:
        raise ValueError("une fixture locale est interdite dans le plan de transport real")
    return tuple(transport for transport in (api, public_http, mirror) if transport is not None)


def _copy_exclusive(source: BinaryIO, destination: Path, *, max_bytes: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_size = 0
    created = False
    try:
        output = destination.open("xb")
        created = True
        with output:
            while chunk := source.read(_COPY_CHUNK_SIZE):
                byte_size += len(chunk)
                if byte_size > max_bytes:
                    raise ValueError("source locale trop volumineuse")
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return byte_size, digest.hexdigest()


def _stream_size(stream: BinaryIO) -> int:
    current = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(current)
    return size


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_COPY_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
