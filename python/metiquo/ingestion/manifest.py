"""Manifeste immuable et empreinte de schéma d'un snapshot Oracle's Elixir."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from metiquo.foundation.time import normalize_utc_datetime
from metiquo.ingestion.object_store import ObjectStore, StoredObject
from metiquo.ingestion.safe_download import SafeDownloadResult
from metiquo.ingestion.source_errors import ChecksumMismatch
from metiquo.ingestion.transport import SourceMetadata, SourceRef

type QualityStatus = Literal["passed", "failed", "capability-only"]
type QualityValue = str | int | float | bool | None

_READ_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ColumnDefinition:
    position: int
    name: str
    data_type: str
    nullable: bool

    def __post_init__(self) -> None:
        if self.position < 0 or not self.name.strip() or not self.data_type.strip():
            raise ValueError("définition de colonne invalide")

    def to_dict(self) -> dict[str, object]:
        return {
            "position": self.position,
            "name": self.name,
            "dataType": self.data_type,
            "nullable": self.nullable,
        }


@dataclass(frozen=True, slots=True)
class SchemaDocument:
    columns: tuple[ColumnDefinition, ...]

    def __post_init__(self) -> None:
        if not self.columns:
            raise ValueError("le schéma doit contenir au moins une colonne")
        positions = [column.position for column in self.columns]
        names = [column.name for column in self.columns]
        if positions != list(range(len(self.columns))):
            raise ValueError("les positions de colonnes doivent être consécutives")
        if len(set(names)) != len(names):
            raise ValueError("les noms de colonnes doivent être uniques")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(_canonical_json(self._columns_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaFingerprint": self.fingerprint,
            "columns": self._columns_dict(),
        }

    def _columns_dict(self) -> list[dict[str, object]]:
        return [column.to_dict() for column in self.columns]


@dataclass(frozen=True, slots=True)
class SnapshotManifest:
    provider: str
    season_year: int
    drive_file_id: str
    requested_at: datetime
    downloaded_at: datetime
    transport: str
    byte_size: int
    sha256: str
    content_type_observed: str
    compression: str
    encoding: str | None
    delimiter: str | None
    schema_fingerprint: str
    row_count: int
    min_event_date: datetime | None
    max_event_date: datetime | None
    quality_status: QualityStatus
    quality: Mapping[str, QualityValue]
    ingestion_code_version: str
    source_confirmed_at: datetime | None = None
    manifest_version: int = 1

    def __post_init__(self) -> None:
        if self.manifest_version != 1:
            raise ValueError("manifestVersion non supportée")
        if self.provider != "oracles_elixir":
            raise ValueError("provider du manifeste invalide")
        if not 2014 <= self.season_year <= 9999:
            raise ValueError("seasonYear du manifeste invalide")
        if not self.drive_file_id.strip() or not self.transport.strip():
            raise ValueError("identité source du manifeste incomplète")
        if self.byte_size < 0 or self.row_count < 0:
            raise ValueError("tailles du manifeste invalides")
        if self.quality_status not in {"passed", "failed", "capability-only"}:
            raise ValueError("qualityStatus du manifeste invalide")
        if self.compression not in {"none", "gzip", "zip"}:
            raise ValueError("compression du manifeste invalide")
        _validate_sha256(self.sha256, "sha256")
        _validate_sha256(self.schema_fingerprint, "schemaFingerprint")
        if not self.ingestion_code_version.strip():
            raise ValueError("ingestionCodeVersion est requis")
        requested_at = normalize_utc_datetime(self.requested_at)
        downloaded_at = normalize_utc_datetime(self.downloaded_at)
        if downloaded_at < requested_at:
            raise ValueError("downloadedAt doit suivre requestedAt")
        object.__setattr__(self, "requested_at", requested_at)
        object.__setattr__(self, "downloaded_at", downloaded_at)
        object.__setattr__(self, "quality", MappingProxyType(dict(self.quality)))
        for name in ("min_event_date", "max_event_date", "source_confirmed_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_utc_datetime(value))
        if (
            self.min_event_date is not None
            and self.max_event_date is not None
            and self.max_event_date < self.min_event_date
        ):
            raise ValueError("maxEventDate doit suivre minEventDate")

    def to_dict(self) -> dict[str, object]:
        return {
            "manifestVersion": self.manifest_version,
            "provider": self.provider,
            "seasonYear": self.season_year,
            "driveFileId": self.drive_file_id,
            "requestedAt": _isoformat(self.requested_at),
            "downloadedAt": _isoformat(self.downloaded_at),
            "sourceConfirmedAt": _optional_isoformat(self.source_confirmed_at),
            "transport": self.transport,
            "byteSize": self.byte_size,
            "sha256": self.sha256,
            "contentTypeObserved": self.content_type_observed,
            "compression": self.compression,
            "encoding": self.encoding,
            "delimiter": self.delimiter,
            "schemaFingerprint": self.schema_fingerprint,
            "rowCount": self.row_count,
            "minEventDate": _optional_isoformat(self.min_event_date),
            "maxEventDate": _optional_isoformat(self.max_event_date),
            "qualityStatus": self.quality_status,
            "quality": dict(self.quality),
            "ingestionCodeVersion": self.ingestion_code_version,
        }

    def to_json_bytes(self) -> bytes:
        return _canonical_json(self.to_dict()) + b"\n"

    @classmethod
    def from_json_bytes(cls, payload: bytes) -> SnapshotManifest:
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ValueError("manifest JSON invalide") from error
        if not isinstance(value, dict):
            raise ValueError("racine du manifeste invalide")
        document = cast(dict[str, Any], value)
        quality = document.get("quality")
        if not isinstance(quality, dict):
            raise ValueError("rapport qualité du manifeste invalide")
        return cls(
            manifest_version=int(document["manifestVersion"]),
            provider=str(document["provider"]),
            season_year=int(document["seasonYear"]),
            drive_file_id=str(document["driveFileId"]),
            requested_at=_parse_datetime(document["requestedAt"]),
            downloaded_at=_parse_datetime(document["downloadedAt"]),
            source_confirmed_at=_parse_optional_datetime(document.get("sourceConfirmedAt")),
            transport=str(document["transport"]),
            byte_size=int(document["byteSize"]),
            sha256=str(document["sha256"]),
            content_type_observed=str(document["contentTypeObserved"]),
            compression=str(document["compression"]),
            encoding=_optional_string(document.get("encoding")),
            delimiter=_optional_string(document.get("delimiter")),
            schema_fingerprint=str(document["schemaFingerprint"]),
            row_count=int(document["rowCount"]),
            min_event_date=_parse_optional_datetime(document.get("minEventDate")),
            max_event_date=_parse_optional_datetime(document.get("maxEventDate")),
            quality_status=cast(QualityStatus, document["qualityStatus"]),
            quality=cast(dict[str, QualityValue], quality),
            ingestion_code_version=str(document["ingestionCodeVersion"]),
        )


def build_snapshot_manifest(
    *,
    source: SourceRef,
    metadata: SourceMetadata,
    download: SafeDownloadResult,
    schema: SchemaDocument,
    row_count: int,
    min_event_date: datetime | None,
    max_event_date: datetime | None,
    quality_status: QualityStatus,
    quality: Mapping[str, QualityValue],
    ingestion_code_version: str,
) -> SnapshotManifest:
    if metadata.source != source or download.source != source:
        raise ValueError("source incohérente entre metadata, download et manifeste")
    return SnapshotManifest(
        provider=source.provider,
        season_year=source.year,
        drive_file_id=source.source_id,
        requested_at=download.transport_receipt.started_at,
        downloaded_at=download.transport_receipt.completed_at,
        source_confirmed_at=metadata.source_confirmed_at,
        transport=download.transport_receipt.transport,
        byte_size=download.byte_size,
        sha256=download.sha256,
        content_type_observed=download.profile.content_type,
        compression=download.profile.compression,
        encoding=download.profile.encoding,
        delimiter=download.profile.delimiter,
        schema_fingerprint=schema.fingerprint,
        row_count=row_count,
        min_event_date=min_event_date,
        max_event_date=max_event_date,
        quality_status=quality_status,
        quality=quality,
        ingestion_code_version=ingestion_code_version,
    )


def store_snapshot(
    *,
    object_store: ObjectStore,
    download: SafeDownloadResult,
    manifest: SnapshotManifest,
    schema: SchemaDocument,
) -> StoredObject:
    if manifest.sha256 != download.sha256 or manifest.byte_size != download.byte_size:
        raise _checksum_error(download, "manifeste incohérent avec le téléchargement")
    if manifest.schema_fingerprint != schema.fingerprint:
        raise _checksum_error(download, "empreinte de schéma incohérente")
    source_kind: Literal["bin", "csv"] = (
        "csv" if download.profile.content_type == "text/csv" else "bin"
    )
    stored = object_store.put_source(
        year=manifest.season_year,
        chunks=_file_chunks(download.final_path),
        source_kind=source_kind,
        manifest=manifest.to_dict(),
        schema=schema.to_dict(),
        quality_report={"status": manifest.quality_status, **manifest.quality},
    )
    with object_store.open_source(year=stored.year, sha256=stored.sha256) as stream:
        reread_hash = _hash_chunks(iter(lambda: stream.read(_READ_CHUNK_SIZE), b""))
    if stored.sha256 != manifest.sha256 or reread_hash != manifest.sha256:
        raise _checksum_error(download, "empreinte différente après stockage et relecture")
    return stored


def _file_chunks(path: Path) -> Iterable[bytes]:
    with path.open("rb") as stream:
        while chunk := stream.read(_READ_CHUNK_SIZE):
            yield chunk


def _hash_chunks(chunks: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def _checksum_error(download: SafeDownloadResult, message: str) -> ChecksumMismatch:
    return ChecksumMismatch(
        message,
        transport=download.transport_receipt.transport,
        source_id=download.source.source_id,
        retryable=False,
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _isoformat(value: datetime) -> str:
    return normalize_utc_datetime(value).isoformat().replace("+00:00", "Z")


def _optional_isoformat(value: datetime | None) -> str | None:
    return _isoformat(value) if value is not None else None


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp du manifeste invalide")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_optional_datetime(value: object) -> datetime | None:
    return None if value is None else _parse_datetime(value)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _validate_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} doit être un SHA-256 hexadécimal")
