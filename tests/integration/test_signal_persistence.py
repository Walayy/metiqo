"""Signaux de value reproductibles et physiquement append-only."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import Engine, Table, create_engine, select, text
from sqlalchemy.exc import DBAPIError

from metiquo.contracts import Event
from metiquo.contracts.enums import (
    AbstentionReason,
    FreshnessStatus,
    GameTitle,
    SelectionType,
    ValueGrade,
)
from metiquo.db.pricing_models import SignalRecord
from metiquo.features import FeatureDatasetBuilder
from metiquo.foundation.finance import DecimalOdds, Probability
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.mapping import PostgresEventMatchingService
from metiquo.models import (
    CHAMPION,
    EvaluationReportBuilder,
    EvaluationReportParameters,
    ModelArtifactStore,
    ModelRegistration,
    ModelRegistry,
    UncertaintyArtifactBuilder,
)
from metiquo.models.predictions import (
    PrematchPredictionRequest,
    PrematchPredictionService,
    RegistryChampionRuntimeLoader,
    StoredPrematchPrediction,
)
from metiquo.pricing import (
    MarketQuote,
    NoVigMarket,
    NoVigPricingEngine,
    PostgresSignalRepository,
    PostgresValuePolicyRepository,
    SignalPublication,
    ValueDecision,
    ValueDecisionEngine,
    ValuePricingEngine,
    ValuePricingInput,
)
from metiquo.providers import ManualImportOddsProvider
from metiquo.repositories import PostgresCanonicalRepository
from metiquo.services.odds_capture import OddsCaptureService, OddsCaptureSource
from tests.integration.test_migrations import alembic_config
from tests.integration.test_model_registry import _calibrator, _database_prerequisites
from tests.integration.test_prematch_predictions import (
    _FixedDecoder,
    _historical_dataset,
    _UncertaintySource,
)
from tests.integration.test_value_policy import _policy


@pytest.mark.integration
def test_signals_keep_exact_inputs_reproduce_and_reject_mutation(
    postgresql_url: str,
    tmp_path: Path,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = _historical_dataset(engine)
    event = next(
        item
        for item in PostgresCanonicalRepository(engine).list()
        if item.starts_at > dataset.cutoff_max
    )
    cutoff = event.starts_at - timedelta(hours=1)
    registered_at = cutoff - timedelta(hours=1)
    prediction = _prediction(
        engine,
        dataset.dataset_id,
        dataset.dataset,
        event.event_id,
        cutoff,
        registered_at,
        tmp_path,
    )

    captured_at = cutoff + timedelta(minutes=20)
    provider_code = f"signal-{uuid4()}"
    provider = ManualImportOddsProvider(
        provider_code,
        clock=FixedClock(UtcInstant(captured_at)),
    )
    imported = provider.import_document(
        json.dumps(
            [_manual_row(provider_code, event, captured_at)],
            separators=(",", ":"),
        ).encode(),
        document_format="json",
    )
    provider_event = provider.list_events(
        cutoff,
        event.starts_at + timedelta(hours=1),
        GameTitle.LEAGUE_OF_LEGENDS,
    )[0]
    capture = OddsCaptureService(
        engine,
        FixedClock(UtcInstant(captured_at + timedelta(minutes=1))),
    ).capture_event(
        provider,
        provider_event,
        OddsCaptureSource("manual_import", "Signal integration", imported.import_key),
    )
    mapping = PostgresEventMatchingService(
        engine,
        FixedClock(UtcInstant(captured_at + timedelta(minutes=2))),
    ).match_event(provider_code, provider_event, (event,))
    assert mapping.selected_event_id == event.event_id
    assert mapping.attempt_id is not None

    policy = _policy(f"signal-policy-{uuid4().hex}", Decimal("0.03"))
    PostgresValuePolicyRepository(
        engine,
        FixedClock(UtcInstant(captured_at + timedelta(minutes=3))),
    ).register(policy, actor="pricing-integration", reason="Reproduction proof")
    no_vig = NoVigPricingEngine().calculate(
        NoVigMarket(
            quotes=(
                MarketQuote(SelectionType.TEAM_A, DecimalOdds(Decimal("1.80"))),
                MarketQuote(SelectionType.TEAM_B, DecimalOdds(Decimal("2.20"))),
            ),
            expected_selections=frozenset((SelectionType.TEAM_A, SelectionType.TEAM_B)),
        )
    )
    priced = ValuePricingEngine().calculate(
        ValuePricingInput(
            no_vig.quote(SelectionType.TEAM_A),
            Probability(prediction.team_a_probability),
            Probability(prediction.team_a_low),
        )
    )
    computed_at = captured_at + timedelta(minutes=10)
    repository = PostgresSignalRepository(engine, FixedClock(UtcInstant(computed_at)))
    publication = SignalPublication(
        odds_snapshot_id=capture.inserted_snapshot_ids[0],
        prediction_id=prediction.prediction_id,
        event_mapping_attempt_id=mapping.attempt_id,
        selection=SelectionType.TEAM_A,
        grade=ValueGrade.VALUE,
        decision=ValueDecision(policy.version, priced, None),
        mapping_confidence=Probability(mapping.candidates[0].total_score),
        source_freshness=FreshnessStatus.FRESH,
        odds_age_seconds=600,
        no_vig_policy_version=no_vig.strategy_version,
    )

    stored = repository.append(publication)
    replay = repository.append(publication)

    assert replay == stored == repository.get(stored.signal_id)
    assert repository.reproduce(stored.signal_id) == stored
    assert stored.odds_snapshot_id == capture.inserted_snapshot_ids[0]
    assert stored.prediction_id == prediction.prediction_id
    assert stored.event_mapping_attempt_id == mapping.attempt_id
    assert stored.policy_version == policy.version
    assert stored.offered_odds == Decimal("1.8000000000000000000000000000")
    assert stored.value_computed is True
    assert stored.pricing_policy_version == priced.policy_version
    assert stored.no_vig_policy_version == no_vig.strategy_version
    assert stored.grade is ValueGrade.VALUE
    assert stored.abstention_reasons == ()
    assert len(stored.signal_fingerprint) == 64

    blocked_repository = PostgresSignalRepository(
        engine,
        FixedClock(UtcInstant(computed_at + timedelta(minutes=1))),
    )
    blocked = blocked_repository.append(
        SignalPublication(
            odds_snapshot_id=capture.inserted_snapshot_ids[0],
            prediction_id=prediction.prediction_id,
            event_mapping_attempt_id=mapping.attempt_id,
            selection=SelectionType.TEAM_A,
            grade=ValueGrade.BLOCKED,
            decision=ValueDecisionEngine().abstain_without_value(
                policy.version,
                reasons=(AbstentionReason.ODDS_STALE,),
            ),
            mapping_confidence=Probability(mapping.candidates[0].total_score),
            source_freshness=FreshnessStatus.STALE,
            odds_age_seconds=660,
        )
    )
    assert blocked.value_computed is False
    assert blocked.abstention_reasons == (AbstentionReason.ODDS_STALE,)
    assert repository.list_for_prediction(prediction.prediction_id) == (stored, blocked)

    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE signals.signals SET grade = 'WATCH' WHERE id = :id"),
            {"id": stored.signal_id},
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("DELETE FROM signals.signals WHERE id = :id"),
            {"id": blocked.signal_id},
        )

    signals = cast(Table, SignalRecord.__table__)
    with engine.connect() as connection:
        forged = dict(
            connection.execute(select(signals).where(signals.c.id == stored.signal_id))
            .mappings()
            .one()
        )
    forged.update(
        id=uuid4(),
        offered_odds=Decimal("1.81"),
        signal_fingerprint="a" * 64,
    )
    with (
        pytest.raises(DBAPIError, match="does not match stored inputs"),
        engine.begin() as connection,
    ):
        connection.execute(signals.insert().values(**forged))
    engine.dispose()


def _prediction(
    engine: Engine,
    dataset_id: UUID,
    dataset_name: str,
    event_id: UUID,
    cutoff: datetime,
    registered_at: datetime,
    tmp_path: Path,
) -> StoredPrematchPrediction:
    calibrator_id, benchmark_id = _database_prerequisites(engine, dataset_id)
    plan, calibrator = _calibrator(
        dataset_id=dataset_id,
        calibrator_id=calibrator_id,
        benchmark_id=benchmark_id,
    )
    uncertainty = UncertaintyArtifactBuilder(
        code_commit="abcdef1",
        clock=FixedClock(UtcInstant(registered_at)),
    ).build(calibrator)
    evaluation = EvaluationReportBuilder(
        code_commit="abcdef1",
        parameters=EvaluationReportParameters(calibration_bins=5, minimum_segment_samples=2),
    ).build(plan, calibrator=calibrator, uncertainty=uncertainty)
    registry = ModelRegistry(
        engine=engine,
        artifacts=ModelArtifactStore(FilesystemObjectStore(tmp_path)),
        clock=FixedClock(UtcInstant(registered_at)),
    )
    registry.register(
        ModelRegistration(
            algorithm="fixed_test_model",
            hyperparameters=MappingProxyType({"probability": "0.60"}),
            status=CHAMPION,
            registered_by="ml-reviewer",
            reason="Signal integration champion",
            code_commit="abcdef1",
        ),
        evaluation=evaluation,
        uncertainty=uncertainty,
        artifact_payload=b"fixed-model:0.60",
    )
    return PrematchPredictionService(
        engine=engine,
        features=FeatureDatasetBuilder(
            engine=engine,
            code_commit="abcdef1",
            dataset=dataset_name,
        ),
        runtime=RegistryChampionRuntimeLoader(
            registry=registry,
            uncertainty_artifacts=_UncertaintySource(uncertainty),
            decoder=_FixedDecoder(),
        ),
        code_commit="abcdef1",
        clock=FixedClock(UtcInstant(cutoff + timedelta(minutes=10))),
    ).predict(PrematchPredictionRequest(event_id=event_id, cutoff_at=cutoff))


def _manual_row(
    provider_code: str,
    event: Event,
    captured_at: datetime,
) -> dict[str, object]:
    return {
        "best_of": event.best_of,
        "captured_at": captured_at.isoformat(),
        "competition": event.competition,
        "decimal_odds": "1.80",
        "event_status": "scheduled",
        "game_title": "lol",
        "line": None,
        "market_label": "Match Winner",
        "market_status": "open",
        "market_type": "MATCH_WINNER",
        "participant_a": event.team_a,
        "participant_b": event.team_b,
        "period": "SERIES",
        "unit": "winner",
        "provenance_reference": "manual:signal:team-a:v1",
        "provider": provider_code,
        "provider_event_id": "signal-event",
        "provider_market_id": "signal-market",
        "provider_selection_id": "signal-team-a",
        "selection": "TEAM_A",
        "selection_label": event.team_a,
        "settlement_rules_version": "match-winner-v1",
        "remake_policy": "void",
        "forfeit_policy": "settle",
        "cancelled_policy": "void",
        "starts_at": event.starts_at.isoformat(),
        "timestamp_reliable": True,
    }
