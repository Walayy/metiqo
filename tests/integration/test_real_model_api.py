"""API réelle des modèles, backtests et décisions auditées."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient, Response
from sqlalchemy import Engine, Table, create_engine, insert, text
from sqlalchemy.exc import DBAPIError

from metiquo.api.app import create_app
from metiquo.contracts.enums import GameTitle, MarketType
from metiquo.db.ml_models import BaselineRun as BaselineRunRow
from metiquo.db.ml_models import CalibratorArtifact as CalibratorArtifactRow
from metiquo.db.ml_models import TabularBenchmarkRun as TabularBenchmarkRunRow
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.models import (
    EvaluationReport,
    EvaluationReportBuilder,
    EvaluationReportParameters,
    ModelArtifactStore,
    ModelRegistration,
    ModelRegistry,
    ModelVersion,
    UncertaintyArtifactBuilder,
)
from metiquo.repositories.postgres_admin import PostgresAdminRepository
from metiquo.repositories.postgres_models import PostgresModelRepository
from metiquo.services.real_admin import RealAdminMutationService
from tests.integration.test_migrations import alembic_config
from tests.integration.test_model_registry import (
    _calibrator,
    _dataset,
)
from tests.integration.test_real_admin_api import ReadyProbe, _seed_real_health, _settings

NOW = datetime(2026, 9, 7, 5, tzinfo=UTC)


class FixedTrainingWorkflow:
    """Double de frontière : le candidat reste un vrai enregistrement PostgreSQL."""

    def __init__(self, model_version_id: UUID) -> None:
        self.model_version_id = model_version_id
        self.calls = 0

    def train(self, game_title: GameTitle, market_type: MarketType) -> UUID:
        assert game_title is GameTitle.LEAGUE_OF_LEGENDS
        assert market_type is MarketType.MATCH_WINNER
        self.calls += 1
        return self.model_version_id


def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: dict[str, object] | None = None,
) -> Response:
    async def send() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, headers=headers, json=json)

    return asyncio.run(send())


@pytest.mark.integration
def test_real_model_api_projects_metrics_and_audits_gated_mutations(
    postgresql_url: str,
    tmp_path: Path,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    _seed_real_health(postgresql_url, "real-model-api-health")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    clock = FixedClock(UtcInstant(NOW))
    candidate, evaluation = _build_candidate(
        engine,
        tmp_path,
        clock,
        promotable=True,
        artifact_payload=b"real-api-model",
    )
    rejected_candidate, _ = _build_candidate(
        engine,
        tmp_path,
        clock,
        promotable=False,
        artifact_payload=b"rejected-api-model",
    )
    model_repository = PostgresModelRepository(engine)
    admin_repository = PostgresAdminRepository(engine, clock)
    workflow = FixedTrainingWorkflow(candidate.model_version_id)
    service = RealAdminMutationService(
        engine,
        _settings(postgresql_url, "real"),
        admin_repository,
        model_repository,
        workflow,
        clock,
    )
    app = create_app(
        settings=_settings(postgresql_url, "real"),
        readiness_probe=ReadyProbe(),
        clock=clock,
        real_admin_repository=admin_repository,
        real_mutation_service=service,
    )

    models_response = _request(app, "GET", "/api/v1/models")
    backtests_response = _request(app, "GET", "/api/v1/backtests")
    assert models_response.status_code == backtests_response.status_code == 200
    model = next(
        item
        for item in models_response.json()["data"]
        if item["modelVersionId"] == str(candidate.model_version_id)
    )
    backtest = next(
        item
        for item in backtests_response.json()["data"]
        if item["modelVersionId"] == str(candidate.model_version_id)
    )
    assert model["modelVersion"] == str(candidate.model_version_id)
    assert model["metrics"]["log_loss"] == str(evaluation.overall.log_loss)
    assert model["baselineMetrics"]["log_loss"] == "0.41"
    assert backtest["modelVersionId"] == str(candidate.model_version_id)
    assert backtest["sampleCount"] == evaluation.overall.sample_count
    assert backtest["finalTestUntouched"] is True

    headers = {"Idempotency-Key": "real-model-train-001"}
    trained = _request(
        app,
        "POST",
        "/api/v1/admin/models/train",
        headers=headers,
        json={"gameTitle": "lol", "marketType": "MATCH_WINNER"},
    )
    replay = _request(
        app,
        "POST",
        "/api/v1/admin/models/train",
        headers=headers,
        json={"gameTitle": "lol", "marketType": "MATCH_WINNER"},
    )
    assert trained.status_code == replay.status_code == 200
    assert trained.json() == replay.json()
    assert workflow.calls == 1

    rejected = _request(
        app,
        "POST",
        f"/api/v1/admin/models/{rejected_candidate.model_version_id}/promote",
        headers={"Idempotency-Key": "real-model-promote-failed"},
        json={"reason": "attempt before gates"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "INVALID_STATE"

    promoted = _request(
        app,
        "POST",
        f"/api/v1/admin/models/{candidate.model_version_id}/promote",
        headers={"Idempotency-Key": "real-model-promote-passed"},
        json={"reason": "three baselines and probabilistic metrics passed"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["data"]["status"] == "champion"
    promote_conflict = _request(
        app,
        "POST",
        f"/api/v1/admin/models/{candidate.model_version_id}/promote",
        headers={"Idempotency-Key": "real-model-promote-passed"},
        json={"reason": "same key but a different decision payload"},
    )
    assert promote_conflict.status_code == 409
    assert promote_conflict.json()["code"] == "CONFLICT"

    retired = _request(
        app,
        "POST",
        f"/api/v1/admin/models/{candidate.model_version_id}/retire",
        headers={"Idempotency-Key": "real-model-retire-001"},
        json={"reason": "manual operational retirement"},
    )
    assert retired.status_code == 200
    assert retired.json()["data"]["status"] == "retired"

    jobs = _request(app, "GET", "/api/v1/admin/jobs").json()["data"]
    audits = _request(app, "GET", "/api/v1/admin/audit-log").json()["data"]
    assert {item["status"] for item in jobs if item["name"].startswith("model-")} == {
        "failed",
        "succeeded",
    }
    assert len([item for item in jobs if item["name"].startswith("model-")]) == 4
    assert {item["action"] for item in audits} == {
        "model.train",
        "model.promote",
        "model.retire",
    }

    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(text("UPDATE ml.model_action_audits SET action = 'model.train'"))
    engine.dispose()


def _build_candidate(
    engine: Engine,
    artifact_root: Path,
    clock: FixedClock,
    *,
    promotable: bool,
    artifact_payload: bytes,
) -> tuple[ModelVersion, EvaluationReport]:
    dataset = _dataset(engine)
    calibrator_fingerprint = hashlib.sha256(artifact_payload).hexdigest()
    calibrator_id, benchmark_id, baseline_ids = _seed_prerequisites(
        engine,
        dataset.dataset_id,
        promotable=promotable,
        calibrator_fingerprint=calibrator_fingerprint,
    )
    plan, calibrator = _calibrator(
        dataset_id=dataset.dataset_id,
        calibrator_id=calibrator_id,
        benchmark_id=benchmark_id,
    )
    calibrator = replace(calibrator, artifact_fingerprint=calibrator_fingerprint)
    uncertainty = UncertaintyArtifactBuilder(code_commit="abcdef1", clock=clock).build(calibrator)
    evaluation = EvaluationReportBuilder(
        code_commit="abcdef1",
        parameters=EvaluationReportParameters(calibration_bins=5, minimum_segment_samples=2),
    ).build(plan, calibrator=calibrator, uncertainty=uncertainty)
    registry = ModelRegistry(
        engine=engine,
        artifacts=ModelArtifactStore(FilesystemObjectStore(artifact_root)),
        clock=clock,
    )
    candidate = registry.register(
        ModelRegistration(
            algorithm="gradient_boosting",
            hyperparameters=MappingProxyType({"seed": 42}),
            registered_by="trainer",
            reason="validated API candidate",
            code_commit="abcdef1",
        ),
        evaluation=evaluation,
        uncertainty=uncertainty,
        artifact_payload=artifact_payload,
    )
    assert len(baseline_ids) == 3
    return candidate, evaluation


def _seed_prerequisites(
    engine: Engine,
    dataset_id: UUID,
    *,
    promotable: bool,
    calibrator_fingerprint: str,
) -> tuple[UUID, UUID, tuple[UUID, ...]]:
    baselines = cast(Table, BaselineRunRow.__table__)
    benchmarks = cast(Table, TabularBenchmarkRunRow.__table__)
    calibrators = cast(Table, CalibratorArtifactRow.__table__)
    baseline_ids = tuple(uuid4() for _ in range(3))
    names = ("competition_prior", "recent_form", "rating")
    benchmark_id = uuid4()
    calibrator_id = uuid4()
    walk_forward_fingerprint = uuid4().hex * 2
    gate = _gate_document(baseline_ids, promotable=promotable)
    with engine.begin() as connection:
        for index, (baseline_id, name) in enumerate(zip(baseline_ids, names, strict=True)):
            connection.execute(
                insert(baselines).values(
                    id=baseline_id,
                    dataset_id=dataset_id,
                    artifact_id=None,
                    market="game_winner",
                    baseline_name=name,
                    baseline_version="api-test-v1",
                    evaluation_split="oof_validation",
                    walk_forward_fingerprint=uuid4().hex * 2,
                    parameters={},
                    metrics={
                        "brier_score": str(Decimal("0.20") + Decimal(index) / 100),
                        "calibration": {"ece": str(Decimal("0.10") + Decimal(index) / 100)},
                        "log_loss": str(Decimal("0.41") + Decimal(index) / 100),
                    },
                    prediction_count=2,
                    predictions_fingerprint=uuid4().hex * 2,
                    run_fingerprint=uuid4().hex * 2,
                    code_commit="abcdef1",
                    created_at=NOW,
                )
            )
        connection.execute(
            insert(benchmarks).values(
                id=benchmark_id,
                dataset_id=dataset_id,
                market="game_winner",
                benchmark_version="api-test-v1",
                walk_forward_fingerprint=walk_forward_fingerprint,
                feature_spec={},
                candidate_evaluations={},
                candidate_count=2,
                selected_candidate="gradient_boosting",
                baseline_run_ids=[str(value) for value in baseline_ids],
                promotion_gate=gate,
                promotable=promotable,
                seed=42,
                predictions_per_candidate=2,
                predictions_fingerprint=uuid4().hex * 2,
                run_fingerprint=uuid4().hex * 2,
                code_commit="abcdef1",
                created_at=NOW,
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
                calibrator_version="api-test-v1",
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
                artifact_fingerprint=calibrator_fingerprint,
                code_commit="abcdef1",
                created_at=NOW,
            )
        )
    return calibrator_id, benchmark_id, baseline_ids


def _gate_document(
    baseline_ids: tuple[UUID, ...],
    *,
    promotable: bool,
) -> dict[str, object]:
    names = ("competition_prior", "recent_form", "rating")
    comparisons = [
        {
            "baseline_name": name,
            "baseline_run_id": str(baseline_id),
            "calibration_ece_gain": "0.01" if promotable else "-0.01",
            "log_loss_gain": "0.02" if promotable else "-0.02",
            "passed": promotable,
            "worst_fold_log_loss_gain": "0.01" if promotable else "-0.01",
        }
        for baseline_id, name in zip(baseline_ids, names, strict=True)
    ]
    return {
        "comparisons": comparisons,
        "failures": [] if promotable else ["BASELINE_NOT_BEATEN:rating"],
        "policy_version": "complex-model-promotion-v1",
        "promotable": promotable,
    }
