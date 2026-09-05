"""Transport officiel Google Drive API v3, activé par credential autorisé."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import SecretStr

from metiquo.config import Settings
from metiquo.foundation.time import Clock, SystemClock
from metiquo.ingestion.source_errors import (
    SourceInvalidResponse,
    SourceNotFound,
    SourcePermissionDenied,
    SourceQuotaExceeded,
    SourceRateLimited,
    SourceTimeout,
    SourceTooLarge,
    SourceTransportError,
    SourceUnavailable,
)
from metiquo.ingestion.transport import (
    DownloadReceipt,
    SourceMetadata,
    SourceRef,
    TransportPolicy,
)

_API_ROOT = "https://www.googleapis.com/drive/v3/files"
_METADATA_FIELDS = "id,name,mimeType,size,modifiedTime"
_CHUNK_SIZE = 256 * 1024
_ERROR_BODY_LIMIT = 64 * 1024


@dataclass(frozen=True, slots=True)
class DriveHttpStream:
    status: int
    headers: Mapping[str, str]
    chunks: Iterable[bytes]


class DriveApiClient(Protocol):
    def get(
        self,
        url: str,
        *,
        bearer: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        max_redirects: int,
    ) -> DriveHttpStream: ...


class UrllibDriveApiClient:
    """Adaptateur standard-library conservant la réponse sous forme de flux."""

    def get(
        self,
        url: str,
        *,
        bearer: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        max_redirects: int,
    ) -> DriveHttpStream:
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {bearer}",
                "Accept": "application/json, application/octet-stream",
                "User-Agent": "Metiquo/0.1 drive-api",
            },
        )
        opener = build_opener(_LimitedRedirectHandler(max_redirects))
        try:
            response = opener.open(
                request,
                timeout=min(connect_timeout_seconds, read_timeout_seconds),
            )
        except HTTPError as error:
            return DriveHttpStream(
                status=error.code,
                headers=_normalize_headers(error.headers),
                chunks=_response_chunks(error),
            )
        except (URLError, TimeoutError, OSError) as error:
            raise TimeoutError("Google Drive API indisponible") from error
        return DriveHttpStream(
            status=int(response.status),
            headers=_normalize_headers(response.headers),
            chunks=_response_chunks(response),
        )


class GoogleDriveApiTransport:
    """Sonde et télécharge via l'API Drive sans jamais exposer le bearer."""

    def __init__(
        self,
        *,
        policy: TransportPolicy,
        bearer: SecretStr,
        client: DriveApiClient | None = None,
        clock: Clock | None = None,
    ) -> None:
        if not bearer.get_secret_value().strip():
            raise ValueError("un credential Google Drive non vide est requis")
        self._policy = policy
        self._bearer = bearer
        self._client = client or UrllibDriveApiClient()
        self._clock = clock or SystemClock()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        client: DriveApiClient | None = None,
        clock: Clock | None = None,
    ) -> GoogleDriveApiTransport | None:
        if settings.oe_google_drive_bearer is None:
            return None
        return cls(
            policy=TransportPolicy.from_settings(settings),
            bearer=settings.oe_google_drive_bearer,
            client=client,
            clock=clock,
        )

    @property
    def name(self) -> str:
        return "google-drive-api"

    @property
    def policy(self) -> TransportPolicy:
        return self._policy

    def probe(self, source: SourceRef) -> SourceMetadata:
        source_url = f"{_API_ROOT}/{quote(source.source_id, safe='')}"
        url = f"{source_url}?{urlencode({'fields': _METADATA_FIELDS})}"
        stream = self._request(url, source)
        body = self._read_bounded(stream.chunks, _ERROR_BODY_LIMIT, source)
        self._raise_for_status(stream.status, body, source)
        try:
            payload = cast(dict[str, Any], json.loads(body))
            if payload.get("id") != source.source_id:
                raise ValueError("ID Drive divergent")
            size_value = payload.get("size")
            content_length = int(size_value) if size_value is not None else None
            modified_value = payload.get("modifiedTime")
            modified_at = _parse_google_datetime(modified_value) if modified_value else None
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise self._error(
                SourceInvalidResponse, source, "métadonnées Drive invalides"
            ) from error
        if content_length is not None and content_length > self.policy.max_download_bytes:
            raise self._error(SourceTooLarge, source, "source Drive trop volumineuse")
        return SourceMetadata(
            source=source,
            transport=self.name,
            probed_at=self._clock.now().value,
            content_length=content_length,
            content_type=_optional_string(payload.get("mimeType")),
            etag=stream.headers.get("etag"),
            last_modified_at=modified_at,
        )

    def download(self, source: SourceRef, destination: Path) -> DownloadReceipt:
        started_at = self._clock.now().value
        url = f"{_API_ROOT}/{quote(source.source_id, safe='')}?alt=media"
        stream = self._request(url, source)
        if not 200 <= stream.status < 300:
            body = self._read_bounded(stream.chunks, _ERROR_BODY_LIMIT, source)
            self._raise_for_status(stream.status, body, source)
        announced_size = _content_length(stream.headers)
        if announced_size is not None and announced_size > self.policy.max_download_bytes:
            raise self._error(SourceTooLarge, source, "source Drive trop volumineuse")

        digest = hashlib.sha256()
        byte_size = 0
        created = False
        try:
            output = destination.open("xb")
            created = True
            with output:
                for chunk in stream.chunks:
                    if not isinstance(chunk, bytes):
                        raise self._error(
                            SourceInvalidResponse, source, "fragment Drive non binaire"
                        )
                    byte_size += len(chunk)
                    if byte_size > self.policy.max_download_bytes:
                        raise self._error(SourceTooLarge, source, "source Drive trop volumineuse")
                    output.write(chunk)
                    digest.update(chunk)
                output.flush()
                os.fsync(output.fileno())
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise
        return DownloadReceipt(
            source=source,
            transport=self.name,
            destination=destination,
            byte_size=byte_size,
            sha256=digest.hexdigest(),
            started_at=started_at,
            completed_at=self._clock.now().value,
            content_type=stream.headers.get("content-type"),
            etag=stream.headers.get("etag"),
        )

    def _request(self, url: str, source: SourceRef) -> DriveHttpStream:
        try:
            return self._client.get(
                url,
                bearer=self._bearer.get_secret_value(),
                connect_timeout_seconds=self.policy.connect_timeout_seconds,
                read_timeout_seconds=self.policy.read_timeout_seconds,
                max_redirects=self.policy.max_redirects,
            )
        except TimeoutError as error:
            raise self._error(SourceTimeout, source, "timeout Google Drive API") from error

    def _raise_for_status(self, status: int, body: bytes, source: SourceRef) -> None:
        if 200 <= status < 300:
            return
        reason = _google_error_reason(body)
        if status == 404:
            raise self._error(SourceNotFound, source, "source Drive introuvable", status)
        if status == 429 or reason in {"rateLimitExceeded", "userRateLimitExceeded"}:
            raise self._error(SourceRateLimited, source, "limite de débit Drive atteinte", status)
        if reason in {"dailyLimitExceeded", "downloadQuotaExceeded", "storageQuotaExceeded"}:
            raise self._error(SourceQuotaExceeded, source, "quota Drive atteint", status)
        if status in {401, 403}:
            raise self._error(SourcePermissionDenied, source, "accès Drive refusé", status)
        raise self._error(SourceUnavailable, source, "Google Drive API indisponible", status)

    def _read_bounded(self, chunks: Iterable[bytes], limit: int, source: SourceRef) -> bytes:
        body = bytearray()
        for chunk in chunks:
            body.extend(chunk)
            if len(body) > limit:
                raise self._error(SourceInvalidResponse, source, "réponse Drive trop volumineuse")
        return bytes(body)

    def _error(
        self,
        error_type: type[SourceTransportError],
        source: SourceRef,
        message: str,
        status: int | None = None,
    ) -> SourceTransportError:
        return error_type(
            message,
            transport=self.name,
            source_id=source.source_id,
            retryable=error_type
            in {SourceQuotaExceeded, SourceRateLimited, SourceTimeout, SourceUnavailable},
            http_status=status,
        )


def _response_chunks(response: Any) -> Iterable[bytes]:
    try:
        while chunk := cast(bytes, response.read(_CHUNK_SIZE)):
            yield chunk
    finally:
        response.close()


class _LimitedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, maximum: int) -> None:
        self._maximum = maximum

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        count = int(getattr(req, "_metiquo_redirect_count", 0))
        if count >= self._maximum:
            raise HTTPError(req.full_url, code, "limite de redirections atteinte", headers, fp)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            cast(Any, redirected)._metiquo_redirect_count = count + 1
        return redirected


def _normalize_headers(headers: Any) -> dict[str, str]:
    return {str(key).casefold(): str(value) for key, value in headers.items()}


def _google_error_reason(body: bytes) -> str | None:
    try:
        payload = json.loads(body)
        return cast(str, payload["error"]["errors"][0]["reason"])
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None


def _parse_google_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("modifiedTime Drive invalide")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _content_length(headers: Mapping[str, str]) -> int | None:
    value = headers.get("content-length")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
