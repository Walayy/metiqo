"""Tests des cutoffs obligatoires pour SQL, Polars et historique canonique."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import polars as pl
import pytest
from alembic import command
from sqlalchemy import Table, create_engine, select, update

from metiquo.canonical.series import CanonicalSeriesBuilder
from metiquo.db.core_models import Game
from metiquo.db.raw_models import CanonicalRow
from metiquo.features import (
    AsOfGameRepository,
    CutoffViolationError,
    FeatureCutoff,
    polars_strictly_before,
    strictly_before_cutoff,
)
from metiquo.foundation.time import FixedClock, UtcInstant
from tests.integration.test_canonical_series import _seed_series
from tests.integration.test_migrations import alembic_config

_PROCESSED_AT = datetime(2026, 9, 6, 13, 0, tzinfo=UTC)
_CUTOFF_AT = datetime(2026, 9, 6, 14, 0, tzinfo=UTC)


@pytest.mark.integration
def test_as_of_repository_excludes_game_at_cutoff_and_records_max_input_time(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = f"feat_002_{uuid4().hex}"
    identities = _seed_series(engine, dataset)
    injected_game = identities["all_games"][0]
    raw = cast(Table, CanonicalRow.__table__)
    with engine.begin() as connection:
        rows = connection.execute(
            select(raw.c.id, raw.c.payload).where(
                raw.c.dataset == dataset,
                raw.c.payload["gameid"].astext == injected_game,
            )
        ).mappings()
        for row in rows:
            payload = dict(cast(dict[str, object], row["payload"]))
            payload["date"] = _CUTOFF_AT.isoformat()
            connection.execute(
                update(raw)
                .where(raw.c.id == row["id"])
                .values(payload=payload, event_date=_CUTOFF_AT.date())
            )
    CanonicalSeriesBuilder(
        engine=engine,
        clock=FixedClock(UtcInstant(_PROCESSED_AT)),
    ).build(dataset=dataset)

    repository = AsOfGameRepository(engine)
    cutoff = FeatureCutoff(_CUTOFF_AT)
    batch = repository.list_before(cutoff=cutoff)

    assert len(batch.games) == 5
    assert injected_game not in {game.source_game_id for game in batch.games}
    assert batch.audit.cutoff_at == _CUTOFF_AT
    assert batch.audit.input_count == 5
    assert batch.audit.max_input_time is not None
    assert batch.audit.max_input_time < batch.audit.cutoff_at
    assert batch.audit.max_knowledge_time == _PROCESSED_AT
    assert len(batch.source_revision_ids) == 15
    assert len(batch.source_snapshot_ids) == 1
    assert all(len(game.team_stats) == 2 for game in batch.games)

    team_id = batch.games[0].team_stats[0].team_id
    assert len(repository.list_before(cutoff=cutoff, team_ids=frozenset({team_id})).games) == 5
    assert (
        repository.list_before(cutoff=cutoff, team_ids=frozenset({uuid4()})).audit.input_count == 0
    )
    with pytest.raises(TypeError, match="FeatureCutoff explicite"):
        repository.list_before(cutoff=cast(Any, None))
    engine.dispose()


def test_cutoff_helpers_are_strict_for_polars_and_direct_audits() -> None:
    cutoff = FeatureCutoff(_CUTOFF_AT)
    before = _CUTOFF_AT - timedelta(microseconds=1)
    after = _CUTOFF_AT + timedelta(microseconds=1)
    frame = pl.DataFrame({"event_time": [before, _CUTOFF_AT, after], "value": [1, 2, 3]})

    filtered = polars_strictly_before(
        frame,
        timestamp_column="event_time",
        cutoff=cutoff,
    ).collect()

    assert filtered["value"].to_list() == [1]
    audit = cutoff.audit([before], source_knowledge_times=[_CUTOFF_AT])
    assert audit.max_input_time == before
    assert audit.max_knowledge_time == _CUTOFF_AT
    with pytest.raises(CutoffViolationError, match="strictement antérieur"):
        cutoff.audit([_CUTOFF_AT])
    with pytest.raises(CutoffViolationError, match="connue après"):
        cutoff.audit([before], source_knowledge_times=[after])
    with pytest.raises(ValueError, match="colonne temporelle absente"):
        polars_strictly_before(frame, timestamp_column="missing", cutoff=cutoff)

    games = cast(Table, Game.__table__)
    statement = strictly_before_cutoff(select(games.c.id), games.c.start_at, cutoff)
    assert "core.games.start_at <" in str(statement)
    with pytest.raises(TypeError, match="FeatureCutoff explicite"):
        strictly_before_cutoff(select(games.c.id), games.c.start_at, cast(Any, None))
