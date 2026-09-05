"""Prédictions pré-match reproductibles et append-only."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import Engine, Table, create_engine, select, text
from sqlalchemy.exc import DBAPIError

from metiquo.canonical.rosters import CanonicalRosterBuilder
from metiquo.db.core_models import Game
from metiquo.features import FeatureDatasetBuilder
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.models import (
    CHAMPION,
    EvaluationReportBuilder,
    EvaluationReportParameters,
    GameWinnerDatasetBuilder,
    GameWinnerDatasetRequest,
    ModelArtifactStore,
    ModelInference,
    ModelRegistration,
    ModelRegistry,
    ModelVersion,
    PrematchPredictionRequest,
    PrematchPredictionService,
    ProbabilityModel,
    RegistryChampionRuntimeLoader,
    StoredTrainingDataset,
    UncertaintyArtifact,
    UncertaintyArtifactBuilder,
)
from tests.integration.test_canonical_rosters import _seed_rosters
from tests.integration.test_migrations import alembic_config
from tests.integration.test_model_registry import (
    _calibrator,
    _database_prerequisites,
)

_KNOWLEDGE_AT = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)


@pytest.mark.integration
def test_repeated_prematch_prediction_keeps_reproducible_inference_and_history(
    postgresql_url: str,
    tmp_path: Path,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = _historical_dataset(engine)
    games = cast(Table, Game.__table__)
    with engine.connect() as connection:
        target_event_id, target_start = connection.execute(
            select(games.c.id, games.c.start_at)
            .where(games.c.start_at > dataset.cutoff_max)
            .order_by(games.c.start_at)
            .limit(1)
        ).one()
    assert isinstance(target_start, datetime)
    cutoff = target_start - timedelta(hours=1)
    registered_at = cutoff - timedelta(hours=1)
    calibrator_id, benchmark_id = _database_prerequisites(engine, dataset.dataset_id)
    plan, calibrator = _calibrator(
        dataset_id=dataset.dataset_id,
        calibrator_id=calibrator_id,
        benchmark_id=benchmark_id,
    )
    uncertainty = UncertaintyArtifactBuilder(
        code_commit="abcdef1",
        clock=FixedClock(UtcInstant(registered_at)),
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
        clock=FixedClock(UtcInstant(registered_at)),
    )
    champion = registry.register(
        ModelRegistration(
            algorithm="fixed_test_model",
            hyperparameters=MappingProxyType({"probability": "0.60"}),
            status=CHAMPION,
            registered_by="ml-reviewer",
            reason="initial manually reviewed champion",
            code_commit="abcdef1",
        ),
        evaluation=evaluation,
        uncertainty=uncertainty,
        artifact_payload=b"fixed-model:0.60",
    )
    runtime = RegistryChampionRuntimeLoader(
        registry=registry,
        uncertainty_artifacts=_UncertaintySource(uncertainty),
        decoder=_FixedDecoder(),
    )
    features = FeatureDatasetBuilder(
        engine=engine,
        code_commit="abcdef1",
        dataset=dataset.dataset,
    )

    first = PrematchPredictionService(
        engine=engine,
        features=features,
        runtime=runtime,
        code_commit="abcdef1",
        clock=FixedClock(UtcInstant(cutoff + timedelta(minutes=10))),
    ).predict(PrematchPredictionRequest(event_id=target_event_id, cutoff_at=cutoff))
    second_service = PrematchPredictionService(
        engine=engine,
        features=features,
        runtime=runtime,
        code_commit="abcdef1",
        clock=FixedClock(UtcInstant(cutoff + timedelta(minutes=20))),
    )
    second = second_service.predict(
        PrematchPredictionRequest(event_id=target_event_id, cutoff_at=cutoff)
    )

    assert first.prediction_id != second.prediction_id
    assert first.prediction_fingerprint != second.prediction_fingerprint
    assert first.inference_fingerprint == second.inference_fingerprint
    assert first.feature_snapshot_id == second.feature_snapshot_id
    assert first.model_version_id == second.model_version_id == champion.model_version_id
    assert first.team_a_probability + first.team_b_probability == Decimal(1)
    assert first.team_a_low + first.team_b_high == Decimal(1)
    assert first.team_a_high + first.team_b_low == Decimal(1)
    assert second_service.list_for_event(target_event_id) == (first, second)

    with pytest.raises(ValueError, match="cutoff pré-match"):
        second_service.predict(
            PrematchPredictionRequest(
                event_id=target_event_id,
                cutoff_at=target_start,
            )
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE ml.prematch_predictions SET team_a_probability = 0.5 WHERE id = :id"),
            {"id": first.prediction_id},
        )
    engine.dispose()


def _historical_dataset(engine: Engine) -> StoredTrainingDataset:
    source_dataset = f"ml_013_{uuid4().hex}"
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
        clock=FixedClock(UtcInstant(_KNOWLEDGE_AT)),
    ).build(
        GameWinnerDatasetRequest(
            period_start=datetime(2026, 8, 1, tzinfo=UTC),
            period_end=datetime(2026, 8, 6, tzinfo=UTC),
        )
    )


class _UncertaintySource:
    def __init__(self, artifact: UncertaintyArtifact) -> None:
        self._artifact = artifact

    def get(self, artifact_id: UUID) -> UncertaintyArtifact | None:
        return self._artifact if artifact_id == self._artifact.artifact_id else None


class _FixedDecoder:
    def decode(self, payload: bytes, *, model: ModelVersion) -> ProbabilityModel:
        assert payload == b"fixed-model:0.60"
        assert model.algorithm == "fixed_test_model"
        return _FixedProbabilityModel()


class _FixedProbabilityModel:
    def predict(self, features: Mapping[str, object]) -> ModelInference:
        assert features
        return ModelInference(
            raw_team_a_probability=Decimal("0.60"),
            training_domain_distance=Decimal("0.25"),
        )
