"""Persistance PostgreSQL du catalogue découvert."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, select

from metiquo.db.raw_models import SourceCatalog
from metiquo.ingestion.catalog import (
    DATASET,
    OFFICIAL_LANDING_PAGE,
    PROVIDER,
    CatalogDiscovery,
    LandingPage,
    SourceCatalogRepository,
    discover_catalog,
    reconcile_catalog,
)

ROOT = Path(__file__).resolve().parents[2]


def alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


def _discovery(file_links: str, instant: datetime) -> CatalogDiscovery:
    page = LandingPage(
        OFFICIAL_LANDING_PAGE,
        f"<html><body>{file_links}</body></html>".encode(),
        instant,
    )
    return discover_catalog(page)


@pytest.mark.integration
def test_catalog_persistence_confirms_and_audits_divergence(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    first_seen = datetime(2026, 9, 5, 10, tzinfo=UTC)
    confirmed_at = datetime(2026, 9, 5, 11, tzinfo=UTC)
    changed_at = datetime(2026, 9, 5, 12, tzinfo=UTC)
    ambiguous_at = datetime(2026, 9, 5, 13, tzinfo=UTC)

    with engine.begin() as connection:
        connection.execute(
            delete(SourceCatalog).where(
                SourceCatalog.provider == PROVIDER,
                SourceCatalog.dataset == DATASET,
            )
        )
        repository = SourceCatalogRepository(connection)
        initial = _discovery(
            '<a href="https://drive.google.com/file/d/file_A/view">2026 match data</a>',
            first_seen,
        )
        repository.apply(reconcile_catalog(initial, repository.active_records()))

    with engine.begin() as connection:
        repository = SourceCatalogRepository(connection)
        active_before = repository.active_records()[2026]
        confirmed = _discovery(
            '<a href="https://drive.google.com/file/d/file_A/view">2026 match data</a>',
            confirmed_at,
        )
        repository.apply(reconcile_catalog(confirmed, repository.active_records()))

    with engine.begin() as connection:
        repository = SourceCatalogRepository(connection)
        changed = _discovery(
            '<a href="https://drive.google.com/file/d/file_B/view">2026 corrected</a>',
            changed_at,
        )
        repository.apply(reconcile_catalog(changed, repository.active_records()))

    with engine.begin() as connection:
        repository = SourceCatalogRepository(connection)
        ambiguous = _discovery(
            '<a href="https://drive.google.com/file/d/file_A/view">2026 original</a>'
            '<a href="https://drive.google.com/file/d/file_C/view">2026 alternate</a>',
            ambiguous_at,
        )
        repository.apply(reconcile_catalog(ambiguous, repository.active_records()))

    with engine.connect() as connection:
        table = SourceCatalog.__table__
        rows = connection.execute(
            select(table).where(
                table.c.provider == PROVIDER,
                table.c.dataset == DATASET,
                table.c.season_year == 2026,
            )
        ).mappings()
        by_status = {str(row["status"]): row for row in rows}
        assert set(by_status) == {"active", "changed", "ambiguous"}
        assert by_status["active"]["id"] == active_before.id
        assert by_status["active"]["drive_file_id"] == "file_A"
        assert by_status["active"]["discovered_at"] == first_seen
        assert by_status["active"]["last_confirmed_at"] == confirmed_at
        assert by_status["active"]["mutable"] is True
        assert by_status["changed"]["drive_file_id"] == "file_B"
        assert by_status["changed"]["last_confirmed_at"] == changed_at
        changed_hash = by_status["changed"]["discovery_payload_hash"]
        assert isinstance(changed_hash, str)
        assert len(changed_hash) == 64
        assert by_status["ambiguous"]["drive_file_id"] == "file_C"

    engine.dispose()
