"""Preuves PostgreSQL des aliases canoniques datés et non ambigus."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import Engine, Table, create_engine, insert, inspect, select, text
from sqlalchemy.exc import DBAPIError

from metiquo.db.core_models import GameTitle, Team
from metiquo.db.mapping_models import EntityAlias
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot, SourceCatalog
from tests.integration.test_migrations import alembic_config

_NOW = datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
_REBRAND_AT = datetime(2026, 7, 1, tzinfo=UTC)


@pytest.mark.integration
def test_aliases_date_rebrands_and_keep_main_and_academy_distinct(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    main_id, academy_id = _seed_teams(engine)
    aliases = cast(Table, EntityAlias.__table__)

    old_sponsor_id = uuid4()
    new_sponsor_id = uuid4()
    academy_alias_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            insert(aliases),
            (
                _alias(
                    old_sponsor_id,
                    canonical_id=main_id,
                    raw_alias="Aurora Esports",
                    normalized_alias="aurora esports",
                    valid_from=datetime(2024, 1, 1, tzinfo=UTC),
                    valid_to=_REBRAND_AT,
                ),
                _alias(
                    new_sponsor_id,
                    canonical_id=main_id,
                    raw_alias="Nova Aurora",
                    normalized_alias="nova aurora",
                    valid_from=_REBRAND_AT,
                    valid_to=None,
                ),
                _alias(
                    academy_alias_id,
                    canonical_id=academy_id,
                    raw_alias="Aurora Esports Academy",
                    normalized_alias="aurora esports academy",
                    valid_from=datetime(2024, 1, 1, tzinfo=UTC),
                    valid_to=None,
                ),
            ),
        )

    with engine.connect() as connection:
        stored = connection.execute(
            select(
                aliases.c.canonical_id,
                aliases.c.raw_alias,
                aliases.c.valid_from,
                aliases.c.valid_to,
            ).order_by(aliases.c.raw_alias)
        ).all()
        exclusion_exists = connection.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM pg_constraint
                  WHERE conname = 'ex_core_entity_aliases_temporal_identity'
                    AND contype = 'x'
                )
                """
            )
        ).scalar_one()
        canonical_index = next(
            item
            for item in inspect(connection).get_indexes("entity_aliases", schema="core")
            if item["name"] == "ix_core_entity_aliases_canonical_validity"
        )
    assert len(stored) == 3
    assert {row.canonical_id for row in stored} == {main_id, academy_id}
    assert next(row for row in stored if row.raw_alias == "Aurora Esports").valid_to == (
        _REBRAND_AT
    )
    assert next(row for row in stored if row.raw_alias == "Nova Aurora").valid_from == (_REBRAND_AT)
    assert exclusion_exists is True
    assert canonical_index["column_names"] == [
        "entity_type",
        "canonical_id",
        "valid_from",
        "valid_to",
    ]

    with (
        pytest.raises(
            DBAPIError,
            match="ex_core_entity_aliases_temporal_identity",
        ),
        engine.begin() as connection,
    ):
        connection.execute(
            insert(aliases).values(
                **_alias(
                    uuid4(),
                    canonical_id=academy_id,
                    raw_alias="AURORA ESPORTS",
                    normalized_alias="aurora esports",
                    valid_from=datetime(2025, 1, 1, tzinfo=UTC),
                    valid_to=None,
                )
            )
        )

    with pytest.raises(DBAPIError, match="canonical team id"), engine.begin() as connection:
        connection.execute(
            insert(aliases).values(
                **_alias(
                    uuid4(),
                    canonical_id=uuid4(),
                    raw_alias="Unknown",
                    normalized_alias="unknown",
                    valid_from=_NOW,
                    valid_to=None,
                )
            )
        )

    with pytest.raises(DBAPIError, match="manual_approval"), engine.begin() as connection:
        invalid = _alias(
            uuid4(),
            canonical_id=main_id,
            raw_alias="Manual without audit",
            normalized_alias="manual without audit",
            valid_from=_NOW,
            valid_to=None,
        )
        invalid["approved_by"] = None
        invalid["approved_at"] = None
        connection.execute(insert(aliases).values(**invalid))
    engine.dispose()


def _seed_teams(engine: Engine) -> tuple[UUID, UUID]:
    catalogs = cast(Table, SourceCatalog.__table__)
    snapshots = cast(Table, Snapshot.__table__)
    runs = cast(Table, IngestionRun.__table__)
    rows = cast(Table, CanonicalRow.__table__)
    game_titles = cast(Table, GameTitle.__table__)
    teams = cast(Table, Team.__table__)
    catalog_id, snapshot_id, run_id, row_id, game_title_id = (uuid4() for _ in range(5))
    main_id, academy_id = uuid4(), uuid4()
    source_hash = hashlib.sha256(str(row_id).encode()).hexdigest()

    with engine.begin() as connection:
        connection.execute(
            insert(catalogs).values(
                id=catalog_id,
                provider="oracles_elixir",
                dataset=f"map-001-{catalog_id}",
                season_year=2026,
                landing_page="https://oracleselixir.com/tools/downloads",
                drive_file_id=f"drive-{catalog_id}",
                source_name="map-001.csv.gz",
                source_modified_at=_NOW,
                source_size=100,
                origin="manual",
                status="active",
                discovered_at=_NOW,
                last_confirmed_at=_NOW,
                mutable=False,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        connection.execute(
            insert(snapshots).values(
                id=snapshot_id,
                source_catalog_id=catalog_id,
                year=2026,
                source_file_id=f"drive-{catalog_id}",
                status="validated",
                sha256=hashlib.sha256(str(snapshot_id).encode()).hexdigest(),
                byte_size=100,
                content_type="text/csv",
                object_key=f"map-001/{snapshot_id}/source.csv",
                received_at=_NOW,
                validated_at=_NOW,
                manifest={},
                created_at=_NOW,
            )
        )
        connection.execute(
            insert(runs).values(
                id=run_id,
                source_catalog_id=catalog_id,
                snapshot_id=snapshot_id,
                run_kind="load",
                status="succeeded",
                attempt=1,
                transport="fixture",
                correlation_id=f"map-001-{run_id}",
                started_at=_NOW,
                finished_at=_NOW,
                counters={},
                created_at=_NOW,
            )
        )
        connection.execute(
            insert(rows).values(
                id=row_id,
                provider="oracles_elixir",
                dataset=f"map-001-{catalog_id}",
                natural_key=f"map-001:{row_id}",
                row_hash=source_hash,
                payload={"teamname": "Aurora"},
                event_date=date(2026, 1, 1),
                source_snapshot_id=snapshot_id,
                source_run_id=run_id,
                revision=1,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        provenance = {
            "processed_at": _NOW,
            "source_natural_key": f"map-001:{row_id}",
            "source_raw_row_id": row_id,
            "source_row_hash": source_hash,
            "source_row_revision": 1,
            "source_run_id": run_id,
            "source_snapshot_id": snapshot_id,
            "transformation_version": "map-001-fixture-v1",
        }
        connection.execute(
            insert(game_titles).values(
                id=game_title_id,
                slug="league-of-legends",
                display_name="League of Legends",
                **provenance,
            )
        )
        connection.execute(
            insert(teams),
            (
                {
                    "id": main_id,
                    "game_title_id": game_title_id,
                    "source_team_id": f"aurora-main-{main_id}",
                    "normalized_name": "aurora esports",
                    "display_name": "Aurora Esports",
                    "source_identity_kind": "teamid",
                    **provenance,
                },
                {
                    "id": academy_id,
                    "game_title_id": game_title_id,
                    "source_team_id": f"aurora-academy-{academy_id}",
                    "normalized_name": "aurora esports academy",
                    "display_name": "Aurora Esports Academy",
                    "source_identity_kind": "teamid",
                    **provenance,
                },
            ),
        )
    return main_id, academy_id


def _alias(
    alias_id: UUID,
    *,
    canonical_id: UUID,
    raw_alias: str,
    normalized_alias: str,
    valid_from: datetime,
    valid_to: datetime | None,
) -> dict[str, object]:
    return {
        "approved_at": _NOW,
        "approved_by": "map-001-test",
        "canonical_id": canonical_id,
        "confidence": Decimal("1.0000"),
        "created_at": _NOW,
        "entity_type": "team",
        "id": alias_id,
        "normalized_alias": normalized_alias,
        "notes": "Fixture datée MAP-001",
        "provider": "mock-provider",
        "raw_alias": raw_alias,
        "source": "manual",
        "valid_from": valid_from,
        "valid_to": valid_to,
    }
