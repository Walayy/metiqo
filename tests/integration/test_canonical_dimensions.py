"""Preuves PostgreSQL des dimensions canoniques traçables."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, Table, create_engine, insert, select, update

from metiquo.canonical.dimensions import CanonicalDimensionBuilder
from metiquo.db.core_models import Competition, GameTitle, Patch, Player, Team
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot, SourceCatalog

_NOW = datetime(2026, 9, 6, 4, 0, tzinfo=UTC)
_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(url: str) -> Config:
    config = Config(_ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


@pytest.mark.integration
def test_dimensions_are_idempotent_and_trace_only_validated_raw(
    postgresql_url: str,
) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = f"cnl_001_{uuid4().hex}"
    valid_rows, forbidden_identity = _seed_sources(engine, dataset)
    builder = CanonicalDimensionBuilder(engine=engine)

    first = builder.build(provider="oracles_elixir", dataset=dataset)
    first_ids = _dimension_ids(engine, valid_rows)
    second = builder.build(provider="oracles_elixir", dataset=dataset)

    assert first == second
    assert first.source_rows == 4
    assert first.game_titles == 1
    assert first.competitions == 1
    assert first.teams == 2
    assert first.players == 2
    assert first.patches == 1
    assert _dimension_ids(engine, valid_rows) == first_ids
    assert all(first_ids.values())

    with engine.connect() as connection:
        assert (
            connection.execute(
                select(Team.id).where(Team.source_team_id == forbidden_identity)
            ).scalar_one_or_none()
            is None
        )
        for model in (GameTitle, Competition, Team, Player, Patch):
            traces = connection.execute(
                select(
                    model.source_raw_row_id,
                    model.source_snapshot_id,
                    model.source_run_id,
                    model.source_natural_key,
                    model.source_row_revision,
                    model.transformation_version,
                    CanonicalRow.provider,
                    CanonicalRow.dataset,
                    Snapshot.status.label("snapshot_status"),
                    IngestionRun.status.label("run_status"),
                )
                .join(CanonicalRow, CanonicalRow.id == model.source_raw_row_id)
                .join(Snapshot, Snapshot.id == model.source_snapshot_id)
                .join(IngestionRun, IngestionRun.id == model.source_run_id)
                .where(CanonicalRow.dataset == dataset)
            ).all()
            assert traces
            assert all(
                trace.provider == "oracles_elixir"
                and trace.dataset == dataset
                and trace.snapshot_status == "validated"
                and trace.run_status == "succeeded"
                and trace.source_row_revision == 1
                and trace.transformation_version == "canonical-dimensions-v1"
                for trace in traces
            )
    engine.dispose()


def _seed_sources(engine: Engine, dataset: str) -> tuple[dict[str, str], str]:
    valid_catalog_id = uuid4()
    valid_snapshot_id = uuid4()
    valid_run_id = uuid4()
    invalid_catalog_id = uuid4()
    invalid_snapshot_id = uuid4()
    invalid_run_id = uuid4()
    forbidden_identity = f"forbidden-{uuid4().hex}"
    suffix = uuid4().hex[:10]
    rows = (
        {
            "gameid": f"CNL-{suffix}",
            "participantid": "100",
            "position": "team",
            "teamid": f"team-blue-{suffix}",
            "teamname": f"Équipe Bleue {suffix}",
            "league": f"Ligue CNL {suffix}",
            "patch": "14.1",
        },
        {
            "gameid": f"CNL-{suffix}",
            "participantid": "200",
            "position": "team",
            "teamid": f"team-red-{suffix}",
            "teamname": f"Équipe Rouge {suffix}",
            "league": f"Ligue CNL {suffix}",
            "patch": "14.1",
        },
        {
            "gameid": f"CNL-{suffix}",
            "participantid": "1",
            "position": "top",
            "teamid": f"team-blue-{suffix}",
            "teamname": f"Équipe Bleue {suffix}",
            "playerid": f"player-top-{suffix}",
            "playername": f"Joueur Haut {suffix}",
            "league": f"Ligue CNL {suffix}",
            "patch": "14.1",
        },
        {
            "gameid": f"CNL-{suffix}",
            "participantid": "6",
            "position": "top",
            "teamid": f"team-red-{suffix}",
            "teamname": f"Équipe Rouge {suffix}",
            "playerid": f"player-rival-{suffix}",
            "playername": f"Joueur Rival {suffix}",
            "league": f"Ligue CNL {suffix}",
            "patch": "14.1",
        },
    )
    valid_ids = {
        "competition": f"ligue cnl {suffix}",
        "team_blue": f"team-blue-{suffix}",
        "team_red": f"team-red-{suffix}",
        "player_top": f"player-top-{suffix}",
        "player_rival": f"player-rival-{suffix}",
        "patch": "14.1",
    }
    with engine.begin() as connection:
        _insert_catalog_snapshot_run(
            connection,
            dataset=dataset,
            year=2197,
            catalog_id=valid_catalog_id,
            snapshot_id=valid_snapshot_id,
            run_id=valid_run_id,
            snapshot_status="validated",
        )
        for ordinal, payload in enumerate(rows, start=1):
            _insert_raw_row(
                connection,
                dataset=dataset,
                snapshot_id=valid_snapshot_id,
                run_id=valid_run_id,
                ordinal=ordinal,
                payload=payload,
            )
        _insert_catalog_snapshot_run(
            connection,
            dataset=dataset,
            year=2196,
            catalog_id=invalid_catalog_id,
            snapshot_id=invalid_snapshot_id,
            run_id=invalid_run_id,
            snapshot_status="quarantined",
        )
        _insert_raw_row(
            connection,
            dataset=dataset,
            snapshot_id=invalid_snapshot_id,
            run_id=invalid_run_id,
            ordinal=99,
            payload={
                "gameid": f"INVALID-{suffix}",
                "participantid": "100",
                "position": "team",
                "teamid": forbidden_identity,
                "teamname": "Ne doit jamais être projetée",
                "league": "Ligue interdite",
                "patch": "99.9",
            },
        )
    return valid_ids, forbidden_identity


def _insert_catalog_snapshot_run(
    connection: Connection,
    *,
    dataset: str,
    year: int,
    catalog_id: UUID,
    snapshot_id: UUID,
    run_id: UUID,
    snapshot_status: str,
) -> None:
    catalog = cast(Table, SourceCatalog.__table__)
    snapshots = cast(Table, Snapshot.__table__)
    runs = cast(Table, IngestionRun.__table__)
    connection.execute(
        insert(catalog).values(
            id=catalog_id,
            created_at=_NOW,
            updated_at=_NOW,
            provider="oracles_elixir",
            dataset=dataset,
            season_year=year,
            landing_page="https://oracleselixir.com/tools/downloads",
            drive_file_id=f"drive-{year}-{dataset}",
            source_name=f"{year}_LoL_esports_match_data_from_OraclesElixir.csv.gz",
            source_modified_at=_NOW,
            source_size=100,
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
            year=year,
            source_file_id=f"drive-{year}-{dataset}",
            status=snapshot_status,
            sha256=hashlib.sha256(f"snapshot-{snapshot_id}".encode()).hexdigest(),
            byte_size=100,
            content_type="text/csv",
            object_key=f"year={year}/sha256={snapshot_id.hex}/source.csv",
            received_at=_NOW,
            validated_at=_NOW if snapshot_status == "validated" else None,
            failure_reason=None if snapshot_status == "validated" else "fixture invalide",
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
            correlation_id=f"cnl-001-{run_id}",
            started_at=_NOW,
            finished_at=_NOW,
            counters={},
            created_at=_NOW,
        )
    )
    connection.execute(
        update(catalog).where(catalog.c.id == catalog_id).values(current_snapshot_id=snapshot_id)
    )


def _insert_raw_row(
    connection: Connection,
    *,
    dataset: str,
    snapshot_id: UUID,
    run_id: UUID,
    ordinal: int,
    payload: dict[str, str],
) -> None:
    canonical_rows = cast(Table, CanonicalRow.__table__)
    natural_key = json.dumps([payload["gameid"], payload["participantid"]], separators=(",", ":"))
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    connection.execute(
        insert(canonical_rows).values(
            id=uuid4(),
            provider="oracles_elixir",
            dataset=dataset,
            natural_key=natural_key,
            row_hash=hashlib.sha256(payload_json.encode()).hexdigest(),
            payload=payload,
            event_date=date(2197, 1, min(ordinal, 28)),
            source_snapshot_id=snapshot_id,
            source_run_id=run_id,
            revision=1,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )


def _dimension_ids(engine: Engine, identities: dict[str, str]) -> dict[str, tuple[UUID, ...]]:
    with engine.connect() as connection:
        return {
            "game_title": tuple(
                connection.execute(
                    select(GameTitle.id).where(GameTitle.slug == "league-of-legends")
                ).scalars()
            ),
            "competition": tuple(
                connection.execute(
                    select(Competition.id).where(
                        Competition.source_competition_id == identities["competition"]
                    )
                ).scalars()
            ),
            "teams": tuple(
                connection.execute(
                    select(Team.id)
                    .where(
                        Team.source_team_id.in_((identities["team_blue"], identities["team_red"]))
                    )
                    .order_by(Team.id)
                ).scalars()
            ),
            "players": tuple(
                connection.execute(
                    select(Player.id)
                    .where(
                        Player.source_player_id.in_(
                            (identities["player_top"], identities["player_rival"])
                        )
                    )
                    .order_by(Player.id)
                ).scalars()
            ),
            "patch": tuple(
                connection.execute(
                    select(Patch.id).where(Patch.version == identities["patch"])
                ).scalars()
            ),
        }
