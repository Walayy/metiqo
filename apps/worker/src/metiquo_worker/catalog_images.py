import io
import threading
import warnings
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
from metiquo_core.config import Settings
from PIL import Image

from metiquo_worker.artifacts import store_bytes, verify_artifact

_decode_lock = threading.Lock()


def image_url(source: str) -> str:
    parsed = urlsplit(source)
    if (
        parsed.scheme not in ("http", "https")
        or parsed.hostname != "static.lolesports.com"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 80, 443)
    ):
        raise ValueError("Logo URL is not on the official Riot logo host")
    return urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, ""))


def read_response(response: httpx.Response, limit: int) -> bytes:
    response.raise_for_status()
    if response.is_redirect:
        raise ValueError("Unexpected source redirect")
    length = response.headers.get("content-length")
    if length and int(length) > limit:
        raise ValueError("Source exceeds configured download limit")
    data = bytearray()
    for chunk in response.iter_bytes():
        data.extend(chunk)
        if len(data) > limit:
            raise ValueError("Source exceeds configured download limit")
    if not data:
        raise ValueError("Empty source response")
    return bytes(data)


def webp(data: bytes, max_pixels: int = 80_000_000) -> bytes:
    # Some official originals are 8334 x 8334. Decode one image at a time to
    # bound memory, then shrink before converting to avoid a full-size RGBA copy.
    with _decode_lock, warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as picture:
            if picture.format not in ("PNG", "JPEG", "WEBP", "GIF"):
                raise ValueError("Unsupported source logo format")
            if picture.width * picture.height > max_pixels:
                raise ValueError("Source logo dimensions exceed limit")
            picture.load()
            picture.thumbnail((144, 144), Image.Resampling.LANCZOS)
            result = picture.convert("RGBA")
            output = io.BytesIO()
            result.save(output, format="WEBP", quality=88, method=6)
            return output.getvalue()


def fetch_image(
    client: httpx.Client, source: str, previous: dict[str, object], settings: Settings
) -> dict[str, object]:
    url = image_url(source)
    root = settings.artifact_dir
    cached = cache_valid(root, previous)
    headers: dict[str, str] = {}
    if cached:
        for cache_key, header in (("etag", "If-None-Match"), ("lastModified", "If-Modified-Since")):
            value = previous.get(cache_key)
            if isinstance(value, str) and value:
                headers[header] = value
    with client.stream("GET", url, headers=headers) as response:
        if response.status_code == 304:
            if not cached or not headers:
                raise ValueError("Unsolicited logo cache response")
            return previous
        raw = read_response(response, settings.catalog_max_image_bytes)
        encoded = webp(raw, settings.catalog_max_image_pixels)
        source_sha, source_path = store_bytes(root, "originals", raw, "bin")
        digest, path = store_bytes(root, "logos", encoded, "webp")
        return {
            "sourceUrl": source,
            "fetchedUrl": url,
            "sourceSha256": source_sha,
            "sourcePath": source_path,
            "sha256": digest,
            "path": path,
            "etag": response.headers.get("etag"),
            "lastModified": response.headers.get("last-modified"),
        }


def cache_valid(root: Path, item: dict[str, object]) -> bool:
    for path_key, digest_key in (("sourcePath", "sourceSha256"), ("path", "sha256")):
        path, digest = item.get(path_key), item.get(digest_key)
        if not isinstance(path, str) or not isinstance(digest, str):
            return False
        if not verify_artifact(root, path, digest):
            return False
    return True
