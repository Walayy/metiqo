"""Gate P6 : capture, mapping, prédiction et décision sans grade fourni."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import Engine, create_engine, func, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from metiquo.api.app import create_app
from metiquo.canonical.capabilities import (
    DEFAULT_CAPABILITY_DEFINITIONS,
    CapabilityRegistry,
    MarketGateEvidence,
)
from metiquo.contracts import Event
from metiquo.contracts.enums import AbstentionReason, GameTitle, ValueGrade
from metiquo.db.feature_models import FeatureSnapshot
from metiquo.db.pricing_models import SignalRecord, ValueEvaluationRecord
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.mapping import PostgresEventMatchingService, PostgresMarketMappingService
from metiquo.models.predictions import StoredPrematchPrediction
from metiquo.pricing import (
    PostgresSignalRepository,
    PostgresValuePolicyRepository,
    SignalIntegrityError,
)
from metiquo.providers import ManualImportOddsProvider
from metiquo.repositories import PostgresCanonicalRepository
from metiquo.services.odds_capture import OddsCaptureService, OddsCaptureSource
from metiquo.services.odds_mapping import PostgresResolvedOddsGate, ResolvedOddsPipeline
from metiquo.services.value_pipeline import PostgresValuePipeline, ValueEvaluationRequest
from tests.integration import test_canonical_rosters as roster_fixture
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _ReadyProbe, _request, _settings
from tests.integration.test_prematch_predictions import _historical_dataset
from tests.integration.test_resolved_odds_gate import _rules
from tests.integration.test_signal_persistence import _manual_row, _prediction
from tests.integration.test_value_policy import _policy

_SLA = timedelta(days=14)


@pytest.mark.integration
@pytest.mark.parametrize("context", [True], indirect=True)
def test_model_and_provider_team_orders_are_resolved_by_identity(context: _Context) -> None:
    now = context.captured_at + timedelta(seconds=10)
    pipeline = PostgresValuePipeline(
        context.engine, source_sla=_SLA, clock=FixedClock(UtcInstant(now))
    )
    for inverted, expected_team, expected_probability in (
        (False, context.prediction.team_a_id, context.prediction.team_a_probability),
        (True, context.prediction.team_b_id, context.prediction.team_b_probability),
    ):
        result = pipeline.evaluate(_capture(context, inverted=inverted))
        assert result.signal is not None and result.grade is ValueGrade.VALUE
        assert result.signal.selected_team_id == expected_team
        assert result.signal.model_probability == expected_probability
        assert (
            PostgresSignalRepository(context.engine).reproduce(result.signal.signal_id)
            == result.signal
        )
    assert result.signal is not None
    with Session(context.engine) as session:
        stored = session.get(SignalRecord, result.signal.signal_id)
        assert stored is not None
        forged = {
            column.name: getattr(stored, column.name) for column in SignalRecord.__table__.columns
        }
    forged.update(
        id=uuid4(), selected_team_id=context.prediction.team_a_id, signal_fingerprint="f" * 64
    )
    with (
        pytest.raises(DBAPIError, match="selected team identity"),
        context.engine.begin() as connection,
    ):
        connection.execute(insert(SignalRecord).values(**forged))


@dataclass(frozen=True)
class _Context:
    engine: Engine
    event: Event
    prediction: StoredPrematchPrediction
    captured_at: datetime
    policy_version: str


@pytest.fixture
def context(
    postgresql_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Iterator[_Context]:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    # La fixture P6 annonce explicitement BO1 et une connaissance source antérieure.
    monkeypatch.setattr(roster_fixture, "_NOW", datetime(2026, 8, 1, 10, tzinfo=UTC))
    game_rows = roster_fixture._game_rows

    def bo1_rows(
        game_id: str, suffix: str, event_date: str, *, changed_top: bool
    ) -> list[dict[str, str]]:
        return [
            {**row, "bestof": "1", "game": "1"}
            for row in game_rows(game_id, suffix, event_date, changed_top=changed_top)
        ]

    monkeypatch.setattr(roster_fixture, "_game_rows", bo1_rows)
    dataset = _historical_dataset(engine)
    event = next(
        item
        for item in PostgresCanonicalRepository(engine).list()
        if item.starts_at > dataset.cutoff_max
    )
    cutoff = event.starts_at - timedelta(hours=1)
    prediction = _prediction(
        engine,
        dataset.dataset_id,
        dataset.dataset,
        event.event_id,
        cutoff,
        cutoff - timedelta(hours=1),
        tmp_path,
        reverse_teams=bool(getattr(request, "param", False)),
    )
    captured = cutoff + timedelta(minutes=20)
    policy = _policy(f"p6-{uuid4().hex}", Decimal("0.03"))
    PostgresValuePolicyRepository(engine, FixedClock(UtcInstant(captured))).register(
        policy,
        actor="p6-fixture",
        reason="Gate thresholds fixed before evaluation",
    )
    with Session(engine) as session:
        feature = session.get(FeatureSnapshot, prediction.feature_snapshot_id)
        assert feature is not None
        snapshot_id = feature.target_oe_snapshot_id
    CapabilityRegistry(
        engine=engine,
        clock=FixedClock(UtcInstant(captured)),
        definitions=tuple(
            replace(item, minimum_sample_size=1, threshold_version="p6-fixture-v1")
            for item in DEFAULT_CAPABILITY_DEFINITIONS
        ),
    ).evaluate_snapshot(
        snapshot_id=snapshot_id,
        market_evidence={
            "market.match_winner": MarketGateEvidence(True, True, True, True, True),
        },
    )
    try:
        yield _Context(engine, event, prediction, captured, policy.version)
    finally:
        engine.dispose()


def _capture(
    context: _Context,
    *,
    suspended: bool = False,
    ambiguous: bool = False,
    complete: bool = True,
    captured_at: datetime | None = None,
    odds_b: str = "8.00",
    inverted: bool = False,
) -> ValueEvaluationRequest:
    captured = captured_at or context.captured_at
    clock = FixedClock(UtcInstant(captured + timedelta(seconds=1)))
    code = f"p6-{uuid4().hex}"
    provider = ManualImportOddsProvider(code, clock=clock)
    common = _manual_row(code, context.event, captured)
    if inverted:
        common["participant_a"], common["participant_b"] = (
            common["participant_b"],
            common["participant_a"],
        )
        common["selection_label"] = context.event.team_b
    common["market_status"] = "suspended" if suspended else "open"
    if ambiguous:
        common["competition"] = "Unknown fixture competition"
    rows = [dict(common, decimal_odds="1.10")]
    if complete:
        rows.append(
            dict(
                common,
                provider_selection_id="signal-team-b",
                selection="TEAM_B",
                selection_label=context.event.team_a if inverted else context.event.team_b,
                decimal_odds=odds_b,
                provenance_reference="manual:p6:team-b",
            )
        )
    imported = provider.import_document(json.dumps(rows).encode(), document_format="json")
    provider_event = provider.list_events(
        context.event.starts_at - timedelta(hours=1),
        context.event.starts_at + timedelta(hours=1),
        GameTitle.LEAGUE_OF_LEGENDS,
    )[0]
    markets = PostgresMarketMappingService(context.engine, clock)
    markets.register_rules(_rules())
    gate = ResolvedOddsPipeline(
        OddsCaptureService(context.engine, clock),
        PostgresEventMatchingService(context.engine, clock),
        markets,
        PostgresResolvedOddsGate(context.engine),
    ).process(
        provider,
        provider_event,
        OddsCaptureSource("manual_import", "P6 explicit test fixture", imported.import_key),
        (context.event,),
    )
    assert gate.event_mapping.attempt_id is not None
    assert gate.market_mappings[0].attempt_id is not None
    with Session(context.engine) as session:
        from metiquo.db.odds_models import OddsSnapshotRecord, ProviderOddsSelection

        snapshot_id = session.scalar(
            select(OddsSnapshotRecord.id)
            .join(
                ProviderOddsSelection, ProviderOddsSelection.id == OddsSnapshotRecord.selection_id
            )
            .where(
                OddsSnapshotRecord.id.in_(gate.capture.inserted_snapshot_ids),
                ProviderOddsSelection.selection_type == ("TEAM_B" if complete else "TEAM_A"),
            )
        )
    assert snapshot_id is not None
    return ValueEvaluationRequest(
        snapshot_id,
        gate.event_mapping.attempt_id,
        gate.market_mappings[0].attempt_id,
        context.policy_version,
        None if ambiguous else context.prediction.prediction_id,
    )


@pytest.mark.integration
def test_value_gate_outsider_replay_and_real_api(
    context: _Context, postgresql_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    from metiquo.foundation.observability import JsonFormatter

    caplog.handler.setFormatter(JsonFormatter())
    caplog.set_level("INFO", logger="metiquo.pricing")
    request = _capture(context)
    now = context.captured_at + timedelta(seconds=10)
    clock = FixedClock(UtcInstant(now))
    pipeline = PostgresValuePipeline(context.engine, source_sla=_SLA, clock=clock)
    result = pipeline.evaluate(request)
    assert result.grade is ValueGrade.VALUE
    assert '"model_version":' in caplog.text
    assert '"snapshot_id":' in caplog.text
    assert '"duration_ms":' in caplog.text
    assert result.reasons == ()
    assert result == pipeline.evaluate(request)
    signal = result.signal
    assert signal is not None
    assert signal.model_probability == Decimal("0.4")
    assert signal.offered_odds == Decimal("8")
    assert signal.expected_value == Decimal("2.2")
    assert signal.model_probability_low == Decimal("0.154268")
    assert signal.conservative_expected_value == Decimal("0.234144")
    assert signal.fair_odds == Decimal("2.5")
    assert signal.no_vig_probability is not None
    assert abs(signal.no_vig_probability - Decimal(11) / Decimal(91)) < Decimal("1E-27")
    assert PostgresSignalRepository(context.engine).reproduce(signal.signal_id) == signal
    with Session(context.engine) as session:
        evidence = session.get(ValueEvaluationRecord, result.evaluation_id)
        assert evidence is not None
        quotes = evidence.evidence["quoteSnapshots"]
        assert isinstance(quotes, list) and len(quotes) == 2
        assert session.scalar(select(func.count()).select_from(ValueEvaluationRecord)) == 1
    app = create_app(
        settings=_settings(postgresql_url, "real"), readiness_probe=_ReadyProbe(), clock=clock
    )
    detail = _request(app, f"/api/v1/opportunities/{signal.signal_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["value"]["grade"] == "VALUE"
    assert detail.json()["data"]["meta"]["dataMode"] == "real"
    app.state.real_admin_engine.dispose()
    for statement in (
        "UPDATE signals.value_evaluations SET grade='NO_EDGE' WHERE id=:id",
        "DELETE FROM signals.value_evaluations WHERE id=:id",
    ):
        with pytest.raises(DBAPIError, match="append-only"), context.engine.begin() as connection:
            connection.execute(text(statement), {"id": result.evaluation_id})


@pytest.mark.integration
@pytest.mark.parametrize("case", ("stale", "suspended", "ambiguous", "incomplete", "no_edge"))
def test_value_gate_refusals_are_persisted(
    context: _Context, postgresql_url: str, case: str
) -> None:
    request = _capture(
        context,
        suspended=case == "suspended",
        ambiguous=case == "ambiguous",
        complete=case != "incomplete",
        odds_b="1.20" if case == "no_edge" else "8.00",
    )
    now = context.captured_at + timedelta(seconds=91 if case == "stale" else 10)
    clock = FixedClock(UtcInstant(now))
    result = PostgresValuePipeline(context.engine, source_sla=_SLA, clock=clock).evaluate(request)
    assert result.grade is (ValueGrade.NO_EDGE if case == "no_edge" else ValueGrade.BLOCKED)
    expected = {
        "stale": AbstentionReason.ODDS_STALE,
        "suspended": AbstentionReason.MARKET_SUSPENDED,
        "ambiguous": AbstentionReason.EVENT_MAPPING_AMBIGUOUS,
        "incomplete": AbstentionReason.MARKET_RULES_UNKNOWN,
        "no_edge": AbstentionReason.EDGE_TOO_SMALL,
    }[case]
    assert expected in result.reasons
    with Session(context.engine) as session:
        record = session.get(ValueEvaluationRecord, result.evaluation_id)
        assert record is not None and expected.value in record.abstention_reasons
    if case == "ambiguous":
        assert result.signal is None
    elif case != "incomplete":
        assert result.signal is not None
        app = create_app(
            settings=_settings(postgresql_url, "real"), readiness_probe=_ReadyProbe(), clock=clock
        )
        response = _request(app, f"/api/v1/opportunities/{result.signal.signal_id}")
        assert response.status_code == 200
        assert not response.json()["data"]["quality"]["publishable"]
        app.state.real_admin_engine.dispose()


@pytest.mark.integration
def test_value_gate_rejects_temporal_leakage_and_rolls_back_publication(context: _Context) -> None:
    request = _capture(context, captured_at=context.prediction.cutoff_at - timedelta(seconds=1))
    clock = FixedClock(UtcInstant(context.captured_at + timedelta(seconds=10)))
    pipeline = PostgresValuePipeline(context.engine, source_sla=_SLA, clock=clock)
    with pytest.raises(SignalIntegrityError, match="cutoff"):
        pipeline.evaluate(request)
    valid = _capture(context)
    with context.engine.begin() as connection:
        connection.execute(
            text("""
            CREATE FUNCTION signals.p6_test_failure() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'p6 injected failure'; END $$;
            CREATE TRIGGER p6_test_failure BEFORE INSERT ON signals.value_evaluations
            FOR EACH ROW EXECUTE FUNCTION signals.p6_test_failure();
        """)
        )
    try:
        with pytest.raises(DBAPIError, match="p6 injected failure"):
            pipeline.evaluate(valid)
        with Session(context.engine) as session:
            assert session.scalar(select(func.count()).select_from(SignalRecord)) == 0
            assert session.scalar(select(func.count()).select_from(ValueEvaluationRecord)) == 0
    finally:
        with context.engine.begin() as connection:
            connection.execute(text("DROP TRIGGER p6_test_failure ON signals.value_evaluations"))
            connection.execute(text("DROP FUNCTION signals.p6_test_failure()"))


@pytest.mark.integration
def test_value_gate_uses_mapping_orientation(context: _Context) -> None:
    request = _capture(context, inverted=True)
    result = PostgresValuePipeline(
        context.engine,
        source_sla=_SLA,
        clock=FixedClock(UtcInstant(context.captured_at + timedelta(seconds=10))),
    ).evaluate(request)
    assert result.signal is not None
    assert result.signal.selection.value == "TEAM_A"
    assert result.signal.model_probability == context.prediction.team_a_probability
    assert result.grade is ValueGrade.VALUE


@pytest.mark.integration
def test_value_gate_reads_source_freshness_instead_of_accepting_it(context: _Context) -> None:
    request = _capture(context)
    result = PostgresValuePipeline(
        context.engine,
        source_sla=timedelta(hours=1),
        clock=FixedClock(UtcInstant(context.captured_at + timedelta(seconds=10))),
    ).evaluate(request)
    assert result.grade is ValueGrade.BLOCKED
    assert AbstentionReason.SOURCE_STALE in result.reasons
    assert result.signal is not None and result.signal.value_computed


@pytest.mark.integration
def test_value_gate_rechecks_capabilities(context: _Context) -> None:
    request = _capture(context)
    with Session(context.engine) as session:
        feature = session.get(FeatureSnapshot, context.prediction.feature_snapshot_id)
        assert feature is not None
        snapshot_id = feature.target_oe_snapshot_id
    CapabilityRegistry(
        engine=context.engine,
        clock=FixedClock(UtcInstant(context.captured_at + timedelta(seconds=2))),
        definitions=tuple(
            replace(item, minimum_sample_size=1, threshold_version="p6-fixture-v1")
            for item in DEFAULT_CAPABILITY_DEFINITIONS
        ),
    ).evaluate_snapshot(
        snapshot_id=snapshot_id,
        market_evidence={
            "market.match_winner": MarketGateEvidence(True, False, True, True, True),
        },
    )
    result = PostgresValuePipeline(
        context.engine,
        source_sla=_SLA,
        clock=FixedClock(UtcInstant(context.captured_at + timedelta(seconds=10))),
    ).evaluate(request)
    assert result.grade is ValueGrade.BLOCKED
    assert AbstentionReason.CAPABILITY_DISABLED in result.reasons
