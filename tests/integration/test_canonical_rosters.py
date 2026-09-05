"""Preuves temporelles des observations et projections de roster."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypedDict, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, Table, create_engine, func, insert, select, update
from sqlalchemy.orm import Session

from metiquo.canonical.rosters import CanonicalRosterBuilder, RosterProjectionService
from metiquo.db.core_models import Game, RosterObservation, Team
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot, SourceCatalog
from metiquo.features import AsOfGameRepository, FeatureCutoff, RosterFeatureCalculator
from metiquo.foundation.time import FixedClock, UtcInstant

_ROOT = Path(__file__).resolve().parents[2]
_NOW = datetime(2026, 9, 6, 10, 0, tzinfo=UTC)
_KNOWLEDGE_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
_POSITIONS = ("top", "jng", "mid", "bot", "sup")


class _RosterIdentities(TypedDict):
    blue_team: str
    games: tuple[str, str]


def _alembic_config(url: str) -> Config:
    config = Config(_ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


@pytest.mark.integration
def test_roster_projection_is_as_of_and_unknown_substitution_lowers_confidence(
    postgresql_url: str,
) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = f"cnl_004_{uuid4().hex}"
    identities = _seed_rosters(engine, dataset)
    builder = CanonicalRosterBuilder(
        engine=engine,
        clock=FixedClock(UtcInstant(_KNOWLEDGE_AT)),
    )

    first = builder.build(provider="oracles_elixir", dataset=dataset)
    observation_ids = _observation_ids(engine, identities["games"])
    second = builder.build(provider="oracles_elixir", dataset=dataset)

    assert first == second
    assert first.observations == 20
    assert first.substitutions == 1
    assert _observation_ids(engine, identities["games"]) == observation_ids

    with Session(engine) as session:
        blue_team = session.execute(
            select(Team).where(Team.source_team_id == identities["blue_team"])
        ).scalar_one()
        top_history = (
            session.execute(
                select(RosterObservation)
                .where(
                    RosterObservation.team_id == blue_team.id,
                    RosterObservation.role == "top",
                )
                .order_by(RosterObservation.observed_at)
            )
            .scalars()
            .all()
        )
        assert [item.continuity_status for item in top_history] == [
            "first_seen",
            "substitution_observed",
        ]
        assert top_history[0].player_id != top_history[1].player_id
        assert top_history[1].observation_confidence == Decimal("0.6500")

        before_projection = session.scalar(select(func.count()).select_from(RosterObservation))
        projection = RosterProjectionService(engine=engine)
        before_change = {
            member.role: member
            for member in projection.as_of(
                team_id=blue_team.id,
                cutoff=datetime(2026, 8, 10, tzinfo=UTC),
            )
        }
        after_change = {
            member.role: member
            for member in projection.as_of(
                team_id=blue_team.id,
                cutoff=datetime(2026, 8, 15, tzinfo=UTC),
            )
        }
        session.expire_all()
        after_projection = session.scalar(select(func.count()).select_from(RosterObservation))

        assert before_change["top"].player_id == top_history[0].player_id
        assert before_change["top"].confidence == Decimal("1.0000")
        assert after_change["top"].player_id == top_history[1].player_id
        assert after_change["top"].confidence == Decimal("0.6500")
        assert after_change["jng"].confidence == Decimal("1.0000")
        assert all(
            member.observed_at < datetime(2026, 8, 15, tzinfo=UTC)
            for member in after_change.values()
        )
        assert before_projection == after_projection

        before_batch = AsOfGameRepository(engine).list_before(
            cutoff=FeatureCutoff(datetime(2026, 8, 10, tzinfo=UTC)),
            team_ids=frozenset({blue_team.id}),
        )
        after_batch = AsOfGameRepository(engine).list_before(
            cutoff=FeatureCutoff(datetime(2026, 8, 15, tzinfo=UTC)),
            team_ids=frozenset({blue_team.id}),
        )
        before_features = RosterFeatureCalculator().calculate(
            before_batch,
            team_a_id=blue_team.id,
            team_b_id=before_batch.games[0].team_stats[1].team_id,
        )
        after_features = RosterFeatureCalculator().calculate(
            after_batch,
            team_a_id=blue_team.id,
            team_b_id=after_batch.games[0].team_stats[1].team_id,
        )

        assert len(before_batch.games) == 1
        assert len(after_batch.games) == 2
        assert all(len(game.player_stats) == 10 for game in after_batch.games)
        assert all(len(game.roster_observations) == 10 for game in after_batch.games)
        assert before_features.team_a.expected_roster["top"].player_id == top_history[0].player_id
        assert after_features.team_a.expected_roster["top"].player_id == top_history[1].player_id
        assert before_features.team_a.games_together == 1
        assert after_features.team_a.games_together == 1
        assert (
            after_features.team_a.expected_roster["top"].observed_at < after_batch.audit.cutoff_at
        )
    engine.dispose()


def _seed_rosters(engine: Engine, dataset: str) -> _RosterIdentities:
    catalog_id = uuid4()
    snapshot_id = uuid4()
    run_id = uuid4()
    suffix = uuid4().hex[:10]
    games = (f"ROSTER-1-{suffix}", f"ROSTER-2-{suffix}")
    payloads = _game_rows(games[0], suffix, "2026-08-05", changed_top=False)
    payloads.extend(_game_rows(games[1], suffix, "2026-08-10", changed_top=True))
    with engine.begin() as connection:
        _insert_context(connection, dataset, catalog_id, snapshot_id, run_id)
        for ordinal, payload in enumerate(payloads, start=1):
            _insert_raw(connection, dataset, snapshot_id, run_id, ordinal, payload)
    return {"blue_team": f"team-blue-{suffix}", "games": games}


def _game_rows(
    game_id: str, suffix: str, event_date: str, *, changed_top: bool
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for side, participant in (("Blue", "100"), ("Red", "200")):
        rows.append(_base_row(game_id, suffix, event_date, side, participant, "team"))
    for side, start in (("Blue", 1), ("Red", 6)):
        for offset, position in enumerate(_POSITIONS):
            participant = str(start + offset)
            row = _base_row(game_id, suffix, event_date, side, participant, position)
            player_key = f"player-{side.casefold()}-{position}-{suffix}"
            if side == "Blue" and position == "top" and changed_top:
                player_key = f"player-blue-top-sub-{suffix}"
            row.update(
                {
                    "playerid": player_key,
                    "playername": player_key,
                    "champion": f"Champion-{position}",
                    "kills": "2",
                    "deaths": "1",
                    "assists": "5",
                }
            )
            rows.append(row)
    return rows


def _base_row(
    game_id: str,
    suffix: str,
    event_date: str,
    side: str,
    participant: str,
    position: str,
) -> dict[str, str]:
    blue = side == "Blue"
    return {
        "gameid": game_id,
        "date": event_date,
        "participantid": participant,
        "side": side,
        "position": position,
        "teamid": f"team-{'blue' if blue else 'red'}-{suffix}",
        "teamname": f"Team {'Blue' if blue else 'Red'} {suffix}",
        "league": f"League CNL4 {suffix}",
        "patch": "14.4",
        "result": "1" if blue else "0",
        "datacompleteness": "complete",
        "gamelength": "1800",
        "forfeit": "false",
    }


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
            season_year=2193,
            landing_page="https://oracleselixir.com/tools/downloads",
            drive_file_id=f"drive-{dataset}",
            source_name="2193_LoL_esports_match_data_from_OraclesElixir.csv.gz",
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
            year=2193,
            source_file_id=f"drive-{dataset}",
            status="validated",
            sha256=hashlib.sha256(f"snapshot-{snapshot_id}".encode()).hexdigest(),
            byte_size=1000,
            content_type="text/csv",
            object_key=f"year=2193/sha256={snapshot_id.hex}/source.csv",
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
            correlation_id=f"cnl-004-{run_id}",
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


def _observation_ids(engine: Engine, source_games: tuple[str, str]) -> tuple[UUID, ...]:
    with engine.connect() as connection:
        return tuple(
            connection.execute(
                select(RosterObservation.id)
                .join(Game, Game.id == RosterObservation.game_id)
                .where(Game.source_game_id.in_(source_games))
                .order_by(RosterObservation.id)
            ).scalars()
        )
