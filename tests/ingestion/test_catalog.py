"""Découverte et réconciliation du catalogue Oracle's Elixir."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.catalog import (
    OFFICIAL_LANDING_PAGE,
    CatalogRecord,
    LandingPage,
    LandingPageFetcher,
    LandingPageInvalid,
    LandingPageUnavailable,
    discover_catalog,
    reconcile_catalog,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "oracles_elixir"
NOW = datetime(2026, 9, 5, 12, tzinfo=UTC)


def _page(name: str) -> LandingPage:
    return LandingPage(OFFICIAL_LANDING_PAGE, (FIXTURES / name).read_bytes(), NOW)


def _active(year: int, file_id: str) -> CatalogRecord:
    return CatalogRecord(
        id=uuid4(),
        season_year=year,
        drive_file_id=file_id,
        source_name=f"{year} match data",
        landing_page=OFFICIAL_LANDING_PAGE,
    )


def test_fetcher_uses_only_official_landing_page() -> None:
    calls: list[tuple[str, float, int]] = []

    def loader(url: str, timeout: float, limit: int) -> bytes:
        calls.append((url, timeout, limit))
        return b"<html></html>"

    page = LandingPageFetcher(
        loader=loader,
        clock=FixedClock(UtcInstant(NOW)),
        timeout_seconds=3,
        max_bytes=1024,
    ).fetch()

    assert calls == [(OFFICIAL_LANDING_PAGE, 3, 1024)]
    assert page.fetched_at == NOW


def test_fetcher_classifies_unavailability_and_oversized_page() -> None:
    def unavailable(url: str, timeout: float, limit: int) -> bytes:
        del url, timeout, limit
        raise TimeoutError

    with pytest.raises(LandingPageUnavailable):
        LandingPageFetcher(loader=unavailable).fetch()

    with pytest.raises(LandingPageInvalid, match="trop volumineuse"):
        LandingPageFetcher(loader=lambda url, timeout, limit: b"x" * 5, max_bytes=4).fetch()


def test_discovery_extracts_drive_ids_and_explicit_years_only() -> None:
    discovery = discover_catalog(_page("downloads_standard.html"))

    assert set(discovery.annual_links) == {2024, 2025}
    assert [link.drive_file_id for link in discovery.links] == ["drive_2024_A", "drive_2025_B"]
    assert all(link.kind == "file" for link in discovery.links)
    assert len(discovery.payload_hash) == 64


def test_changed_id_is_reported_without_replacing_active() -> None:
    discovery = discover_catalog(_page("downloads_standard.html"))
    active = {2024: _active(2024, "previous_2024")}

    reconciliation = reconcile_catalog(discovery, active)

    changed = next(decision for decision in reconciliation.decisions if decision.year == 2024)
    assert changed.status == "changed"
    assert changed.previous == active[2024]
    assert changed.candidates[0].drive_file_id == "drive_2024_A"


def test_duplicate_ambiguity_and_disappearance_are_detected() -> None:
    discovery = discover_catalog(_page("downloads_ambiguous.html"))
    active = {2025: _active(2025, "active_2025"), 2026: _active(2026, "active_2026")}

    reconciliation = reconcile_catalog(discovery, active)

    by_year = {decision.year: decision for decision in reconciliation.decisions}
    assert by_year[2026].status == "ambiguous"
    assert by_year[2026].previous == active[2026]
    assert {link.drive_file_id for link in by_year[2026].candidates} == {
        "old_2026",
        "new_2026",
    }
    assert by_year[2025].status == "missing"
    assert {alert.kind for alert in reconciliation.alerts} == {"duplicate", "unresolved"}


def test_current_folder_only_page_never_confirms_an_annual_source() -> None:
    discovery = discover_catalog(_page("downloads_current_folder_only.html"))
    active = {2026: _active(2026, "validated_bootstrap")}

    reconciliation = reconcile_catalog(discovery, active)

    assert discovery.annual_links == {}
    assert discovery.links[0].kind == "folder"
    assert reconciliation.decisions[0].status == "missing"
    assert reconciliation.decisions[0].previous == active[2026]
    assert reconciliation.alerts[0].kind == "unresolved"
