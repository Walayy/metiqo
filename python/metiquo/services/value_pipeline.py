"""Décider et publier la value uniquement depuis les preuves PostgreSQL."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from metiquo.contracts.enums import (
    AbstentionReason as Reason,
)
from metiquo.contracts.enums import (
    FreshnessStatus,
    MarketStatus,
    MarketType,
    ModelStatus,
    SelectionType,
    ValueGrade,
)
from metiquo.db.base import Base
from metiquo.db.core_models import CapabilityEvaluation, Game
from metiquo.db.feature_models import FeatureSnapshot
from metiquo.db.ml_models import ModelVersion, PrematchPrediction
from metiquo.db.odds_models import (
    EventMappingAttempt,
    EventMappingCandidateScore,
    MappingReviewRecord,
    MarketMappingAttempt,
    MarketRulesRecord,
    OddsProviderRecord,
    OddsSnapshotRecord,
    ProviderOddsMarket,
    ProviderOddsSelection,
)
from metiquo.db.pricing_models import ValueEvaluationRecord, ValuePolicyRecord
from metiquo.db.raw_models import Snapshot
from metiquo.foundation.finance import DecimalOdds, Probability
from metiquo.foundation.time import Clock, FixedClock, SystemClock, UtcInstant
from metiquo.ingestion.freshness import (
    FreshnessPolicy,
    FreshnessService,
    PostgresFreshnessRepository,
)
from metiquo.markets.game_winner import GameWinnerMarketPlugin
from metiquo.pricing import (
    MarketQuote,
    NoVigMarket,
    NoVigPricingEngine,
    PostgresSignalRepository,
    SignalIntegrityError,
    SignalPublication,
    ValueAdmissionGate,
    ValueAdmissionInput,
    ValueDecision,
    ValueDecisionEngine,
    ValuePricingEngine,
    ValuePricingInput,
)
from metiquo.pricing.policy import ValueThresholds, value_policy_from_storage
from metiquo.pricing.signal_repository import StoredSignal

VALUE_PIPELINE_VERSION = "value-pipeline-v1"
_PRICE_REASONS = frozenset(
    (
        Reason.EDGE_TOO_SMALL,
        Reason.EXPECTED_VALUE_TOO_SMALL,
        Reason.CONSERVATIVE_EV_NEGATIVE,
        Reason.CONSERVATIVE_EV_TOO_SMALL,
    )
)


@dataclass(frozen=True, slots=True)
class ValueEvaluationRequest:
    """Références d'entrée ; aucun grade, probabilité ou booléen d'admission."""

    odds_snapshot_id: UUID
    event_mapping_attempt_id: UUID
    market_mapping_attempt_id: UUID
    policy_version: str
    prediction_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ValueEvaluation:
    evaluation_id: UUID
    signal: StoredSignal | None
    grade: ValueGrade
    reasons: tuple[Reason, ...]
    computed_at: datetime
    fingerprint: str


class PostgresValuePipeline:
    """Publication atomique du signal et de la preuve complète, refus compris."""

    def __init__(
        self,
        engine: Engine,
        *,
        source_sla: timedelta,
        clock: Clock | None = None,
    ) -> None:
        if source_sla <= timedelta(0):
            raise ValueError("le SLA source doit être positif")
        self.engine = engine
        self.source_sla = source_sla
        self.clock = clock or SystemClock()

    def evaluate(self, request: ValueEvaluationRequest) -> ValueEvaluation:
        now = self.clock.now().value
        with self.engine.begin() as connection, Session(bind=connection) as session:
            return self._evaluate(connection, session, request, now)

    def _evaluate(
        self,
        connection: Connection,
        session: Session,
        request: ValueEvaluationRequest,
        now: datetime,
    ) -> ValueEvaluation:
        odds = _get(session, OddsSnapshotRecord, request.odds_snapshot_id)
        attempt = _get(session, EventMappingAttempt, request.event_mapping_attempt_id)
        mapping = _get(session, MarketMappingAttempt, request.market_mapping_attempt_id)
        market = _get(session, ProviderOddsMarket, odds.market_id)
        provider = _get(session, OddsProviderRecord, odds.provider_id)
        selection = _get(session, ProviderOddsSelection, odds.selection_id)
        if provider.provider_type not in {"manual_import", "licensed_feed"}:
            raise SignalIntegrityError("le parcours réel exige une source de cotes autorisée")
        if attempt.provider_event_id != odds.event_id or mapping.provider_event_id != odds.event_id:
            raise SignalIntegrityError("les mappings doivent référencer l'événement de la cote")
        if mapping.provider_market_id != market.provider_market_id:
            raise SignalIntegrityError("le mapping ne correspond pas au marché de la cote")
        if max(odds.recorded_at, attempt.evaluated_at, mapping.evaluated_at) > now:
            raise SignalIntegrityError("une preuve enregistrée dans le futur est interdite")
        policy_row = session.scalar(
            select(ValuePolicyRecord).where(
                ValuePolicyRecord.version == request.policy_version,
            )
        )
        if policy_row is None or policy_row.created_at > now:
            raise SignalIntegrityError("la politique doit être enregistrée avant la décision")
        policy = value_policy_from_storage(
            version=policy_row.version,
            thresholds=ValueThresholds(
                min_edge=policy_row.min_edge,
                min_ev=policy_row.min_ev,
                min_conservative_ev=policy_row.min_conservative_ev,
                max_odds_age_seconds=policy_row.max_odds_age_seconds,
                min_mapping_confidence=policy_row.min_mapping_confidence,
            ),
            tuned_through=policy_row.tuned_through,
            final_test_starts_at=policy_row.final_test_starts_at,
            overrides=policy_row.overrides,
        )
        event_id, confidence, inverted = _event_mapping(session, attempt, now)
        reasons: list[Reason] = []
        if event_id is None:
            reasons.append(Reason.EVENT_MAPPING_AMBIGUOUS)
        rules = session.scalar(
            select(MarketRulesRecord).where(
                MarketRulesRecord.reference == mapping.rules_reference,
            )
        )
        if (
            mapping.result_status != "mapped"
            or rules is None
            or not rules.active
            or mapping.canonical_period != market.period
            or mapping.canonical_market_type != market.market_type
            or mapping.rules_reference != market.settlement_rules_version
            or mapping.canonical_line != odds.line
        ):
            reasons.append(Reason.MARKET_RULES_UNKNOWN)
        reliable = (
            odds.captured_at is not None and odds.timestamp_reliable and not odds.informational_only
        )
        age = (
            int((now - odds.captured_at).total_seconds()) if odds.captured_at is not None else None
        )
        if not reliable or age is None or age < 0:
            reasons.append(Reason.ODDS_STALE)
        if not provider.enabled or odds.provider_status != "operational":
            reasons.append(Reason.SOURCE_STALE)
        if odds.market_status != "open":
            reasons.append(Reason.MARKET_SUSPENDED)
        if odds.event_status != "scheduled":
            reasons.append(Reason.EVENT_ALREADY_STARTED)
        newer = session.scalar(
            select(OddsSnapshotRecord.id)
            .where(
                OddsSnapshotRecord.market_id == odds.market_id,
                OddsSnapshotRecord.recorded_at > odds.recorded_at,
                OddsSnapshotRecord.recorded_at <= now,
            )
            .limit(1)
        )
        if newer is not None:
            reasons.append(Reason.ODDS_STALE)
        prediction = (
            _get(session, PrematchPrediction, request.prediction_id)
            if request.prediction_id is not None
            else None
        )
        if prediction is not None and event_id is not None and prediction.event_id != event_id:
            raise SignalIntegrityError("la prédiction ne correspond pas à l'événement résolu")
        if prediction is not None and prediction.predicted_at > now:
            raise SignalIntegrityError("une prédiction future est interdite")
        game = session.get(Game, event_id) if event_id is not None else None
        if prediction is None or game is None or game.start_at is None:
            reasons.append(Reason.CAPABILITY_DISABLED)
        if game is not None and game.start_at is not None and now >= game.start_at:
            reasons.append(Reason.EVENT_ALREADY_STARTED)
        # Un modèle game winner ne price ni une série BO3 ni une autre game par analogie.
        if game is not None and not (
            (market.period == "SERIES" and game.best_of == 1)
            or (game.game_number is not None and market.period == f"GAME_{game.game_number}")
        ):
            reasons.append(Reason.CAPABILITY_DISABLED)
        freshness = FreshnessStatus.FAILED
        model_status = ModelStatus.BLOCKED
        evidence: dict[str, object] = {"sourceSlaSeconds": int(self.source_sla.total_seconds())}
        if prediction is not None:
            model = _get(session, ModelVersion, prediction.model_version_id)
            model_status = ModelStatus(model.status)
            if model.status_changed_at > now:
                raise SignalIntegrityError("l'état courant du modèle appartient au futur")
            if model_status is not ModelStatus.CHAMPION:
                reasons.append(Reason.MODEL_STALE)
            feature = _get(session, FeatureSnapshot, prediction.feature_snapshot_id)
            raw = _get(session, Snapshot, feature.target_oe_snapshot_id)
            facts = FreshnessService(
                repository=PostgresFreshnessRepository(connection),
                sla=self.source_sla,
                clock=FixedClock(UtcInstant(now)),
            ).evaluate(raw.source_catalog_id, policy=FreshnessPolicy())
            freshness = facts.status
            if raw.status != "validated" or facts.snapshot_id != raw.id:
                freshness = FreshnessStatus.DEGRADED
            if freshness is not FreshnessStatus.FRESH:
                reasons.append(Reason.SOURCE_STALE)
            if odds.captured_at is not None and prediction.cutoff_at > odds.captured_at:
                raise SignalIntegrityError("le cutoff des features dépasse la capture de cote")
            if not prediction.enabled:
                reasons.append(Reason.CAPABILITY_DISABLED)
            capability_ids: list[str] = []
            for capability in GameWinnerMarketPlugin().required_capabilities():
                state = session.scalar(
                    select(CapabilityEvaluation)
                    .where(
                        CapabilityEvaluation.snapshot_id == raw.id,
                        CapabilityEvaluation.capability == capability,
                        CapabilityEvaluation.evaluated_at <= now,
                    )
                    .order_by(
                        CapabilityEvaluation.evaluated_at.desc(),
                        CapabilityEvaluation.evaluation_revision.desc(),
                    )
                    .limit(1)
                )
                if state is None or state.status != "enabled":
                    reasons.append(Reason.CAPABILITY_DISABLED)
                if state is not None:
                    capability_ids.append(str(state.id))
            evidence["capabilityEvaluationIds"] = capability_ids
            evidence.update(
                {
                    "source": facts.to_dict(),
                    "targetOeSnapshotId": str(raw.id),
                    "modelStatus": model.status,
                    "modelVersionId": str(model.id),
                    "featureSnapshotId": str(feature.id),
                    "predictionFingerprint": prediction.prediction_fingerprint,
                }
            )
        # Une capture est complète uniquement à timestamp ET document source identiques.
        quote_rows = tuple(
            session.execute(
                select(OddsSnapshotRecord, ProviderOddsSelection.selection_type)
                .join(
                    ProviderOddsSelection,
                    ProviderOddsSelection.id == OddsSnapshotRecord.selection_id,
                )
                .where(
                    OddsSnapshotRecord.market_id == odds.market_id,
                    OddsSnapshotRecord.captured_at == odds.captured_at,
                    OddsSnapshotRecord.raw_payload_reference == odds.raw_payload_reference,
                    OddsSnapshotRecord.recorded_at <= now,
                )
                .order_by(OddsSnapshotRecord.id)
            )
        )
        expected = frozenset((SelectionType.TEAM_A, SelectionType.TEAM_B))
        complete = (
            len(quote_rows) == 2
            and {row[1] for row in quote_rows} == {value.value for value in expected}
            and rules is not None
            and set(rules.selection_types) == {value.value for value in expected}
            and all(
                row[0].timestamp_reliable and not row[0].informational_only for row in quote_rows
            )
        )
        if not complete:
            reasons.append(Reason.MARKET_RULES_UNKNOWN)
        if any(row[0].market_status != "open" for row in quote_rows):
            reasons.append(Reason.MARKET_SUSPENDED)
        evidence["quoteSnapshots"] = [
            {"id": str(row[0].id), "fingerprint": row[0].observation_fingerprint}
            for row in quote_rows
        ]
        canonical_selection = _oriented(SelectionType(selection.selection_type), inverted)
        no_vig_version: str | None = None
        engine = ValueDecisionEngine()
        resolved = policy.resolve(
            MarketType(market.market_type),
            competition_id=game.competition_id if game else None,
            bucket="longshot" if odds.decimal_odds >= Decimal(4) else "standard",
        )
        evidence["policyFingerprint"] = policy.fingerprint
        evidence["appliedScopes"] = list(resolved.applied_scopes)
        evidence["thresholds"] = resolved.thresholds.document()
        if age is not None and age > resolved.thresholds.max_odds_age_seconds:
            reasons.append(Reason.ODDS_STALE)
        if confidence < resolved.thresholds.min_mapping_confidence:
            reasons.append(Reason.EVENT_MAPPING_AMBIGUOUS)
        if (
            set(reasons)
            & {
                Reason.CAPABILITY_DISABLED,
                Reason.EVENT_MAPPING_AMBIGUOUS,
                Reason.MARKET_RULES_UNKNOWN,
            }
            or not reliable
            or age is None
            or age < 0
        ):
            decision = engine.abstain_without_value(
                policy.version,
                reasons=reasons,
                model_reason_codes=prediction.reason_codes if prediction else (),
            )
        else:
            assert prediction is not None and game is not None and game.start_at is not None
            assert age is not None
            no_vig = NoVigPricingEngine().calculate(
                NoVigMarket(
                    quotes=tuple(
                        MarketQuote(
                            _oriented(SelectionType(row[1]), inverted),
                            DecimalOdds(row[0].decimal_odds),
                        )
                        for row in quote_rows
                    ),
                    expected_selections=expected,
                )
            )
            no_vig_version = no_vig.strategy_version
            probability = (
                prediction.team_a_probability
                if canonical_selection is SelectionType.TEAM_A
                else prediction.team_b_probability
            )
            low = (
                prediction.team_a_low
                if canonical_selection is SelectionType.TEAM_A
                else prediction.team_b_low
            )
            value = ValuePricingEngine().calculate(
                ValuePricingInput(
                    no_vig.quote(canonical_selection),
                    Probability(probability),
                    Probability(low),
                )
            )
            admission = ValueAdmissionGate().evaluate(
                ValueAdmissionInput(
                    value_price=value,
                    policy=resolved,
                    mapping_confidence=Probability(confidence),
                    odds_age_seconds=age,
                    model_status=model_status,
                    source_freshness=freshness,
                    market_status=MarketStatus(odds.market_status),
                    prediction_cutoff=prediction.cutoff_at,
                    event_starts_at=game.start_at,
                    evaluated_at=now,
                    capability_enabled=prediction.enabled,
                    event_mapping_resolved=True,
                    market_rules_known=True,
                )
            )
            decision = engine.from_admission(
                admission,
                evaluated_value=value,
                upstream_reasons=reasons,
                model_reason_codes=prediction.reason_codes,
            )
            evidence["checks"] = [
                {"code": check.code.value, "passed": check.passed} for check in admission.checks
            ]
        grade = grade_decision(decision)
        signal: StoredSignal | None = None
        if (
            event_id is not None
            and prediction is not None
            and reliable
            and age is not None
            and age >= 0
        ):
            signal = PostgresSignalRepository(self.engine).append_in_transaction(
                connection,
                SignalPublication(
                    odds_snapshot_id=odds.id,
                    prediction_id=prediction.id,
                    event_mapping_attempt_id=attempt.id,
                    selection=canonical_selection,
                    grade=grade,
                    decision=decision,
                    mapping_confidence=Probability(confidence),
                    source_freshness=freshness,
                    odds_age_seconds=age,
                    no_vig_policy_version=no_vig_version,
                ),
                computed_at=now,
            )
        values = {
            "odds_snapshot_id": str(odds.id),
            "event_mapping_attempt_id": str(attempt.id),
            "market_mapping_attempt_id": str(mapping.id),
            "prediction_id": str(prediction.id) if prediction else None,
            "policy_version": policy.version,
            "signal_id": str(signal.signal_id) if signal else None,
            "engine_version": VALUE_PIPELINE_VERSION,
            "grade": grade.value,
            "abstention_reasons": [reason.value for reason in decision.reasons],
            "evidence": evidence,
            "computed_at": now.isoformat(),
        }
        fingerprint = hashlib.sha256(
            json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        evaluation_id = uuid5(NAMESPACE_URL, f"metiquo:value-evaluation:{fingerprint}")
        connection.execute(
            insert(ValueEvaluationRecord)
            .values(
                **{
                    **values,
                    "id": evaluation_id,
                    "odds_snapshot_id": odds.id,
                    "event_mapping_attempt_id": attempt.id,
                    "market_mapping_attempt_id": mapping.id,
                    "prediction_id": prediction.id if prediction else None,
                    "signal_id": signal.signal_id if signal else None,
                    "computed_at": now,
                    "fingerprint": fingerprint,
                },
            )
            .on_conflict_do_nothing(index_elements=["fingerprint"])
        )
        return ValueEvaluation(evaluation_id, signal, grade, decision.reasons, now, fingerprint)


def grade_decision(decision: ValueDecision) -> ValueGrade:
    """V1 : VALUE après tous les gardes ; NO_EDGE seulement pour un écart insuffisant."""
    if decision.is_opportunity:
        return ValueGrade.VALUE
    if decision.evaluated_value is not None and set(decision.reasons) <= _PRICE_REASONS:
        return ValueGrade.NO_EDGE
    return ValueGrade.BLOCKED


def _get[T: Base](session: Session, model: type[T], identity: UUID) -> T:
    row = session.get(model, identity, with_for_update={"read": True})
    if row is None:
        raise SignalIntegrityError(f"preuve {model.__tablename__} introuvable")
    return row


def _oriented(selection: SelectionType, inverted: bool) -> SelectionType:
    if selection not in {SelectionType.TEAM_A, SelectionType.TEAM_B}:
        raise SignalIntegrityError("le modèle binaire exige une sélection équipe")
    if not inverted:
        return selection
    return SelectionType.TEAM_B if selection is SelectionType.TEAM_A else SelectionType.TEAM_A


def _event_mapping(
    session: Session,
    attempt: EventMappingAttempt,
    now: datetime,
) -> tuple[UUID | None, Decimal, bool]:
    if attempt.result_status == "auto_matched":
        return attempt.selected_event_id, attempt.top_score, attempt.selections_inverted
    review = session.scalar(
        select(MappingReviewRecord)
        .where(
            MappingReviewRecord.attempt_id == attempt.id,
        )
        .with_for_update(read=True)
    )
    if (
        review is None
        or review.status != "approved"
        or review.reviewed_at is None
        or review.reviewed_at > now
    ):
        return None, attempt.top_score, False
    candidate = session.scalar(
        select(EventMappingCandidateScore).where(
            EventMappingCandidateScore.attempt_id == attempt.id,
            EventMappingCandidateScore.canonical_event_id == review.selected_event_id,
        )
    )
    if candidate is None:
        raise SignalIntegrityError("le candidat approuvé est introuvable")
    return (
        cast(UUID, review.selected_event_id),
        candidate.total_score,
        candidate.selections_inverted,
    )
