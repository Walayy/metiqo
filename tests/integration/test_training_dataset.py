"""Reproductibilité et provenance du dataset d'entraînement game winner."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import Engine, Table, create_engine, insert, select, text, update
from sqlalchemy.exc import DBAPIError

from metiquo.canonical.rosters import CanonicalRosterBuilder
from metiquo.db.core_models import CanonicalEntityRevision, GameTeamStat
from metiquo.db.raw_models import Snapshot
from metiquo.features import FeatureDatasetBuilder
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.models import GameWinnerDatasetBuilder, GameWinnerDatasetRequest
from tests.integration.test_canonical_rosters import _seed_rosters
from tests.integration.test_migrations import alembic_config

_KNOWLEDGE_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
_CREATED_AT = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)


@pytest.mark.integration
def test_game_winner_dataset_is_reproducible_and_rejects_unvalidated_labels(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    source_dataset = f"ml_001_{uuid4().hex}"
    _seed_rosters(engine, source_dataset)
    CanonicalRosterBuilder(
        engine=engine,
        clock=FixedClock(UtcInstant(_KNOWLEDGE_AT)),
    ).build(dataset=source_dataset)
    feature_report = FeatureDatasetBuilder(
        engine=engine,
        code_commit="abcdef1",
        dataset=source_dataset,
    ).rebuild_from(date(2026, 8, 1))
    request = GameWinnerDatasetRequest(
        period_start=datetime(2026, 8, 1, tzinfo=UTC),
        period_end=datetime(2026, 9, 1, tzinfo=UTC),
    )
    builder = GameWinnerDatasetBuilder(
        engine=engine,
        code_commit="abcdef1",
        dataset=source_dataset,
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    )

    first = builder.build(request)
    repeated = GameWinnerDatasetBuilder(
        engine=engine,
        code_commit="abcdef1",
        dataset=source_dataset,
        clock=FixedClock(UtcInstant(_CREATED_AT.replace(day=8))),
    ).build(request)

    assert first == repeated
    assert first.dataset_id == repeated.dataset_id
    assert first.dataset_hash == repeated.dataset_hash
    assert len(first.dataset_hash) == 64
    assert first.dataset_version == "game-winner-dataset-v1"
    assert first.example_count == 2
    assert first.exclusion_count == 0
    assert first.exclusions == ()
    assert first.cutoff_min == datetime(2026, 8, 5, tzinfo=UTC)
    assert first.cutoff_max == datetime(2026, 8, 10, tzinfo=UTC)
    assert tuple(example.feature_snapshot_id for example in first.examples) == (
        feature_report.snapshot_ids
    )
    assert all(
        example.label_source_snapshot_id in first.oe_snapshot_ids for example in first.examples
    )
    assert builder.get(first.dataset_id) == first
    with engine.connect() as connection:
        for example in first.examples:
            result = connection.execute(
                select(GameTeamStat.result).where(
                    GameTeamStat.game_id == example.event_id,
                    GameTeamStat.team_id == example.team_a_id,
                )
            ).scalar_one()
            status = connection.execute(
                select(Snapshot.status).where(Snapshot.id == example.label_source_snapshot_id)
            ).scalar_one()
            revision_type, revision_snapshot_id = connection.execute(
                select(
                    CanonicalEntityRevision.entity_type,
                    CanonicalEntityRevision.source_snapshot_id,
                ).where(CanonicalEntityRevision.id == example.label_source_revision_id)
            ).one()
            assert result is example.label_team_a_win
            assert status == "validated"
            assert revision_type == "game_team_stat"
            assert revision_snapshot_id == example.label_source_snapshot_id

    quarantined_id = _replace_label_snapshot_with_quarantine(
        engine,
        first.examples[-1].event_id,
        first.examples[-1].team_a_id,
    )
    changed = builder.build(request)

    assert changed.dataset_id != first.dataset_id
    assert changed.dataset_hash != first.dataset_hash
    assert changed.example_count == 1
    assert changed.exclusion_count == 1
    assert changed.exclusions == (
        {
            "event_id": str(first.examples[-1].event_id),
            "reason": "label_snapshot_not_validated",
        },
    )
    assert quarantined_id not in changed.oe_snapshot_ids
    assert builder.get(first.dataset_id) == first
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE ml.datasets SET code_commit = '1234567' WHERE id = :id"),
            {"id": first.dataset_id},
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE ml.dataset_examples SET label_team_a_win = NOT label_team_a_win "
                "WHERE dataset_id = :id"
            ),
            {"id": first.dataset_id},
        )
    engine.dispose()


def _replace_label_snapshot_with_quarantine(
    engine: Engine,
    event_id: UUID,
    team_id: UUID,
) -> UUID:
    snapshots = cast(Table, Snapshot.__table__)
    quarantined_id = uuid4()
    with engine.begin() as connection:
        source = connection.execute(
            select(
                snapshots.c.source_catalog_id,
                snapshots.c.year,
                snapshots.c.source_file_id,
            )
            .join(GameTeamStat, GameTeamStat.source_snapshot_id == snapshots.c.id)
            .where(GameTeamStat.game_id == event_id, GameTeamStat.team_id == team_id)
        ).one()
        connection.execute(
            insert(snapshots).values(
                id=quarantined_id,
                source_catalog_id=source.source_catalog_id,
                year=source.year,
                source_file_id=f"quarantined-{quarantined_id}",
                status="quarantined",
                sha256=hashlib.sha256(str(quarantined_id).encode()).hexdigest(),
                byte_size=12,
                content_type="text/html",
                object_key=f"quarantine/sha256={quarantined_id.hex}/source.bin",
                received_at=_CREATED_AT,
                validated_at=None,
                failure_reason="UNEXPECTED_HTML",
                manifest={},
                created_at=_CREATED_AT,
            )
        )
        connection.execute(
            update(GameTeamStat)
            .where(GameTeamStat.game_id == event_id, GameTeamStat.team_id == team_id)
            .values(source_snapshot_id=quarantined_id)
        )
    return quarantined_id
