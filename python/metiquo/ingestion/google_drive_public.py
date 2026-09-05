"""Transport HTTP public Google Drive sans contournement des pages intermédiaires."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from itertools import chain
from pathlib import Path
from typing import Any, NoReturn, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from metiquo.foundation.time import Clock, SystemClock
from metiquo.ingestion.source_errors import (
    SourceNotFound,
    SourcePermissionDenied,
    SourceRateLimited,
    SourceTimeout,
    SourceTooLarge,
    SourceTransportError,
    SourceUnavailable,
    UnexpectedHtmlResponse,
)
from metiquo.ingestion.transport import (
    DownloadReceipt,
    SourceMetadata,
    SourceRef,
    TransportPolicy,
)

_PUBLIC_ENDPOINT = "https://drive.google.com/uc"
_CHUNK_SIZE = 256 * 1024
_ERROR_BODY_LIMIT = 64 * 1024


@dataclass(frozen=True, slots=True)
class PublicHttpStream:
    status: int
    headers: Mapping[str, str]
    chunks: Iterable[bytes]


class PublicHttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        max_redirects: int,
    ) -> PublicHttpStream: ...


class UrllibPublicHttpClient:
    def get(
        self,
        url: str,
        *,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        max_redirects: int,
    ) -> PublicHttpStream:
        request = Request(
            url,
            headers={
                "Accept": "application/octet-stream,text/csv,application/gzip",
                "User-Agent": "Metiquo/0.1 drive-public",
            },
        )
        opener = build_opener(_LimitedRedirectHandler(max_redirects))
        try:
            response = opener.open(
                request,
                timeout=min(connect_timeout_seconds, read_timeout_seconds),
            )
        except HTTPError as error:
            return PublicHttpStream(
                error.code,
                _normalize_headers(error.headers),
                _response_chunks(error),
            )
        except (URLError, TimeoutError, OSError) as error:
            raise TimeoutError("Google Drive public indisponible") from error
        return PublicHttpStream(
            int(response.status),
            _normalize_headers(response.headers),
            _response_chunks(response),
        )


class GoogleDrivePublicHttpTransport:
    """Téléchargement public borné qui refuse toute page HTML intermédiaire."""

    def __init__(
        self,
        *,
        policy: TransportPolicy,
        client: PublicHttpClient | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._policy = policy
        self._client = client or UrllibPublicHttpClient()
        self._clock = clock or SystemClock()

    @property
    def name(self) -> str:
        return "google-drive-public-http"

    @property
    def policy(self) -> TransportPolicy:
        return self._policy

    def probe(self, source: SourceRef) -> SourceMetadata:
        stream = self._request(source)
        iterator = iter(stream.chunks)
        try:
            first_chunk = next(iterator, b"")
            self._reject_html(stream.headers, first_chunk, source)
            if not 200 <= stream.status < 300:
                _bounded_body(first_chunk, iterator, _ERROR_BODY_LIMIT)
                self._raise_for_status(stream.status, source)
            content_length = _content_length(stream.headers)
            if content_length is not None and content_length > self.policy.max_download_bytes:
                raise self._error(SourceTooLarge, source, "source publique trop volumineuse")
            return SourceMetadata(
                source=source,
                transport=self.name,
                probed_at=self._clock.now().value,
                content_length=content_length,
                content_type=stream.headers.get("content-type"),
                etag=stream.headers.get("etag"),
                last_modified_at=_last_modified(stream.headers),
            )
        finally:
            _close_iterator(iterator)

    def download(self, source: SourceRef, destination: Path) -> DownloadReceipt:
        started_at = self._clock.now().value
        stream = self._request(source)
        iterator = iter(stream.chunks)
        created = False
        try:
            first_chunk = next(iterator, b"")
            self._reject_html(stream.headers, first_chunk, source)
            if not 200 <= stream.status < 300:
                _bounded_body(first_chunk, iterator, _ERROR_BODY_LIMIT)
                self._raise_for_status(stream.status, source)
            announced_size = _content_length(stream.headers)
            if announced_size is not None and announced_size > self.policy.max_download_bytes:
                raise self._error(SourceTooLarge, source, "source publique trop volumineuse")

            digest = hashlib.sha256()
            byte_size = 0
            output = destination.open("xb")
            created = True
            with output:
                for chunk in chain((first_chunk,), iterator):
                    if not isinstance(chunk, bytes):
                        raise TypeError("fragment HTTP public non binaire")
                    byte_size += len(chunk)
                    if byte_size > self.policy.max_download_bytes:
                        raise self._error(
                            SourceTooLarge, source, "source publique trop volumineuse"
                        )
                    output.write(chunk)
                    digest.update(chunk)
                output.flush()
                os.fsync(output.fileno())
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
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise
        finally:
            _close_iterator(iterator)

    def _request(self, source: SourceRef) -> PublicHttpStream:
        query = urlencode({"export": "download", "id": source.source_id})
        url = f"{_PUBLIC_ENDPOINT}?{query}"
        try:
            return self._client.get(
                url,
                connect_timeout_seconds=self.policy.connect_timeout_seconds,
                read_timeout_seconds=self.policy.read_timeout_seconds,
                max_redirects=self.policy.max_redirects,
            )
        except TimeoutError as error:
            raise self._error(SourceTimeout, source, "timeout Google Drive public") from error

    def _reject_html(
        self, headers: Mapping[str, str], first_chunk: bytes, source: SourceRef
    ) -> None:
        content_type = headers.get("content-type", "").casefold()
        prefix = first_chunk[:4096].lstrip().lower()
        if (
            "text/html" not in content_type
            and "application/xhtml+xml" not in content_type
            and not prefix.startswith((b"<!doctype html", b"<html"))
        ):
            return
        if b"quota" in prefix:
            message = "page HTML de quota Drive refusée"
        elif b"consent" in prefix or b"confirm" in prefix:
            message = "page HTML de consentement Drive refusée"
        elif b"login" in prefix or b"accounts.google" in prefix:
            message = "page HTML de connexion Drive refusée"
        else:
            message = "réponse HTML Drive inattendue refusée"
        raise self._error(UnexpectedHtmlResponse, source, message)

    def _raise_for_status(self, status: int, source: SourceRef) -> NoReturn:
        if status == 404:
            raise self._error(SourceNotFound, source, "source Drive publique introuvable", status)
        if status == 429:
            raise self._error(SourceRateLimited, source, "limite de débit Drive atteinte", status)
        if status in {401, 403}:
            raise self._error(SourcePermissionDenied, source, "accès Drive public refusé", status)
        raise self._error(SourceUnavailable, source, "Google Drive public indisponible", status)

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
            retryable=error_type in {SourceRateLimited, SourceTimeout, SourceUnavailable},
            http_status=status,
        )


def _bounded_body(first: bytes, chunks: Iterable[bytes], limit: int) -> bytes:
    body = bytearray(first)
    for chunk in chunks:
        body.extend(chunk)
        if len(body) > limit:
            break
    return bytes(body[:limit])


def _response_chunks(response: Any) -> Iterable[bytes]:
    try:
        while chunk := cast(bytes, response.read(_CHUNK_SIZE)):
            yield chunk
    finally:
        response.close()


def _close_iterator(iterator: object) -> None:
    close = getattr(iterator, "close", None)
    if callable(close):
        close()


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


def _content_length(headers: Mapping[str, str]) -> int | None:
    value = headers.get("content-length")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _last_modified(headers: Mapping[str, str]) -> datetime | None:
    value = headers.get("last-modified")
    if value is None:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(UTC)
