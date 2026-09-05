"""Gate d'un dataset P3 complet, traçable et reproductible."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import Table, create_engine, insert, select

from metiquo.canonical.rosters import CanonicalRosterBuilder
from metiquo.db.core_models import Game
from metiquo.db.feature_models import FeatureInvalidation
from metiquo.features import FeatureDatasetBuilder, FeatureSnapshotStore
from metiquo.foundation.time import FixedClock, UtcInstant
from tests.integration.test_canonical_rosters import _seed_rosters
from tests.integration.test_migrations import alembic_config

_KNOWLEDGE_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)


@pytest.mark.integration
def test_complete_feature_dataset_rebuild_is_deterministic_and_traceable(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = f"feat_014_{uuid4().hex}"
    _seed_rosters(engine, dataset)
    CanonicalRosterBuilder(
        engine=engine,
        clock=FixedClock(UtcInstant(_KNOWLEDGE_AT)),
    ).build(dataset=dataset)
    builder = FeatureDatasetBuilder(
        engine=engine,
        code_commit="abcdef1",
        dataset=dataset,
    )

    first = builder.rebuild_from(date(2026, 8, 1))
    second = builder.rebuild_from(date(2026, 8, 1))

    assert first.target_count == 2
    assert first.snapshot_count == 2
    assert first.created_count == 2
    assert first.rebuilt_count == 0
    assert str(first.coverage) == "1.000000"
    assert first.cutoff_min == datetime(2026, 8, 5, tzinfo=UTC)
    assert first.cutoff_max == datetime(2026, 8, 10, tzinfo=UTC)
    assert first.example_snapshot_id is not None
    assert first.snapshot_ids == second.snapshot_ids
    assert second.created_count == 0
    assert second.rebuilt_count == 0
    assert second.missingness == first.missingness
    assert first.missingness["roster.team_a.individual_strength"] > 0

    example = FeatureSnapshotStore(engine=engine).get(first.example_snapshot_id)
    assert example is not None
    assert example.target_game_ids == (example.event_id,)
    assert example.event_id not in example.source_game_ids
    assert example.max_input_time is None
    assert example.max_knowledge_time is None
    assert example.leakage_checks == {
        "knowledge_time_cutoff": True,
        "source_time_strict_cutoff": True,
        "target_game_excluded": True,
        "train_only_transforms": True,
    }
    assert example.definition_versions
    assert set(example.definition_versions) == set(example.values) == set(example.missingness)
    assert len(example.vector_hash) == 64
    assert len(example.snapshot_hash) == 64

    affected_snapshot_id = first.snapshot_ids[-1]
    affected = FeatureSnapshotStore(engine=engine).get(affected_snapshot_id)
    assert affected is not None
    with engine.connect() as connection:
        source_run_id, source_snapshot_id = connection.execute(
            select(Game.source_run_id, Game.source_snapshot_id).where(Game.id == affected.event_id)
        ).one()
    invalidation_id = uuid4()
    invalidations = cast(Table, FeatureInvalidation.__table__)
    with engine.begin() as connection:
        connection.execute(
            insert(invalidations).values(
                id=invalidation_id,
                source_run_id=cast(UUID, source_run_id),
                source_snapshot_id=cast(UUID, source_snapshot_id),
                provider="oracles_elixir",
                dataset=dataset,
                affected_from=date(2026, 8, 10),
                changed_through=date(2026, 8, 10),
                revision_count=1,
                reason="RAW_ROW_REVISED",
                created_at=datetime(2026, 9, 6, 16, 0, tzinfo=UTC),
            )
        )

    rebuilt_report = builder.rebuild_from(date(2026, 8, 10))
    repeated_report = builder.rebuild_from(date(2026, 8, 10))
    rebuilt_snapshot = FeatureSnapshotStore(engine=engine).get(rebuilt_report.snapshot_ids[0])

    assert rebuilt_report.target_count == 1
    assert rebuilt_report.created_count == 0
    assert rebuilt_report.rebuilt_count == 1
    assert rebuilt_snapshot is not None
    assert rebuilt_snapshot.snapshot_id != affected.snapshot_id
    assert rebuilt_snapshot.supersedes_snapshot_id == affected.snapshot_id
    assert rebuilt_snapshot.generation == 2
    assert rebuilt_snapshot.rebuild_invalidation_ids == (invalidation_id,)
    assert FeatureSnapshotStore(engine=engine).get(affected.snapshot_id) == affected
    assert repeated_report.rebuilt_count == 0
    assert repeated_report.snapshot_ids == rebuilt_report.snapshot_ids
    engine.dispose()
