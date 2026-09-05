"""Preuves de roundtrip et d'historisation append-only du modèle canonique."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, Table, create_engine, func, insert, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from metiquo.canonical.games import CanonicalGameBuilder
from metiquo.db.core_models import CanonicalEntityRevision, CanonicalEntitySource, Game
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot, SourceCatalog

_ROOT = Path(__file__).resolve().parents[2]
_NOW = datetime(2026, 9, 6, 11, 0, tzinfo=UTC)


def _alembic_config(url: str) -> Config:
    config = Config(_ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


@pytest.mark.integration
def test_canonical_revision_roundtrip_keeps_old_raw_trace(postgresql_url: str) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = f"cnl_005_{uuid4().hex}"
    source_game_id = f"CNL5-{uuid4().hex[:10]}"
    source_row_id = _seed_history_game(engine, dataset, source_game_id)
    builder = CanonicalGameBuilder(engine=engine)

    builder.build(provider="oracles_elixir", dataset=dataset)
    game_id = _game_id(engine, source_game_id)
    initial = _game_revisions(engine, game_id)
    assert [item.revision for item in initial] == [1]
    assert initial[0].quality_status == "complete"
    assert initial[0].correction is False
    assert _source_count(engine, initial[0].id) == 2

    # Une reconstruction identique ne crée pas de fausse révision.
    builder.build(provider="oracles_elixir", dataset=dataset)
    assert [item.revision for item in _game_revisions(engine, game_id)] == [1]

    new_snapshot_id, new_run_id = _correct_player_row(engine, dataset, source_row_id)
    builder.build(provider="oracles_elixir", dataset=dataset)
    revisions = _game_revisions(engine, game_id)

    assert [item.revision for item in revisions] == [1, 2]
    assert revisions[1].previous_revision_id == revisions[0].id
    assert revisions[1].correction is True
    assert revisions[1].source_snapshot_id in {
        revisions[0].source_snapshot_id,
        new_snapshot_id,
    }
    assert revisions[1].source_run_id is not None
    assert _source_payload(engine, revisions[0].id, source_row_id)["kills"] == "10"
    corrected_source = _source_payload(engine, revisions[1].id, source_row_id)
    assert corrected_source["kills"] == "99"

    with engine.connect() as connection:
        roundtrip = connection.execute(
            select(
                CanonicalEntitySource.source_snapshot_id,
                CanonicalEntitySource.source_run_id,
                Snapshot.status,
                IngestionRun.status,
            )
            .join(Snapshot, Snapshot.id == CanonicalEntitySource.source_snapshot_id)
            .join(IngestionRun, IngestionRun.id == CanonicalEntitySource.source_run_id)
            .where(
                CanonicalEntitySource.entity_revision_id == revisions[1].id,
                CanonicalEntitySource.source_raw_row_id == source_row_id,
            )
        ).one()
        assert roundtrip[0] == new_snapshot_id
        assert roundtrip[1] == new_run_id
        assert roundtrip[2:] == ("validated", "succeeded")

    revision_table = cast(Table, CanonicalEntityRevision.__table__)
    with (
        pytest.raises(DBAPIError, match="canonical history is append-only"),
        engine.begin() as connection,
    ):
        connection.execute(
            update(revision_table)
            .where(revision_table.c.id == revisions[0].id)
            .values(quality_status="tampered")
        )
    engine.dispose()


def _game_id(engine: Engine, source_game_id: str) -> UUID:
    with engine.connect() as connection:
        return connection.execute(
            select(Game.id).where(Game.source_game_id == source_game_id)
        ).scalar_one()


def _seed_history_game(engine: Engine, dataset: str, source_game_id: str) -> UUID:
    catalog_id = uuid4()
    snapshot_id = uuid4()
    run_id = uuid4()
    blue_row_id = uuid4()
    suffix = uuid4().hex[:8]
    catalog = cast(Table, SourceCatalog.__table__)
    snapshots = cast(Table, Snapshot.__table__)
    runs = cast(Table, IngestionRun.__table__)
    raw = cast(Table, CanonicalRow.__table__)
    with engine.begin() as connection:
        connection.execute(
            insert(catalog).values(
                id=catalog_id,
                created_at=_NOW,
                updated_at=_NOW,
                provider="oracles_elixir",
                dataset=dataset,
                season_year=2194,
                landing_page="https://oracleselixir.com/tools/downloads",
                drive_file_id=f"drive-{dataset}",
                source_name="2194_LoL_esports_match_data_from_OraclesElixir.csv.gz",
                source_modified_at=_NOW,
                source_size=1000,
                origin="discovered",
                status="active",
                discovered_at=_NOW,
                last_confirmed_at=_NOW,
                mutable=False,
            )
        )
        connection.execute(
            insert(snapshots).values(
                id=snapshot_id,
                source_catalog_id=catalog_id,
                year=2194,
                source_file_id=f"drive-{dataset}",
                status="validated",
                sha256=hashlib.sha256(f"snapshot-{snapshot_id}".encode()).hexdigest(),
                byte_size=1000,
                content_type="text/csv",
                object_key=f"history/{snapshot_id}/source.csv",
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
                correlation_id=f"cnl-005-{run_id}",
                started_at=_NOW,
                finished_at=_NOW,
                counters={},
                created_at=_NOW,
            )
        )
        for side, participant, row_id in (
            ("Blue", "100", blue_row_id),
            ("Red", "200", uuid4()),
        ):
            blue = side == "Blue"
            payload = {
                "gameid": source_game_id,
                "date": "2026-08-01T18:00:00Z",
                "participantid": participant,
                "side": side,
                "position": "team",
                "teamid": f"team-{'blue' if blue else 'red'}-{suffix}",
                "teamname": f"Team {'Blue' if blue else 'Red'} {suffix}",
                "league": f"League CNL5 {suffix}",
                "patch": "14.5",
                "result": "1" if blue else "0",
                "datacompleteness": "complete",
                "gamelength": "1800",
                "forfeit": "false",
                "kills": "10" if blue else "5",
            }
            serialized = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            connection.execute(
                insert(raw).values(
                    id=row_id,
                    provider="oracles_elixir",
                    dataset=dataset,
                    natural_key=json.dumps([source_game_id, participant], separators=(",", ":")),
                    row_hash=hashlib.sha256(serialized.encode()).hexdigest(),
                    payload=payload,
                    event_date=date(2026, 8, 1),
                    source_snapshot_id=snapshot_id,
                    source_run_id=run_id,
                    revision=1,
                    created_at=_NOW,
                    updated_at=_NOW,
                )
            )
        connection.execute(
            update(catalog)
            .where(catalog.c.id == catalog_id)
            .values(current_snapshot_id=snapshot_id)
        )
    return blue_row_id


def _correct_player_row(engine: Engine, dataset: str, source_row_id: UUID) -> tuple[UUID, UUID]:
    raw = cast(Table, CanonicalRow.__table__)
    snapshots = cast(Table, Snapshot.__table__)
    runs = cast(Table, IngestionRun.__table__)
    catalogs = cast(Table, SourceCatalog.__table__)
    snapshot_id = uuid4()
    run_id = uuid4()
    with engine.begin() as connection:
        row = connection.execute(select(raw).where(raw.c.id == source_row_id)).mappings().one()
        old_snapshot = (
            connection.execute(select(snapshots).where(snapshots.c.id == row["source_snapshot_id"]))
            .mappings()
            .one()
        )
        payload = dict(row["payload"])
        payload["kills"] = "99"
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        connection.execute(
            insert(snapshots).values(
                id=snapshot_id,
                source_catalog_id=old_snapshot["source_catalog_id"],
                year=old_snapshot["year"],
                source_file_id=f"correction-{snapshot_id}",
                status="validated",
                sha256=hashlib.sha256(f"snapshot-{snapshot_id}".encode()).hexdigest(),
                byte_size=1001,
                content_type="text/csv",
                object_key=f"correction/{snapshot_id}/source.csv",
                received_at=_NOW + timedelta(minutes=1),
                validated_at=_NOW + timedelta(minutes=1),
                manifest={"correction": True},
                created_at=_NOW + timedelta(minutes=1),
            )
        )
        connection.execute(
            insert(runs).values(
                id=run_id,
                source_catalog_id=old_snapshot["source_catalog_id"],
                snapshot_id=snapshot_id,
                run_kind="load",
                status="succeeded",
                attempt=2,
                transport="fixture",
                correlation_id=f"cnl-005-{run_id}",
                started_at=_NOW + timedelta(minutes=1),
                finished_at=_NOW + timedelta(minutes=1),
                counters={"updated": 1},
                created_at=_NOW + timedelta(minutes=1),
            )
        )
        connection.execute(
            update(raw)
            .where(raw.c.id == source_row_id)
            .values(
                payload=payload,
                row_hash=hashlib.sha256(serialized.encode()).hexdigest(),
                revision=2,
                source_snapshot_id=snapshot_id,
                source_run_id=run_id,
                updated_at=_NOW + timedelta(minutes=1),
            )
        )
        connection.execute(
            update(catalogs)
            .where(catalogs.c.id == old_snapshot["source_catalog_id"])
            .values(current_snapshot_id=snapshot_id)
        )
    return snapshot_id, run_id


def _game_revisions(engine: Engine, game_id: UUID) -> list[CanonicalEntityRevision]:
    with Session(engine) as session:
        return list(
            session.execute(
                select(CanonicalEntityRevision)
                .where(
                    CanonicalEntityRevision.entity_type == "game",
                    CanonicalEntityRevision.entity_id == game_id,
                )
                .order_by(CanonicalEntityRevision.revision)
            ).scalars()
        )


def _source_count(engine: Engine, revision_id: UUID) -> int:
    with engine.connect() as connection:
        return int(
            connection.scalar(
                select(func.count())
                .select_from(CanonicalEntitySource)
                .where(CanonicalEntitySource.entity_revision_id == revision_id)
            )
            or 0
        )


def _source_payload(engine: Engine, revision_id: UUID, source_row_id: UUID) -> dict[str, str]:
    with engine.connect() as connection:
        payload = connection.scalar(
            select(CanonicalEntitySource.source_payload).where(
                CanonicalEntitySource.entity_revision_id == revision_id,
                CanonicalEntitySource.source_raw_row_id == source_row_id,
            )
        )
    return cast(dict[str, str], payload)
