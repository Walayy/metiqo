"""Catalogue de secours versionné, utilisé seulement pendant une indisponibilité."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from metiquo.foundation.time import Clock, SystemClock
from metiquo.ingestion.catalog import (
    OFFICIAL_LANDING_PAGE,
    CatalogDiscovery,
    DriveLink,
    LandingPageFetcher,
    LandingPageUnavailable,
    discover_catalog,
)


class FallbackCatalogInvalid(ValueError):
    """Le catalogue versionné n'est pas conforme au contrat strict."""


@dataclass(frozen=True, slots=True)
class FallbackSource:
    year: int
    drive_file_id: str
    mutable: bool
    origin: str


@dataclass(frozen=True, slots=True)
class VersionedFallbackCatalog:
    version: int
    sources: tuple[FallbackSource, ...]
    payload_hash: str

    @classmethod
    def load(cls, path: Path) -> VersionedFallbackCatalog:
        try:
            payload = path.read_bytes()
            document = json.loads(payload)
        except (OSError, json.JSONDecodeError) as error:
            raise FallbackCatalogInvalid("catalogue de secours illisible") from error
        if not isinstance(document, dict):
            raise FallbackCatalogInvalid("racine du catalogue de secours invalide")
        raw_document = cast(dict[str, Any], document)
        if raw_document.get("version") != 1:
            raise FallbackCatalogInvalid("version de catalogue de secours non supportée")
        raw_sources = raw_document.get("sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raise FallbackCatalogInvalid("le catalogue de secours doit contenir des sources")

        sources = tuple(_parse_source(value) for value in raw_sources)
        years = [source.year for source in sources]
        if len(set(years)) != len(years):
            raise FallbackCatalogInvalid(
                "une année apparaît plusieurs fois dans le catalogue de secours"
            )
        return cls(
            version=1,
            sources=sources,
            payload_hash=hashlib.sha256(payload).hexdigest(),
        )

    def as_discovery(self, clock: Clock) -> CatalogDiscovery:
        links = tuple(
            DriveLink(
                drive_file_id=source.drive_file_id,
                url=f"https://drive.google.com/file/d/{source.drive_file_id}/view",
                source_name=f"{source.year} Oracle's Elixir validated bootstrap",
                kind="file",
                year=source.year,
                mutable=source.mutable,
            )
            for source in self.sources
        )
        return CatalogDiscovery(
            landing_page=OFFICIAL_LANDING_PAGE,
            payload_hash=self.payload_hash,
            fetched_at=clock.now().value,
            links=links,
            origin="validated-bootstrap",
        )


@dataclass(frozen=True, slots=True)
class CatalogResolution:
    discovery: CatalogDiscovery
    used_fallback: bool
    outage_reason: str | None


class CatalogDiscoveryService:
    """Résoudre la source officielle, sans masquer une divergence observable."""

    def __init__(
        self,
        fetcher: LandingPageFetcher,
        fallback: VersionedFallbackCatalog,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._fetcher = fetcher
        self._fallback = fallback
        self._clock = clock or SystemClock()

    def resolve(self) -> CatalogResolution:
        try:
            page = self._fetcher.fetch()
        except LandingPageUnavailable as error:
            return CatalogResolution(
                discovery=self._fallback.as_discovery(self._clock),
                used_fallback=True,
                outage_reason=str(error),
            )
        return CatalogResolution(
            discovery=discover_catalog(page),
            used_fallback=False,
            outage_reason=None,
        )


def _parse_source(value: object) -> FallbackSource:
    if not isinstance(value, dict):
        raise FallbackCatalogInvalid("entrée de secours invalide")
    source = cast(dict[str, Any], value)
    if set(source) != {"year", "drive_file_id", "mutable", "origin"}:
        raise FallbackCatalogInvalid("champs de l'entrée de secours invalides")
    year = source["year"]
    drive_file_id = source["drive_file_id"]
    mutable = source["mutable"]
    origin = source["origin"]
    if not isinstance(year, int) or isinstance(year, bool) or not 2014 <= year <= 9999:
        raise FallbackCatalogInvalid("année de secours invalide")
    if not isinstance(drive_file_id, str) or re.fullmatch(r"[A-Za-z0-9_-]+", drive_file_id) is None:
        raise FallbackCatalogInvalid("ID Drive de secours invalide")
    if not isinstance(mutable, bool):
        raise FallbackCatalogInvalid("indicateur mutable de secours invalide")
    if origin != "validated-bootstrap":
        raise FallbackCatalogInvalid("l'origine de secours doit être validated-bootstrap")
    return FallbackSource(year, drive_file_id, mutable, origin)
