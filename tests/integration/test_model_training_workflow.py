"""Commande d'entraînement complète sur les tables PostgreSQL réelles."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4, uuid5

import pytest
from alembic import command
from sqlalchemy import Engine, Table, create_engine, insert, select

from metiquo.canonical.rosters import CanonicalRosterBuilder
from metiquo.db.core_models import CanonicalEntityRevision, Game
from metiquo.db.feature_models import FeatureSnapshot
from metiquo.db.ml_models import TrainingDataset, TrainingDatasetExample
from metiquo.features import FeatureDatasetBuilder
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.models import (
    BLOCKED,
    CANDIDATE,
    CHAMPION,
    GameWinnerTrainingWorkflow,
    ModelArtifactStore,
    ModelLifecycle,
    ModelRegistry,
    PromotionEvidence,
    TabularFeatureSpec,
    WalkForwardConfig,
)
from tests.integration.test_canonical_rosters import _seed_rosters
from tests.integration.test_migrations import alembic_config

_NAMESPACE = UUID("15395da0-1550-49cb-920e-eac65104a453")
_KNOWLEDGE_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
_CREATED_AT = datetime(2026, 9, 7, 13, 0, tzinfo=UTC)


@pytest.mark.integration
def test_training_workflow_publishes_candidate_then_allows_gated_promotion(
    postgresql_url: str,
    tmp_path: Path,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset_id = _seed_training_dataset(engine)
    artifacts = ModelArtifactStore(FilesystemObjectStore(tmp_path / "models"))
    workflow = GameWinnerTrainingWorkflow(
        engine=engine,
        artifacts=artifacts,
        code_commit="abcdef1",
        dataset_id=dataset_id,
        walk_forward=WalkForwardConfig(
            minimum_train_periods=20,
            validation_periods=10,
            final_test_periods=10,
        ),
        features=TabularFeatureSpec(
            numeric_fields=("economy.team_a.kills_per_minute",),
            categorical_fields=(),
        ),
        clock=FixedClock(UtcInstant(_CREATED_AT)),
    )

    result = workflow.run()
    registry = ModelRegistry(engine=engine, artifacts=artifacts)
    version = registry.get(result.model_version_id)

    assert result.gate_passed is True
    assert result.model_status == CANDIDATE
    assert version is not None
    assert version.status == CANDIDATE
    assert registry.current_champion() is None
    assert len(result.baselines) == 3
    assert result.reproduction.dataset_id == dataset_id
    assert result.reproduction.feature_snapshot_id in {
        item.feature_snapshot_id for item in result.plan.final_test
    }

    evidence = PromotionEvidence(
        evaluation_report_fingerprint=result.evaluation.report_fingerprint,
        baseline_log_loss_deltas={
            item.baseline_name: item.log_loss_gain
            for item in result.benchmark.promotion_gate.comparisons
        },
        metric_basis=("log_loss", "calibration_ece"),
        manual_approval_reference="integration-review-ml-017",
    )
    promoted = ModelLifecycle(
        engine=engine,
        clock=FixedClock(UtcInstant(_CREATED_AT + timedelta(minutes=1))),
    ).promote(
        result.model_version_id,
        actor="ml-reviewer",
        reason="gate P4 vérifié",
        evidence=evidence,
    )

    assert promoted.status == CHAMPION
    assert registry.current_champion() is not None
    assert registry.current_champion().model_version_id == result.model_version_id  # type: ignore[union-attr]

    rejected = GameWinnerTrainingWorkflow(
        engine=engine,
        artifacts=artifacts,
        code_commit="abcdef1",
        dataset_id=dataset_id,
        walk_forward=WalkForwardConfig(
            minimum_train_periods=20,
            validation_periods=10,
            final_test_periods=10,
        ),
        features=TabularFeatureSpec(
            numeric_fields=("rating.difference",),
            categorical_fields=(),
        ),
        clock=FixedClock(UtcInstant(_CREATED_AT + timedelta(minutes=2))),
    ).run()

    assert rejected.gate_passed is False
    assert rejected.model_status == BLOCKED
    assert registry.get(rejected.model_version_id).status == BLOCKED  # type: ignore[union-attr]
    assert registry.current_champion().model_version_id == result.model_version_id  # type: ignore[union-attr]
    engine.dispose()


def _seed_training_dataset(engine: Engine) -> UUID:
    source_dataset = f"ml_017_{uuid4().hex}"
    _seed_rosters(engine, source_dataset)
    CanonicalRosterBuilder(
        engine=engine,
        clock=FixedClock(UtcInstant(_KNOWLEDGE_AT)),
    ).build(dataset=source_dataset)
    FeatureDatasetBuilder(
        engine=engine,
        code_commit="abcdef1",
        dataset=source_dataset,
    ).rebuild_from(date(2026, 8, 1))

    games = cast(Table, Game.__table__)
    snapshots = cast(Table, FeatureSnapshot.__table__)
    revisions = cast(Table, CanonicalEntityRevision.__table__)
    datasets = cast(Table, TrainingDataset.__table__)
    examples = cast(Table, TrainingDatasetExample.__table__)
    with engine.connect() as connection:
        game_template = dict(connection.execute(select(games).limit(1)).mappings().one())
        snapshot_template = dict(connection.execute(select(snapshots).limit(1)).mappings().one())
        label_revision_id = cast(
            UUID,
            connection.execute(select(revisions.c.id).limit(1)).scalar_one(),
        )

    dataset_id = uuid4()
    competition_id = cast(UUID | None, game_template["competition_id"])
    feature_set_id = cast(UUID, snapshot_template["feature_set_id"])
    source_snapshot_id = cast(UUID, game_template["source_snapshot_id"])
    start = datetime(2025, 1, 1, tzinfo=UTC)
    game_rows: list[dict[str, object]] = []
    snapshot_rows: list[dict[str, object]] = []
    example_rows: list[dict[str, object]] = []
    for index in range(70):
        event_id = uuid5(dataset_id, f"event-{index}")
        feature_snapshot_id = uuid5(dataset_id, f"feature-{index}")
        cutoff = start + timedelta(days=index)
        label = index % 4 != 0
        signal = 4.0 if label else -4.0
        game_row = {
            **game_template,
            "id": event_id,
            "source_game_id": f"ml-017-{dataset_id}-{index}",
            "source_natural_key": f"ml-017-game-{dataset_id}-{index}",
            "source_row_hash": _hash(f"game-{dataset_id}-{index}"),
            "event_date": cutoff.date(),
            "start_at": cutoff + timedelta(hours=4),
            "processed_at": _KNOWLEDGE_AT,
        }
        game_rows.append(game_row)
        snapshot_rows.append(
            {
                **snapshot_template,
                "id": feature_snapshot_id,
                "event_id": event_id,
                "cutoff_at": cutoff,
                "max_input_time": None,
                "max_knowledge_time": None,
                "values": {
                    "economy.team_a.kills_per_minute": signal,
                    "rating.difference": 0,
                },
                "missingness": {},
                "source_game_ids": [],
                "target_game_ids": [str(event_id)],
                "source_revision_ids": [],
                "source_snapshot_ids": [str(source_snapshot_id)],
                "source_games_fingerprint": _hash(f"games-{dataset_id}-{index}"),
                "vector_hash": _hash(f"vector-{dataset_id}-{index}"),
                "snapshot_hash": _hash(f"snapshot-{dataset_id}-{index}"),
                "supersedes_snapshot_id": None,
                "created_at": _CREATED_AT,
            }
        )
        example_rows.append(
            {
                "dataset_id": dataset_id,
                "position": index,
                "event_id": event_id,
                "feature_snapshot_id": feature_snapshot_id,
                "team_a_id": snapshot_template["team_a_id"],
                "team_b_id": snapshot_template["team_b_id"],
                "competition_id": competition_id,
                "cutoff_at": cutoff,
                "label_team_a_win": label,
                "label_source_revision_id": label_revision_id,
                "label_source_snapshot_id": source_snapshot_id,
            }
        )
    with engine.begin() as connection:
        connection.execute(insert(games), game_rows)
        connection.execute(insert(snapshots), snapshot_rows)
        connection.execute(
            insert(datasets).values(
                id=dataset_id,
                market="game_winner",
                provider="oracles_elixir",
                dataset=source_dataset,
                dataset_version="game-winner-dataset-v1",
                feature_set_id=feature_set_id,
                feature_set_version="full-v1",
                feature_set_hash=_hash("feature-set"),
                label_definition="team-a-win-v1",
                quality_filter={},
                period_start=start,
                period_end=start + timedelta(days=70),
                cutoff_min=start,
                cutoff_max=start + timedelta(days=69),
                competition_ids=[str(competition_id)] if competition_id else [],
                oe_snapshot_ids=[str(source_snapshot_id)],
                exclusions=[],
                example_count=70,
                exclusion_count=0,
                examples_fingerprint=_hash(f"examples-{dataset_id}"),
                dataset_hash=_hash(f"dataset-{dataset_id}"),
                code_commit="abcdef1",
                created_at=_CREATED_AT,
            )
        )
        connection.execute(insert(examples), example_rows)
    return dataset_id


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
