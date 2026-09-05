"""Snapshot de feature immuable, hashé et reproductible."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

from metiquo.canonical.rosters import CanonicalRosterBuilder
from metiquo.db.core_models import Team
from metiquo.features import (
    AsOfGameRepository,
    CutoffViolationError,
    FeatureCutoff,
    FeatureDefinitionSpec,
    FeatureRegistry,
    FeatureSetSpec,
    FeatureSnapshotSpec,
    FeatureSnapshotStore,
)
from metiquo.foundation.time import FixedClock, UtcInstant
from tests.integration.test_canonical_rosters import _seed_rosters
from tests.integration.test_migrations import alembic_config

_KNOWLEDGE_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
_CUTOFF = FeatureCutoff(datetime(2026, 8, 15, tzinfo=UTC))
_CREATED_AT = datetime(2026, 9, 6, 15, 0, tzinfo=UTC)


@pytest.mark.integration
def test_snapshot_hash_roundtrip_idempotence_and_append_only(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = f"feat_011_{uuid4().hex}"
    identities = _seed_rosters(engine, dataset)
    CanonicalRosterBuilder(
        engine=engine,
        clock=FixedClock(UtcInstant(_KNOWLEDGE_AT)),
    ).build(dataset=dataset)
    with engine.connect() as connection:
        team_a_id = connection.execute(
            select(Team.id).where(Team.source_team_id == identities["blue_team"])
        ).scalar_one()
    batch = AsOfGameRepository(engine).list_before(
        cutoff=_CUTOFF,
        team_ids=frozenset({team_a_id}),
    )
    team_b_id = next(
        stat.team_id for stat in batch.games[0].team_stats if stat.team_id != team_a_id
    )
    registry = FeatureRegistry(
        engine=engine,
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    )
    feature_set = registry.register_set(
        FeatureSetSpec(
            name=f"snapshot-test-{dataset}",
            set_version="v1",
            code_version="snapshot-test-v1",
            definitions=(
                FeatureDefinitionSpec(
                    name="rating.team_a",
                    domain="rating",
                    definition_version="v1",
                    parameters={},
                    availability="required",
                    code_version="v1",
                ),
                FeatureDefinitionSpec(
                    name="roster.team_a.confidence",
                    domain="roster",
                    definition_version="v1",
                    parameters={},
                    availability="optional",
                    code_version="v1",
                ),
            ),
        )
    )
    vector = registry.build_vector(
        feature_set_name=feature_set.name,
        feature_set_version=feature_set.set_version,
        values={
            "rating.team_a": Decimal("1510.500000"),
            "roster.team_a.confidence": None,
        },
    )
    event_id = uuid4()
    target_game_id = uuid4()
    specification = FeatureSnapshotSpec(
        event_id=event_id,
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        target_oe_snapshot_id=batch.source_snapshot_ids[0],
        cutoff=_CUTOFF,
        vector=vector,
        source_batch=batch,
        target_game_ids=frozenset({target_game_id}),
        code_commit="abcdef1",
        leakage_checks={"train_only_transforms": True},
    )
    store = FeatureSnapshotStore(
        engine=engine,
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    )

    first = store.create(specification)
    second = store.create(specification)

    assert first == second
    assert store.get(first.snapshot_id) == first
    assert first.feature_set_id == feature_set.feature_set_id
    assert first.event_id == event_id
    assert first.cutoff_at == _CUTOFF.at
    assert first.max_input_time is not None and first.max_input_time < first.cutoff_at
    assert first.max_knowledge_time == _KNOWLEDGE_AT
    assert first.values == {
        "rating.team_a": "1510.500000",
        "roster.team_a.confidence": None,
    }
    assert first.missingness == {
        "rating.team_a": False,
        "roster.team_a.confidence": True,
    }
    assert set(first.source_game_ids) == {game.game_id for game in batch.games}
    assert set(batch.source_revision_ids) == set(first.source_revision_ids)
    assert batch.source_snapshot_ids[0] in first.source_snapshot_ids
    assert all(first.leakage_checks.values())
    assert len(first.source_games_fingerprint) == 64
    assert len(first.vector_hash) == 64
    assert len(first.snapshot_hash) == 64
    assert first.generation == 1

    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(text("UPDATE features.feature_snapshots SET code_commit = '1234567'"))
    with pytest.raises(CutoffViolationError, match="target_game_excluded"):
        store.create(
            FeatureSnapshotSpec(
                event_id=event_id,
                team_a_id=team_a_id,
                team_b_id=team_b_id,
                target_oe_snapshot_id=batch.source_snapshot_ids[0],
                cutoff=_CUTOFF,
                vector=vector,
                source_batch=batch,
                target_game_ids=frozenset({batch.games[0].game_id}),
                code_commit="abcdef1",
                leakage_checks={"train_only_transforms": True},
            )
        )
    with pytest.raises(CutoffViolationError, match="train_only_transforms"):
        store.create(
            FeatureSnapshotSpec(
                event_id=event_id,
                team_a_id=team_a_id,
                team_b_id=team_b_id,
                target_oe_snapshot_id=batch.source_snapshot_ids[0],
                cutoff=_CUTOFF,
                vector=vector,
                source_batch=batch,
                target_game_ids=frozenset({target_game_id}),
                code_commit="abcdef1",
                leakage_checks={"train_only_transforms": False},
            )
        )
    engine.dispose()
