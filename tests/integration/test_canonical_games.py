"""Preuves des parties et statistiques canoniques sans zéro inventé."""

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
from sqlalchemy.orm import Session

from metiquo.canonical.games import CanonicalGameBuilder
from metiquo.db.core_models import Game, GamePlayerStat, GameTeamStat, Team
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot, SourceCatalog

_ROOT = Path(__file__).resolve().parents[2]
_NOW = datetime(2026, 9, 6, 6, 0, tzinfo=UTC)


def _alembic_config(url: str) -> Config:
    config = Config(_ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


@pytest.mark.integration
def test_games_keep_quality_flags_provenance_and_explicit_missingness(
    postgresql_url: str,
) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = f"cnl_002_{uuid4().hex}"
    game_ids = _seed_games(engine, dataset)
    builder = CanonicalGameBuilder(engine=engine)

    first = builder.build(provider="oracles_elixir", dataset=dataset)
    before = _fact_ids(engine, game_ids)
    second = builder.build(provider="oracles_elixir", dataset=dataset)

    assert first == second
    assert first.source_rows == 18
    assert first.games == 4
    assert first.team_stats == 8
    assert first.player_stats == 10
    assert _fact_ids(engine, game_ids) == before

    with Session(engine) as connection:
        games = {
            item.source_game_id: item
            for item in connection.execute(
                select(Game).where(Game.source_game_id.in_(game_ids.values()))
            ).scalars()
        }
        assert games[game_ids["complete"]].quality_status == "complete"
        assert games[game_ids["complete"]].complete is True
        assert games[game_ids["complete"]].usable_for_training is True
        assert games[game_ids["incomplete"]].quality_status == "incomplete"
        assert games[game_ids["incomplete"]].complete is False
        assert games[game_ids["incomplete"]].usable_for_training is False
        assert games[game_ids["remake"]].quality_status == "remake"
        assert games[game_ids["remake"]].remake is True
        assert games[game_ids["remake"]].usable_for_training is False
        assert games[game_ids["forfeit"]].quality_status == "forfeit"
        assert games[game_ids["forfeit"]].forfeit is True
        assert games[game_ids["forfeit"]].usable_for_training is False

        for game in games.values():
            if game.complete:
                results = (
                    connection.execute(
                        select(GameTeamStat.result)
                        .where(GameTeamStat.game_id == game.id)
                        .order_by(GameTeamStat.side)
                    )
                    .scalars()
                    .all()
                )
                assert len(results) == 2
                assert sum(result is True for result in results) == 1

        blue_team = connection.execute(
            select(GameTeamStat)
            .join(Team, Team.id == GameTeamStat.team_id)
            .where(
                GameTeamStat.game_id == games[game_ids["complete"]].id,
                GameTeamStat.side == "Blue",
            )
        ).scalar_one()
        assert blue_team.gold is None
        assert blue_team.availability["gold"] is False
        assert blue_team.kills == 10
        assert blue_team.availability["kills"] is True

        top_player = connection.execute(
            select(GamePlayerStat).where(
                GamePlayerStat.game_id == games[game_ids["complete"]].id,
                GamePlayerStat.side == "Blue",
                GamePlayerStat.position == "top",
            )
        ).scalar_one()
        assert top_player.assists is None
        assert top_player.availability["assists"] is False
        assert top_player.gold is None
        assert top_player.availability["gold"] is False
        assert top_player.source_snapshot_id == games[game_ids["complete"]].source_snapshot_id
        assert top_player.source_row_revision == 1
        assert top_player.transformation_version == "canonical-games-v1"
    engine.dispose()


def _seed_games(engine: Engine, dataset: str) -> dict[str, str]:
    catalog_id = uuid4()
    snapshot_id = uuid4()
    run_id = uuid4()
    suffix = uuid4().hex[:10]
    game_ids = {kind: f"CNL2-{kind.upper()}-{suffix}" for kind in _KINDS}
    payloads: list[dict[str, str]] = []
    payloads.extend(_complete_game(game_ids["complete"], suffix))
    payloads.extend(_team_only_game(game_ids["incomplete"], suffix, completeness="partial"))
    payloads.extend(_team_only_game(game_ids["remake"], suffix, game_length="500"))
    payloads.extend(_team_only_game(game_ids["forfeit"], suffix, forfeit="true"))
    with engine.begin() as connection:
        _insert_context(connection, dataset, catalog_id, snapshot_id, run_id)
        for ordinal, payload in enumerate(payloads, start=1):
            _insert_raw(connection, dataset, snapshot_id, run_id, ordinal, payload)
    return game_ids


_KINDS = ("complete", "incomplete", "remake", "forfeit")
_POSITIONS = ("top", "jng", "mid", "bot", "sup")


def _base(game_id: str, suffix: str, side: str, participant: str) -> dict[str, str]:
    blue = side == "Blue"
    return {
        "gameid": game_id,
        "date": "2026-08-01T18:00:00Z",
        "participantid": participant,
        "side": side,
        "teamid": f"team-{'blue' if blue else 'red'}-{suffix}",
        "teamname": f"Team {'Blue' if blue else 'Red'} {suffix}",
        "league": f"League CNL2 {suffix}",
        "patch": "14.2",
        "result": "1" if blue else "0",
        "datacompleteness": "complete",
        "gamelength": "1800",
        "forfeit": "false",
    }


def _complete_game(game_id: str, suffix: str) -> list[dict[str, str]]:
    rows = _team_only_game(game_id, suffix)
    for side, start in (("Blue", 1), ("Red", 6)):
        for offset, position in enumerate(_POSITIONS):
            participant = start + offset
            row = _base(game_id, suffix, side, str(participant))
            row.update(
                {
                    "position": position,
                    "playerid": f"player-{side.casefold()}-{position}-{suffix}",
                    "playername": f"{side} {position} {suffix}",
                    "champion": f"Champion-{position}",
                    "kills": str(offset),
                    "deaths": str(4 - offset),
                    "assists": "" if side == "Blue" and position == "top" else "7",
                    "total cs": str(200 + offset),
                    "earnedgold": "" if side == "Blue" and position == "top" else "12000",
                }
            )
            rows.append(row)
    return rows


def _team_only_game(
    game_id: str,
    suffix: str,
    *,
    completeness: str = "complete",
    game_length: str = "1800",
    forfeit: str = "false",
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for side, participant in (("Blue", "100"), ("Red", "200")):
        row = _base(game_id, suffix, side, participant)
        row.update(
            {
                "position": "team",
                "datacompleteness": completeness,
                "gamelength": game_length,
                "forfeit": forfeit,
                "kills": "10" if side == "Blue" else "5",
                "deaths": "5" if side == "Blue" else "10",
                "earnedgold": "" if side == "Blue" else "45000",
                "towers": "8" if side == "Blue" else "3",
                "dragons": "" if side == "Blue" else "2",
                "barons": "1" if side == "Blue" else "0",
            }
        )
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
            season_year=2195,
            landing_page="https://oracleselixir.com/tools/downloads",
            drive_file_id=f"drive-{dataset}",
            source_name="2195_LoL_esports_match_data_from_OraclesElixir.csv.gz",
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
            year=2195,
            source_file_id=f"drive-{dataset}",
            status="validated",
            sha256=hashlib.sha256(f"snapshot-{snapshot_id}".encode()).hexdigest(),
            byte_size=1000,
            content_type="text/csv",
            object_key=f"year=2195/sha256={snapshot_id.hex}/source.csv",
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
            correlation_id=f"cnl-002-{run_id}",
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
            event_date=date(2026, 8, 1),
            source_snapshot_id=snapshot_id,
            source_run_id=run_id,
            revision=1,
            created_at=_NOW,
            updated_at=_NOW,
        )
    )


def _fact_ids(engine: Engine, game_ids: dict[str, str]) -> dict[str, tuple[UUID, ...]]:
    with engine.connect() as connection:
        games = (
            connection.execute(
                select(Game.id).where(Game.source_game_id.in_(game_ids.values())).order_by(Game.id)
            )
            .scalars()
            .all()
        )
        return {
            "games": tuple(games),
            "teams": tuple(
                connection.execute(
                    select(GameTeamStat.id)
                    .where(GameTeamStat.game_id.in_(games))
                    .order_by(GameTeamStat.id)
                ).scalars()
            ),
            "players": tuple(
                connection.execute(
                    select(GamePlayerStat.id)
                    .where(GamePlayerStat.game_id.in_(games))
                    .order_by(GamePlayerStat.id)
                ).scalars()
            ),
        }
