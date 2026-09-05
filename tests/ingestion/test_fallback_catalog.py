"""Sélection stricte du catalogue de secours versionné."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.catalog import (
    OFFICIAL_LANDING_PAGE,
    LandingPageFetcher,
    LandingPageInvalid,
)
from metiquo.ingestion.fallback_catalog import (
    CatalogDiscoveryService,
    FallbackCatalogInvalid,
    VersionedFallbackCatalog,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "oracles_elixir_sources.yml"
NOW = datetime(2026, 9, 5, 14, tzinfo=UTC)
CLOCK = FixedClock(UtcInstant(NOW))


def test_versioned_bootstrap_has_the_validated_2026_source() -> None:
    fallback = VersionedFallbackCatalog.load(CONFIG)

    assert fallback.version == 1
    assert len(fallback.payload_hash) == 64
    assert len(fallback.sources) == 1
    source = fallback.sources[0]
    assert source.year == 2026
    assert source.drive_file_id == "1hnpbrUpBMS1TZI7IovfpKeZfWJH1Aptm"
    assert source.mutable is True
    assert source.origin == "validated-bootstrap"


def test_fallback_is_selected_only_when_landing_page_is_unavailable() -> None:
    def unavailable(url: str, timeout: float, limit: int) -> bytes:
        del url, timeout, limit
        raise TimeoutError

    service = CatalogDiscoveryService(
        LandingPageFetcher(loader=unavailable, clock=CLOCK),
        VersionedFallbackCatalog.load(CONFIG),
        clock=CLOCK,
    )

    resolution = service.resolve()

    assert resolution.used_fallback is True
    assert resolution.outage_reason is not None
    assert resolution.discovery.origin == "validated-bootstrap"
    assert resolution.discovery.annual_links[2026][0].mutable is True


def test_accessible_folder_only_page_does_not_use_fallback() -> None:
    payload = (
        b'<a href="https://drive.google.com/drive/u/1/folders/current_folder">Google Drive</a>'
    )
    service = CatalogDiscoveryService(
        LandingPageFetcher(loader=lambda url, timeout, limit: payload, clock=CLOCK),
        VersionedFallbackCatalog.load(CONFIG),
        clock=CLOCK,
    )

    resolution = service.resolve()

    assert resolution.used_fallback is False
    assert resolution.outage_reason is None
    assert resolution.discovery.origin == "discovered"
    assert resolution.discovery.annual_links == {}
    assert resolution.discovery.links[0].drive_file_id == "current_folder"


def test_invalid_accessible_page_is_not_hidden_by_fallback() -> None:
    service = CatalogDiscoveryService(
        LandingPageFetcher(loader=lambda url, timeout, limit: b"x" * 5, max_bytes=4),
        VersionedFallbackCatalog.load(CONFIG),
    )

    with pytest.raises(LandingPageInvalid, match="trop volumineuse"):
        service.resolve()


def test_catalog_rejects_unknown_version_and_duplicate_years(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yml"
    invalid.write_text('{"version":2,"sources":[]}')
    with pytest.raises(FallbackCatalogInvalid, match="version"):
        VersionedFallbackCatalog.load(invalid)

    duplicate = tmp_path / "duplicate.yml"
    duplicate.write_text(
        """{
          "version": 1,
          "sources": [
            {"year": 2026, "drive_file_id": "a", "mutable": true,
             "origin": "validated-bootstrap"},
            {"year": 2026, "drive_file_id": "b", "mutable": true,
             "origin": "validated-bootstrap"}
          ]
        }"""
    )
    with pytest.raises(FallbackCatalogInvalid, match="plusieurs fois"):
        VersionedFallbackCatalog.load(duplicate)


def test_official_endpoint_is_preserved_in_fallback_audit() -> None:
    discovery = VersionedFallbackCatalog.load(CONFIG).as_discovery(CLOCK)

    assert discovery.landing_page == OFFICIAL_LANDING_PAGE
    assert discovery.fetched_at == NOW
