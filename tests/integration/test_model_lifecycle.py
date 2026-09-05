"""Promotion manuelle, shadow prediction et rollback atomique."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import cast

import pytest
from alembic import command
from sqlalchemy import Table, create_engine, select, text
from sqlalchemy.exc import DBAPIError

from metiquo.db.ml_models import ShadowPrediction as ShadowPredictionRow
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.models import (
    BLOCKED,
    CANDIDATE,
    CHAMPION,
    COMPETITION_PRIOR,
    RATING,
    RECENT_FORM,
    RETIRED,
    EvaluationReport,
    EvaluationReportBuilder,
    EvaluationReportParameters,
    ModelArtifactStore,
    ModelLifecycle,
    ModelRegistration,
    ModelRegistry,
    ModelVersion,
    PromotionEvidence,
    UncertaintyArtifact,
    UncertaintyArtifactBuilder,
)
from tests.integration.test_migrations import alembic_config
from tests.integration.test_model_registry import (
    _calibrator,
    _database_prerequisites,
    _dataset,
)

_OCCURRED_AT = datetime(2026, 9, 7, 4, 0, tzinfo=UTC)


@pytest.mark.integration
def test_manual_promotion_shadow_and_immediate_rollback_preserve_versions(
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
        clock=FixedClock(UtcInstant(_OCCURRED_AT)),
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
        clock=FixedClock(UtcInstant(_OCCURRED_AT)),
    )
    first = _register_candidate(
        registry,
        algorithm="gradient_boosting",
        code_commit="abcdef1",
        payload=b"model-v1",
        evaluation=evaluation,
        uncertainty=uncertainty,
    )
    challenger = _register_candidate(
        registry,
        algorithm="hist_gradient_boosting",
        code_commit="abcdef2",
        payload=b"model-v2",
        evaluation=evaluation,
        uncertainty=uncertainty,
    )
    blocked = _register_candidate(
        registry,
        algorithm="blocked_candidate",
        code_commit="abcdef3",
        payload=b"model-blocked",
        evaluation=evaluation,
        uncertainty=uncertainty,
    )
    lifecycle = ModelLifecycle(
        engine=engine,
        clock=FixedClock(UtcInstant(_OCCURRED_AT)),
    )
    evidence = PromotionEvidence(
        evaluation_report_fingerprint=evaluation.report_fingerprint,
        baseline_log_loss_deltas=MappingProxyType(
            {
                COMPETITION_PRIOR: Decimal("0.05"),
                RECENT_FORM: Decimal("0.04"),
                RATING: Decimal("0.03"),
            }
        ),
        metric_basis=("log_loss", "calibration_ece", "interval_coverage"),
        manual_approval_reference="review/ml-011/initial",
    )

    initial = lifecycle.promote(
        first.model_version_id,
        actor="ml-reviewer",
        reason="initial champion after review",
        evidence=evidence,
    )
    assert initial.status == CHAMPION
    assert initial.previous_champion_id is None
    stored_first = registry.get(first.model_version_id)
    stored_challenger = registry.get(challenger.model_version_id)
    assert stored_first is not None and stored_first.status == CHAMPION
    assert stored_challenger is not None and stored_challenger.status == CANDIDATE

    source_event = dataset.examples[0]
    shadow = lifecycle.record_shadow(
        challenger.model_version_id,
        event_id=source_event.event_id,
        cutoff_at=source_event.cutoff_at,
        predicted_at=source_event.cutoff_at + timedelta(minutes=1),
        probability=Decimal("0.61"),
        p_low=Decimal("0.53"),
        p_high=Decimal("0.69"),
        context_fingerprint="d" * 64,
    )
    promoted = lifecycle.promote(
        challenger.model_version_id,
        actor="ml-reviewer",
        reason="challenger beats all baselines on several metrics",
        evidence=PromotionEvidence(
            evaluation_report_fingerprint=evaluation.report_fingerprint,
            baseline_log_loss_deltas=evidence.baseline_log_loss_deltas,
            metric_basis=evidence.metric_basis,
            manual_approval_reference="review/ml-011/challenger",
        ),
    )
    assert promoted.previous_champion_id == first.model_version_id
    stored_first = registry.get(first.model_version_id)
    current_champion = registry.current_champion()
    assert stored_first is not None and stored_first.status == RETIRED
    assert current_champion is not None
    assert current_champion.model_version_id == challenger.model_version_id

    rolled_back = lifecycle.rollback(
        first.model_version_id,
        actor="on-call-reviewer",
        reason="production drift detected",
    )
    assert rolled_back.previous_champion_id == challenger.model_version_id
    current_champion = registry.current_champion()
    stored_challenger = registry.get(challenger.model_version_id)
    assert current_champion is not None
    assert current_champion.model_version_id == first.model_version_id
    assert stored_challenger is not None and stored_challenger.status == RETIRED

    shadows = cast(Table, ShadowPredictionRow.__table__)
    with engine.connect() as connection:
        stored_shadow = (
            connection.execute(select(shadows).where(shadows.c.id == shadow.prediction_id))
            .mappings()
            .one()
        )
    assert stored_shadow["model_version_id"] == challenger.model_version_id
    assert stored_shadow["champion_model_version_id"] == first.model_version_id
    assert stored_shadow["probability"] == Decimal("0.61000000")

    blocked_result = lifecycle.block(
        blocked.model_version_id,
        actor="ml-reviewer",
        reason="calibration guard failed",
    )
    assert blocked_result.status == BLOCKED
    stored_blocked = registry.get(blocked.model_version_id)
    assert stored_blocked is not None and stored_blocked.status == BLOCKED
    assert {item.action for item in lifecycle.status_events(first.model_version_id)} == {
        "promote",
        "retire_for_promotion",
        "rollback",
    }
    with pytest.raises(ValueError, match="probabiliste primaire"):
        PromotionEvidence(
            evaluation_report_fingerprint=evaluation.report_fingerprint,
            baseline_log_loss_deltas=evidence.baseline_log_loss_deltas,
            metric_basis=("accuracy", "roc_auc"),
            manual_approval_reference="review/invalid",
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE ml.model_status_events SET reason = 'tampered' WHERE id = :id"),
            {"id": initial.event_ids[0]},
        )
    engine.dispose()


def _register_candidate(
    registry: ModelRegistry,
    *,
    algorithm: str,
    code_commit: str,
    payload: bytes,
    evaluation: EvaluationReport,
    uncertainty: UncertaintyArtifact,
) -> ModelVersion:
    return registry.register(
        ModelRegistration(
            algorithm=algorithm,
            hyperparameters=MappingProxyType({"seed": int(code_commit[-1], 16)}),
            registered_by="trainer",
            reason="validated candidate",
            code_commit=code_commit,
        ),
        evaluation=evaluation,
        uncertainty=uncertainty,
        artifact_payload=payload,
    )
