import base64
import csv
import hashlib
import os
import re
import shutil
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

FILENAME = re.compile(r"^(\d{4})_LoL_esports_match_data_from_OraclesElixir\.csv$")
REQUIRED_COLUMNS = {"gameid", "participantid", "teamid", "playerid", "date", "year", "league"}


@dataclass(frozen=True)
class SourceFile:
    id: str
    name: str
    year: int


@dataclass(frozen=True)
class ValidatedFile:
    source: SourceFile
    path: Path
    sha256: str
    byte_count: int
    row_count: int
    columns: list[str]


def is_export_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "storage.googleapis.com"
        and parsed.port in (None, 443)
        and parsed.username is None
        and parsed.password is None
        and parsed.path.startswith("/drive-bulk-export-anonymous/")
    )


def download_export(url: str, target: Path, max_bytes: int) -> None:
    if not is_export_url(url):
        raise ValueError("Unexpected Drive export destination")
    md5 = hashlib.md5(usedforsecurity=False)
    byte_count = 0
    with httpx.stream("GET", url, timeout=httpx.Timeout(120, connect=30)) as response:
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError("Unexpected archive redirect")
        if "text/html" in response.headers.get("content-type", "").lower():
            raise ValueError("Drive returned an HTML page instead of an archive")
        length = response.headers.get("content-length")
        if length and int(length) > max_bytes:
            raise ValueError("Archive exceeds configured download limit")
        with target.open("wb") as output:
            for chunk in response.iter_bytes(1024 * 1024):
                byte_count += len(chunk)
                if byte_count > max_bytes:
                    raise ValueError("Archive exceeds configured download limit")
                md5.update(chunk)
                output.write(chunk)
        if length and byte_count != int(length):
            raise ValueError("Truncated archive")
        hashes = response.headers.get("x-goog-hash", "")
        expected = next(
            (h.strip()[4:] for h in hashes.split(",") if h.strip().startswith("md5=")), None
        )
        if expected and base64.b64encode(md5.digest()).decode() != expected:
            raise ValueError("GCS archive checksum mismatch")


def csv_records(path: Path) -> Iterator[dict[str, str]]:
    csv.field_size_limit(2_000_000)
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        columns = next(reader, [])
        if len(columns) != len(set(columns)) or not REQUIRED_COLUMNS.issubset(columns):
            raise ValueError("CSV header missing required columns or containing duplicate columns")
        for index, row in enumerate(reader, start=2):
            if len(row) != len(columns):
                raise ValueError(f"CSV row {index} has an invalid number of columns")
            yield dict(zip(columns, row, strict=True))


def validate_archive(
    archive: Path, expected: list[SourceFile], staging: Path, max_expanded_bytes: int
) -> list[ValidatedFile]:
    sources = {source.name: source for source in expected}
    if len(sources) != len(expected) or not sources:
        raise ValueError("Empty or duplicate requested inventory")
    result: list[ValidatedFile] = []
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        names = [entry.filename for entry in members]
        if len(names) != len(set(names)) or set(names) != set(sources):
            raise ValueError("ZIP inventory differs from selection; no partial import is allowed")
        if sum(entry.file_size for entry in members) > max_expanded_bytes:
            raise ValueError("Expanded ZIP exceeds configured size limit")
        for entry in members:
            if not FILENAME.fullmatch(entry.filename) or entry.flag_bits & 1:
                raise ValueError("Invalid or encrypted ZIP member")
            path = staging / entry.filename
            sha256 = hashlib.sha256()
            byte_count = 0
            with zipped.open(entry) as source, path.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    byte_count += len(chunk)
                    if byte_count > entry.file_size:
                        raise ValueError("ZIP member exceeds declared size")
                    sha256.update(chunk)
                    output.write(chunk)
                # Reading through EOF also verifies each member's ZIP CRC.
            row_count = 0
            columns: list[str] = []
            for row in csv_records(path):
                if not columns:
                    columns = list(row)
                row_count += 1
            if row_count == 0:
                raise ValueError("Empty source CSV")
            result.append(
                ValidatedFile(
                    sources[entry.filename],
                    path,
                    sha256.hexdigest(),
                    byte_count,
                    row_count,
                    columns,
                )
            )
    return result


def persist_artifact(file: ValidatedFile, root: Path) -> str:
    relative = Path("sha256") / file.sha256[:2] / f"{file.sha256}.csv"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        with target.open("rb") as existing:
            if hashlib.file_digest(existing, "sha256").hexdigest() != file.sha256:
                raise ValueError("Existing stored artifact is corrupt")
    else:
        temporary = target.with_suffix(".pending")
        try:
            with file.path.open("rb") as source, temporary.open("wb") as output:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return relative.as_posix()
