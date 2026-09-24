"""Verified LoLTV listing captures used to discover missing detail URLs."""

import gzip
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from metiquo_worker.sources.loltv import ROOT_URL, LoltvEvent, listing

PARIS = ZoneInfo("Europe/Paris")
ARCHIVE_DIR = Path(__file__).with_name("archive")
MANIFEST_PATH = ARCHIVE_DIR / "manifest.json"


@dataclass(frozen=True)
class ArchivedListing:
    filename: str
    first_day: date
    last_day: date
    retrieved_at: datetime
    document_sha256: str
    artifact_sha256: str

    def evidence(self, url: str) -> dict[str, str]:
        return {
            "url": url,
            "retrievedAt": self.retrieved_at.isoformat(),
            "documentSha256": self.document_sha256,
            "artifactSha256": self.artifact_sha256,
        }


def _read_manifest() -> list[ArchivedListing]:
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("archives"), list):
        raise ValueError("LoLTV archive manifest must contain an archives list")

    result: list[ArchivedListing] = []
    for entry in cast(list[object], raw["archives"]):
        if not isinstance(entry, dict):
            raise ValueError("LoLTV archive manifest entry must be an object")
        value = cast(dict[str, object], entry)
        filename = value.get("filename")
        first_day = value.get("from")
        last_day = value.get("to")
        retrieved_at = value.get("retrievedAt")
        document_sha256 = value.get("documentSha256")
        artifact_sha256 = value.get("artifactSha256")
        if (
            not isinstance(filename, str)
            or not isinstance(first_day, str)
            or not isinstance(last_day, str)
            or not isinstance(retrieved_at, str)
            or not isinstance(document_sha256, str)
            or not isinstance(artifact_sha256, str)
        ):
            raise ValueError("LoLTV archive manifest entry has invalid fields")
        if Path(filename).name != filename or not filename.endswith(".gz"):
            raise ValueError("LoLTV archive filename must be a local gzip artifact")
        captured_at = datetime.fromisoformat(retrieved_at)
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("LoLTV archive retrieval time must include a timezone")
        hashes = (document_sha256, artifact_sha256)
        invalid_hash = any(
            len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
            for value in hashes
        )
        if invalid_hash:
            raise ValueError("LoLTV archive checksums must be lowercase SHA-256 values")
        first = date.fromisoformat(first_day)
        last = date.fromisoformat(last_day)
        if first > last:
            raise ValueError("LoLTV archive date range is reversed")
        result.append(
            ArchivedListing(
                filename=filename,
                first_day=first,
                last_day=last,
                retrieved_at=captured_at,
                document_sha256=hashes[0],
                artifact_sha256=hashes[1],
            )
        )
    return result


def _read_archive(archive: ArchivedListing) -> tuple[list[LoltvEvent], dict[str, str]]:
    compressed = (ARCHIVE_DIR / archive.filename).read_bytes()
    if hashlib.sha256(compressed).hexdigest() != archive.artifact_sha256:
        raise ValueError("LoLTV archived listing artifact checksum mismatch")
    document = gzip.decompress(compressed)
    if hashlib.sha256(document).hexdigest() != archive.document_sha256:
        raise ValueError("LoLTV archived listing document checksum mismatch")
    url = ROOT_URL + "/matches/results"
    events, _, _ = listing(document.decode("utf-8"), url)
    evidence = archive.evidence(url)
    selected = [
        replace(event, payload={**event.payload, "archivedDiscovery": evidence})
        for event in events
        if archive.first_day <= event.starts_at.astimezone(PARIS).date() <= archive.last_day
        and event.status == "finished"
    ]
    return selected, evidence


def discover_archived_events(
    first: date, last: date
) -> tuple[list[LoltvEvent], list[dict[str, str]]]:
    """Discover in-window candidates from any overlapping verified public capture."""
    candidates: dict[str, tuple[datetime, LoltvEvent]] = {}
    evidence_by_checksum: dict[str, dict[str, str]] = {}
    archives = sorted(_read_manifest(), key=lambda item: item.retrieved_at, reverse=True)
    for archive in archives:
        if first > archive.last_day or last < archive.first_day:
            continue
        events, evidence = _read_archive(archive)
        evidence_by_checksum[archive.artifact_sha256] = evidence
        for event in events:
            event_day = event.starts_at.astimezone(PARIS).date()
            if first <= event_day <= last:
                current = candidates.get(event.source_id)
                if current is None or archive.retrieved_at > current[0]:
                    candidates[event.source_id] = (archive.retrieved_at, event)
    selected = [item[1] for item in candidates.values()]
    selected.sort(key=lambda event: (event.starts_at, event.source_id))
    return selected, list(evidence_by_checksum.values())
