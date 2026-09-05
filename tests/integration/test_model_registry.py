"""Contraintes PostgreSQL et chargement vérifié du registre de modèles."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import cast
from uuid import UUID, uuid4, uuid5

import pytest
from alembic import command
from sqlalchemy import Engine, Table, create_engine, insert, text
from sqlalchemy.exc import DBAPIError

from metiquo.canonical.rosters import CanonicalRosterBuilder
from metiquo.db.ml_models import CalibratorArtifact as CalibratorArtifactRow
from metiquo.db.ml_models import TabularBenchmarkRun as TabularBenchmarkRunRow
from metiquo.features import FeatureDatasetBuilder
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.models import (
    CHAMPION,
    BaselinePrediction,
    CalibrationCandidateEvaluation,
    CalibrationSearchParameters,
    CalibratorArtifact,
    ChampionAlreadyExistsError,
    EvaluationReportBuilder,
    EvaluationReportParameters,
    GameWinnerDatasetBuilder,
    GameWinnerDatasetRequest,
    ModelArtifactStore,
    ModelRegistration,
    ModelRegistry,
    StoredTrainingDataset,
    UncertaintyArtifactBuilder,
    WalkForwardConfig,
    WalkForwardExample,
    WalkForwardPlan,
    WalkForwardSplitter,
    evaluate_binary_probabilities,
)
from tests.integration.test_canonical_rosters import _seed_rosters
from tests.integration.test_migrations import alembic_config

_NAMESPACE = UUID("30885d30-4e2e-4d4b-a831-7eb0b03d2af0")
_KNOWLEDGE_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
_REGISTERED_AT = datetime(2026, 9, 7, 2, 0, tzinfo=UTC)


@pytest.mark.integration
def test_registry_enforces_single_champion_and_immutable_metadata(
    postgresql_url: str,
    tmp_path: Path,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = _dataset(engine)
    calibrator_id, benchmark_id = _database_prerequisites(engine, dataset.dataset_id)
    plan, calibrator = _calibrator(
        dataset_id=dataset.dataset_id,
        calibrator_id=calibrator_id,
        benchmark_id=benchmark_id,
    )
    uncertainty = UncertaintyArtifactBuilder(
        code_commit="abcdef1",
        clock=FixedClock(UtcInstant(_REGISTERED_AT)),
    ).build(calibrator)
    evaluation = EvaluationReportBuilder(
        code_commit="abcdef1",
        parameters=EvaluationReportParameters(
            calibration_bins=5,
            minimum_segment_samples=2,
        ),
    ).build(plan, calibrator=calibrator, uncertainty=uncertainty)
    registry = ModelRegistry(
        engine=engine,
        artifacts=ModelArtifactStore(FilesystemObjectStore(tmp_path)),
        clock=FixedClock(UtcInstant(_REGISTERED_AT)),
    )
    payload = b"serialized-gradient-boosting-and-calibrator"
    candidate = ModelRegistration(
        algorithm="hist_gradient_boosting",
        hyperparameters=MappingProxyType({"learning_rate": "0.05", "seed": 42}),
        registered_by="ml-reviewer",
        reason="walk-forward gates passed",
        code_commit="abcdef1",
    )

    stored = registry.register(
        candidate,
        evaluation=evaluation,
        uncertainty=uncertainty,
        artifact_payload=payload,
    )

    assert (
        registry.register(
            candidate,
            evaluation=evaluation,
            uncertainty=uncertainty,
            artifact_payload=payload,
        )
        == stored
    )
    assert registry.load_artifact(stored) == payload
    assert stored.dataset_hash == dataset.dataset_hash
    assert stored.feature_set_version == dataset.feature_set_version
    assert stored.training_cutoff_min == dataset.cutoff_min
    assert stored.training_cutoff_max == dataset.cutoff_max
    assert stored.evaluation_report_fingerprint == evaluation.report_fingerprint
    assert stored.uncertainty_fingerprint == uncertainty.artifact_fingerprint

    first_champion = registry.register(
        ModelRegistration(
            algorithm="gradient_boosting",
            hyperparameters=MappingProxyType({"seed": 7}),
            status=CHAMPION,
            registered_by="ml-reviewer",
            reason="manual initial champion",
            code_commit="abcdef2",
        ),
        evaluation=evaluation,
        uncertainty=uncertainty,
        artifact_payload=b"champion-artifact-v1",
    )
    assert registry.current_champion() == first_champion
    with pytest.raises(ChampionAlreadyExistsError, match="champion existe déjà"):
        registry.register(
            ModelRegistration(
                algorithm="challenger",
                hyperparameters=MappingProxyType({"seed": 8}),
                status=CHAMPION,
                registered_by="ml-reviewer",
                reason="conflicting champion",
                code_commit="abcdef3",
            ),
            evaluation=evaluation,
            uncertainty=uncertainty,
            artifact_payload=b"champion-artifact-v2",
        )
    with pytest.raises(DBAPIError, match="immutable metadata"), engine.begin() as connection:
        connection.execute(
            text("UPDATE ml.model_versions SET algorithm = 'tampered' WHERE id = :id"),
            {"id": stored.model_version_id},
        )
    with pytest.raises(DBAPIError, match="cannot be deleted"), engine.begin() as connection:
        connection.execute(
            text("DELETE FROM ml.model_versions WHERE id = :id"),
            {"id": stored.model_version_id},
        )
    engine.dispose()


def _dataset(engine: Engine) -> StoredTrainingDataset:
    source_dataset = f"ml_010_{uuid4().hex}"
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
    return GameWinnerDatasetBuilder(
        engine=engine,
        code_commit="abcdef1",
        dataset=source_dataset,
        clock=FixedClock(UtcInstant(_REGISTERED_AT)),
    ).build(
        GameWinnerDatasetRequest(
            period_start=datetime(2026, 8, 1, tzinfo=UTC),
            period_end=datetime(2026, 9, 1, tzinfo=UTC),
        )
    )


def _database_prerequisites(engine: Engine, dataset_id: UUID) -> tuple[UUID, UUID]:
    benchmarks = cast(Table, TabularBenchmarkRunRow.__table__)
    calibrators = cast(Table, CalibratorArtifactRow.__table__)
    benchmark_id = uuid4()
    calibrator_id = uuid4()
    walk_forward_fingerprint = uuid4().hex * 2
    with engine.begin() as connection:
        connection.execute(
            insert(benchmarks).values(
                id=benchmark_id,
                dataset_id=dataset_id,
                market="game_winner",
                benchmark_version="test-v1",
                walk_forward_fingerprint=walk_forward_fingerprint,
                feature_spec={},
                candidate_evaluations={},
                candidate_count=2,
                selected_candidate="gradient_boosting",
                baseline_run_ids=[str(uuid4()), str(uuid4()), str(uuid4())],
                promotion_gate={},
                promotable=True,
                seed=42,
                predictions_per_candidate=1,
                predictions_fingerprint=uuid4().hex * 2,
                run_fingerprint=uuid4().hex * 2,
                code_commit="abcdef1",
                created_at=_REGISTERED_AT,
            )
        )
        connection.execute(
            insert(calibrators).values(
                id=calibrator_id,
                dataset_id=dataset_id,
                benchmark_run_id=benchmark_id,
                ensemble_run_id=None,
                market="game_winner",
                source_kind="tabular",
                calibrator_version="test-v1",
                walk_forward_fingerprint=walk_forward_fingerprint,
                method="platt",
                parameters={},
                candidate_evaluations={},
                metrics={},
                calibration_slope=Decimal(1),
                calibration_intercept=Decimal(),
                segment_reports=[],
                oos_prediction_count=1,
                oos_predictions_fingerprint=uuid4().hex * 2,
                artifact_fingerprint="b" * 64,
                code_commit="abcdef1",
                created_at=_REGISTERED_AT,
            )
        )
    return calibrator_id, benchmark_id


def _calibrator(
    *,
    dataset_id: UUID,
    calibrator_id: UUID,
    benchmark_id: UUID,
) -> tuple[WalkForwardPlan, CalibratorArtifact]:
    examples = tuple(
        WalkForwardExample(
            example_id=uuid5(_NAMESPACE, f"event-{index}"),
            feature_snapshot_id=uuid5(_NAMESPACE, f"snapshot-{index}"),
            cutoff_at=_REGISTERED_AT - timedelta(days=10 - index),
            label=index % 2 == 0,
            competition_id=uuid5(_NAMESPACE, "competition"),
            patch="14.1",
            international=False,
            feature_values=MappingProxyType(
                {
                    "context.best_of": 3,
                    "context.league": "LCS",
                    "context.stage": "regular",
                }
            ),
            missingness=MappingProxyType({}),
        )
        for index in range(6)
    )
    plan = WalkForwardSplitter(
        WalkForwardConfig(
            minimum_train_periods=1,
            validation_periods=1,
            final_test_periods=1,
        )
    ).split(examples)
    predictions = tuple(
        BaselinePrediction(
            example_id=item.example_id,
            fold_index=index,
            cutoff_at=item.cutoff_at,
            label=item.label,
            probability=Decimal("0.8") if item.label else Decimal("0.2"),
        )
        for index, item in enumerate(plan.oof_validation)
    )
    metrics = evaluate_binary_probabilities(predictions, bin_count=5)
    evaluations = MappingProxyType(
        {
            method: CalibrationCandidateEvaluation(
                method=method,
                metrics=metrics,
                calibration_slope=Decimal(1),
                calibration_intercept=Decimal(),
                oos_predictions_fingerprint="a" * 64,
            )
            for method in ("platt", "isotonic")
        }
    )
    return plan, CalibratorArtifact(
        artifact_id=calibrator_id,
        dataset_id=dataset_id,
        benchmark_run_id=benchmark_id,
        ensemble_run_id=None,
        market="game_winner",
        source_kind="tabular",
        calibrator_version="test-v1",
        walk_forward_fingerprint=plan.fingerprint,
        method="isotonic",
        parameters=MappingProxyType(
            {"x_thresholds": ["0.00000000", "1.00000000"], "y_thresholds": ["0", "1"]}
        ),
        search=CalibrationSearchParameters(),
        candidate_evaluations=evaluations,
        metrics=metrics,
        calibration_slope=Decimal(1),
        calibration_intercept=Decimal(),
        segment_reports=(),
        oos_predictions_fingerprint="a" * 64,
        artifact_fingerprint="b" * 64,
        code_commit="abcdef1",
        created_at=_REGISTERED_AT,
        oos_predictions=predictions,
    )
