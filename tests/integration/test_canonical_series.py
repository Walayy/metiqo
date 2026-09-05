"""Preuves de reconstruction des séries et de refus des ambiguïtés."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TypedDict, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, Table, create_engine, insert, select, update
from sqlalchemy.orm import Session

from metiquo.canonical.series import CanonicalSeriesBuilder
from metiquo.db.core_models import Game, Series, Team
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot, SourceCatalog

_ROOT = Path(__file__).resolve().parents[2]
_NOW = datetime(2026, 9, 6, 8, 0, tzinfo=UTC)


class _SeriesIdentities(TypedDict):
    all_games: tuple[str, ...]
    ambiguous_games: tuple[str, str]
    blue_team: str
    fallback_marker: str
    source_series_id: str


def _alembic_config(url: str) -> Config:
    config = Config(_ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


@pytest.mark.integration
def test_series_prefer_oe_support_bo2_draw_and_leave_ambiguity_unresolved(
    postgresql_url: str,
) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = f"cnl_003_{uuid4().hex}"
    identities = _seed_series(engine, dataset)
    builder = CanonicalSeriesBuilder(engine=engine)

    first = builder.build(provider="oracles_elixir", dataset=dataset)
    before = _series_ids(engine, identities)
    second = builder.build(provider="oracles_elixir", dataset=dataset)

    assert first == second
    assert first.source_games == 6
    assert first.series == 2
    assert first.resolved_games == 4
    assert first.ambiguous_games == 2
    assert first.missing_context_games == 0
    assert _series_ids(engine, identities) == before

    with Session(engine) as session:
        oe_series = session.execute(
            select(Series).where(Series.source_series_id == identities["source_series_id"])
        ).scalar_one()
        assert oe_series.identity_strategy == "oe"
        assert oe_series.best_of == 3
        assert oe_series.allows_draw is False
        assert oe_series.complete is True
        assert oe_series.result_status in {"team_one", "team_two"}
        winner = session.execute(
            select(Team).where(Team.id == oe_series.winner_team_id)
        ).scalar_one()
        assert winner.source_team_id == identities["blue_team"]
        assert {oe_series.score_one, oe_series.score_two} == {0, 2}
        assert oe_series.source_snapshot_id is not None
        assert oe_series.source_row_revision == 1

        fallback = session.execute(
            select(Series).where(
                Series.identity_strategy == "fallback",
                Series.series_key.like(f"%{identities['fallback_marker']}%"),
            )
        ).scalar_one()
        assert fallback.best_of == 2
        assert fallback.allows_draw is True
        assert fallback.complete is True
        assert fallback.result_status == "draw"
        assert fallback.winner_team_id is None
        assert fallback.score_one == 1
        assert fallback.score_two == 1

        ambiguous = (
            session.execute(
                select(Game).where(Game.source_game_id.in_(identities["ambiguous_games"]))
            )
            .scalars()
            .all()
        )
        assert len(ambiguous) == 2
        assert all(game.series_id is None for game in ambiguous)
        assert all(game.series_resolution_status == "ambiguous" for game in ambiguous)
    engine.dispose()


def _seed_series(engine: Engine, dataset: str) -> _SeriesIdentities:
    catalog_id = uuid4()
    snapshot_id = uuid4()
    run_id = uuid4()
    suffix = uuid4().hex[:10]
    source_series_id = f"OE-SERIES-{suffix}"
    explicit = (f"EXP-1-{suffix}", f"EXP-2-{suffix}")
    fallback = (f"FALLBACK-1-{suffix}", f"FALLBACK-2-{suffix}")
    ambiguous = (f"AMBIG-1-{suffix}", f"AMBIG-2-{suffix}")
    rows: list[dict[str, str]] = []
    rows.extend(_game_rows(explicit[0], suffix, "2026-08-02", 1, 3, True, source_series_id))
    rows.extend(_game_rows(explicit[1], suffix, "2026-08-02", 2, 3, True, source_series_id))
    rows.extend(_game_rows(fallback[0], suffix, "2026-08-03", 1, 2, True))
    rows.extend(_game_rows(fallback[1], suffix, "2026-08-03", 2, 2, False))
    rows.extend(_game_rows(ambiguous[0], suffix, "2026-08-04", 1, 3, True))
    rows.extend(_game_rows(ambiguous[1], suffix, "2026-08-04", 1, 3, False))
    with engine.begin() as connection:
        _insert_context(connection, dataset, catalog_id, snapshot_id, run_id)
        for ordinal, payload in enumerate(rows, start=1):
            _insert_raw(connection, dataset, snapshot_id, run_id, ordinal, payload)
    return {
        "all_games": explicit + fallback + ambiguous,
        "ambiguous_games": ambiguous,
        "blue_team": f"team-blue-{suffix}",
        "fallback_marker": "2026-08-03",
        "source_series_id": source_series_id,
    }


def _game_rows(
    game_id: str,
    suffix: str,
    event_date: str,
    game_number: int,
    best_of: int,
    blue_wins: bool,
    series_id: str | None = None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for side, participant in (("Blue", "100"), ("Red", "200")):
        is_blue = side == "Blue"
        result = blue_wins if is_blue else not blue_wins
        row = {
            "gameid": game_id,
            "date": event_date,
            "participantid": participant,
            "side": side,
            "position": "team",
            "teamid": f"team-{'blue' if is_blue else 'red'}-{suffix}",
            "teamname": f"Team {'Blue' if is_blue else 'Red'} {suffix}",
            "league": f"League CNL3 {suffix}",
            "patch": "14.3",
            "result": "1" if result else "0",
            "datacompleteness": "complete",
            "gamelength": "1800",
            "forfeit": "false",
            "game": str(game_number),
            "bestof": str(best_of),
        }
        if series_id is not None:
            row["seriesid"] = series_id
        rows.append(row)
    return rows


def _insert_context(
    connection: Connection,
    dataset: str,
    catalog_id: UUID,
    snapshot_id: UUID,
    run_id: UUID,
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
            object_key=f"year=2194/sha256={snapshot_id.hex}/source.csv",
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
            correlation_id=f"cnl-003-{run_id}",
            started_at=_NOW,
            finished_at=_NOW,
            counters={},
            created_at=_NOW,
        )
    )
    connection.execute(
        update(catalog).where(catalog.c.id == catalog_id).values(current_snapshot_id=snapshot_id)
    )


def _insert_raw(
    connection: Connection,
    dataset: str,
    snapshot_id: UUID,
    run_id: UUID,
    ordinal: int,
    payload: dict[str, str],
) -> None:
    table = cast(Table, CanonicalRow.__table__)
    natural_key = json.dumps([payload["gameid"], payload["participantid"]], separators=(",", ":"))
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    connection.execute(
        insert(table).values(
            id=uuid4(),
            provider="oracles_elixir",
            dataset=dataset,
            natural_key=natural_key,
            row_hash=hashlib.sha256(serialized.encode()).hexdigest(),
            payload=payload,
            event_date=date.fromisoformat(payload["date"]),
            source_snapshot_id=snapshot_id,
            source_run_id=run_id,
            revision=1,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )


def _series_ids(engine: Engine, identities: _SeriesIdentities) -> dict[str, tuple[UUID, ...]]:
    games = identities["all_games"]
    with engine.connect() as connection:
        game_ids = (
            connection.execute(
                select(Game.id).where(Game.source_game_id.in_(games)).order_by(Game.id)
            )
            .scalars()
            .all()
        )
        return {
            "games": tuple(game_ids),
            "series": tuple(
                connection.execute(
                    select(Series.id)
                    .where(Series.id.in_(select(Game.series_id).where(Game.id.in_(game_ids))))
                    .order_by(Series.id)
                ).scalars()
            ),
        }
