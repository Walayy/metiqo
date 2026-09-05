"""Promotion manuelle, shadow predictions et rollback atomique."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, RowMapping, Table, select, update
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.ml_models import ModelStatusEvent as ModelStatusEventRow
from metiquo.db.ml_models import ModelVersion as ModelVersionRow
from metiquo.db.ml_models import ShadowPrediction as ShadowPredictionRow
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime
from metiquo.models.baselines import COMPETITION_PRIOR, RATING, RECENT_FORM
from metiquo.models.evaluation import PromotionMetricPolicy
from metiquo.models.registry import BLOCKED, CANDIDATE, CHAMPION, RETIRED

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROBABILITY_QUANTUM = Decimal("0.00000001")
_REQUIRED_BASELINES = frozenset({COMPETITION_PRIOR, RECENT_FORM, RATING})


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    evaluation_report_fingerprint: str
    baseline_log_loss_deltas: Mapping[str, Decimal]
    metric_basis: tuple[str, ...]
    manual_approval_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "baseline_log_loss_deltas",
            MappingProxyType(dict(self.baseline_log_loss_deltas)),
        )
        if _SHA256.fullmatch(self.evaluation_report_fingerprint) is None:
            raise ValueError("fingerprint du rapport d'évaluation invalide")
        if not self.manual_approval_reference.strip():
            raise ValueError("une référence d'approbation manuelle est requise")
        if set(self.baseline_log_loss_deltas) != _REQUIRED_BASELINES:
            raise ValueError("les trois baselines doivent être comparées avant promotion")
        if any(
            not value.is_finite() or value <= 0 for value in self.baseline_log_loss_deltas.values()
        ):
            raise ValueError("chaque gain de log loss face aux baselines doit être positif")
        PromotionMetricPolicy().assert_valid_basis(self.metric_basis)
        if len(set(self.metric_basis)) < 2:
            raise ValueError("la promotion exige une décision multi-métrique")

    def document(self) -> dict[str, object]:
        return {
            "baseline_log_loss_deltas": {
                key: str(value) for key, value in sorted(self.baseline_log_loss_deltas.items())
            },
            "evaluation_report_fingerprint": self.evaluation_report_fingerprint,
            "manual_approval_reference": self.manual_approval_reference,
            "metric_basis": list(self.metric_basis),
        }


@dataclass(frozen=True, slots=True)
class ModelStatusEvent:
    event_id: UUID
    model_version_id: UUID
    related_model_version_id: UUID | None
    action: str
    from_status: str
    to_status: str
    actor: str
    reason: str
    evidence: Mapping[str, object]
    occurred_at: datetime
    transition_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))
        object.__setattr__(self, "occurred_at", normalize_utc_datetime(self.occurred_at))


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    model_version_id: UUID
    status: str
    previous_champion_id: UUID | None
    event_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ShadowPrediction:
    prediction_id: UUID
    model_version_id: UUID
    champion_model_version_id: UUID
    event_id: UUID
    cutoff_at: datetime
    predicted_at: datetime
    probability: Decimal
    p_low: Decimal
    p_high: Decimal
    context_fingerprint: str
    prediction_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff_at", normalize_utc_datetime(self.cutoff_at))
        object.__setattr__(self, "predicted_at", normalize_utc_datetime(self.predicted_at))
        if not Decimal() <= self.p_low <= self.probability <= self.p_high <= Decimal(1):
            raise ValueError("l'intervalle shadow doit être ordonné dans [0,1]")
        if self.predicted_at < self.cutoff_at:
            raise ValueError("la prédiction shadow ne peut précéder son cutoff")
        if _SHA256.fullmatch(self.context_fingerprint) is None:
            raise ValueError("fingerprint de contexte invalide")


class ModelLifecycle:
    """Appliquer les transitions de champion sous verrou PostgreSQL."""

    def __init__(self, *, engine: Engine, clock: Clock | None = None) -> None:
        self._engine = engine
        self._clock = clock or SystemClock()

    def promote(
        self,
        model_version_id: UUID,
        *,
        actor: str,
        reason: str,
        evidence: PromotionEvidence,
    ) -> LifecycleResult:
        _validate_decision(actor, reason)
        models = cast(Table, ModelVersionRow.__table__)
        events = cast(Table, ModelStatusEventRow.__table__)
        occurred_at = self._clock.now().value
        with self._engine.begin() as connection:
            target = (
                connection.execute(
                    select(models).where(models.c.id == model_version_id).with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if target is None:
                raise ValueError("version candidate introuvable")
            if target["status"] != CANDIDATE:
                raise ValueError("seule une version candidate peut être promue")
            if target["evaluation_report_fingerprint"] != evidence.evaluation_report_fingerprint:
                raise ValueError("la preuve de promotion ne correspond pas au rapport enregistré")
            current = (
                connection.execute(
                    select(models)
                    .where(
                        models.c.game == target["game"],
                        models.c.market == target["market"],
                        models.c.segment == target["segment"],
                        models.c.status == CHAMPION,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            previous_id = cast(UUID | None, current["id"] if current is not None else None)
            event_ids: list[UUID] = []
            if current is not None:
                connection.execute(
                    update(models)
                    .where(models.c.id == current["id"])
                    .values(
                        status=RETIRED,
                        status_changed_by=actor,
                        status_changed_at=occurred_at,
                        status_reason=reason,
                    )
                )
                event_ids.append(
                    _record_event(
                        connection,
                        events,
                        model_version_id=cast(UUID, current["id"]),
                        related_model_version_id=model_version_id,
                        action="retire_for_promotion",
                        from_status=CHAMPION,
                        to_status=RETIRED,
                        actor=actor,
                        reason=reason,
                        evidence={"replacement": str(model_version_id)},
                        occurred_at=occurred_at,
                    )
                )
            connection.execute(
                update(models)
                .where(models.c.id == model_version_id)
                .values(
                    status=CHAMPION,
                    status_changed_by=actor,
                    status_changed_at=occurred_at,
                    status_reason=reason,
                )
            )
            event_ids.append(
                _record_event(
                    connection,
                    events,
                    model_version_id=model_version_id,
                    related_model_version_id=previous_id,
                    action="promote",
                    from_status=CANDIDATE,
                    to_status=CHAMPION,
                    actor=actor,
                    reason=reason,
                    evidence=evidence.document(),
                    occurred_at=occurred_at,
                )
            )
        return LifecycleResult(model_version_id, CHAMPION, previous_id, tuple(event_ids))

    def rollback(
        self,
        model_version_id: UUID,
        *,
        actor: str,
        reason: str,
    ) -> LifecycleResult:
        _validate_decision(actor, reason)
        models = cast(Table, ModelVersionRow.__table__)
        events = cast(Table, ModelStatusEventRow.__table__)
        occurred_at = self._clock.now().value
        with self._engine.begin() as connection:
            target = (
                connection.execute(
                    select(models).where(models.c.id == model_version_id).with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if target is None or target["status"] != RETIRED:
                raise ValueError("le rollback exige une version précédemment retirée")
            current = (
                connection.execute(
                    select(models)
                    .where(
                        models.c.game == target["game"],
                        models.c.market == target["market"],
                        models.c.segment == target["segment"],
                        models.c.status == CHAMPION,
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if current is None or current["id"] == model_version_id:
                raise ValueError("aucun champion distinct à remplacer lors du rollback")
            current_id = cast(UUID, current["id"])
            connection.execute(
                update(models)
                .where(models.c.id == current_id)
                .values(
                    status=RETIRED,
                    status_changed_by=actor,
                    status_changed_at=occurred_at,
                    status_reason=reason,
                )
            )
            retired_event = _record_event(
                connection,
                events,
                model_version_id=current_id,
                related_model_version_id=model_version_id,
                action="retire_for_rollback",
                from_status=CHAMPION,
                to_status=RETIRED,
                actor=actor,
                reason=reason,
                evidence={"rollback_target": str(model_version_id)},
                occurred_at=occurred_at,
            )
            connection.execute(
                update(models)
                .where(models.c.id == model_version_id)
                .values(
                    status=CHAMPION,
                    status_changed_by=actor,
                    status_changed_at=occurred_at,
                    status_reason=reason,
                )
            )
            rollback_event = _record_event(
                connection,
                events,
                model_version_id=model_version_id,
                related_model_version_id=current_id,
                action="rollback",
                from_status=RETIRED,
                to_status=CHAMPION,
                actor=actor,
                reason=reason,
                evidence={"replaced_champion": str(current_id)},
                occurred_at=occurred_at,
            )
        return LifecycleResult(
            model_version_id,
            CHAMPION,
            current_id,
            (retired_event, rollback_event),
        )

    def block(
        self,
        model_version_id: UUID,
        *,
        actor: str,
        reason: str,
    ) -> LifecycleResult:
        _validate_decision(actor, reason)
        models = cast(Table, ModelVersionRow.__table__)
        events = cast(Table, ModelStatusEventRow.__table__)
        occurred_at = self._clock.now().value
        with self._engine.begin() as connection:
            target = (
                connection.execute(
                    select(models).where(models.c.id == model_version_id).with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if target is None or target["status"] != CANDIDATE:
                raise ValueError("seule une version candidate peut être bloquée")
            connection.execute(
                update(models)
                .where(models.c.id == model_version_id)
                .values(
                    status=BLOCKED,
                    status_changed_by=actor,
                    status_changed_at=occurred_at,
                    status_reason=reason,
                )
            )
            event_id = _record_event(
                connection,
                events,
                model_version_id=model_version_id,
                related_model_version_id=None,
                action="block",
                from_status=CANDIDATE,
                to_status=BLOCKED,
                actor=actor,
                reason=reason,
                evidence={},
                occurred_at=occurred_at,
            )
        return LifecycleResult(model_version_id, BLOCKED, None, (event_id,))

    def retire(
        self,
        model_version_id: UUID,
        *,
        actor: str,
        reason: str,
    ) -> LifecycleResult:
        """Retirer explicitement un candidat ou un champion avec une preuve append-only."""

        _validate_decision(actor, reason)
        models = cast(Table, ModelVersionRow.__table__)
        events = cast(Table, ModelStatusEventRow.__table__)
        occurred_at = self._clock.now().value
        with self._engine.begin() as connection:
            target = (
                connection.execute(
                    select(models).where(models.c.id == model_version_id).with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if target is None:
                raise ValueError("version de modèle introuvable")
            current_status = cast(str, target["status"])
            if current_status not in {CANDIDATE, CHAMPION}:
                raise ValueError("seul un candidat ou un champion actif peut être retiré")
            connection.execute(
                update(models)
                .where(models.c.id == model_version_id)
                .values(
                    status=RETIRED,
                    status_changed_by=actor,
                    status_changed_at=occurred_at,
                    status_reason=reason,
                )
            )
            event_id = _record_event(
                connection,
                events,
                model_version_id=model_version_id,
                related_model_version_id=None,
                action="retire",
                from_status=current_status,
                to_status=RETIRED,
                actor=actor,
                reason=reason,
                evidence={"manual": True},
                occurred_at=occurred_at,
            )
        return LifecycleResult(model_version_id, RETIRED, None, (event_id,))

    def record_shadow(
        self,
        model_version_id: UUID,
        *,
        event_id: UUID,
        cutoff_at: datetime,
        predicted_at: datetime,
        probability: Decimal,
        p_low: Decimal,
        p_high: Decimal,
        context_fingerprint: str,
    ) -> ShadowPrediction:
        cutoff_at = normalize_utc_datetime(cutoff_at)
        predicted_at = normalize_utc_datetime(predicted_at)
        probability = _probability(probability)
        p_low = _probability(p_low)
        p_high = _probability(p_high)
        if not p_low <= probability <= p_high:
            raise ValueError("l'intervalle shadow doit contenir la probabilité")
        if predicted_at < cutoff_at:
            raise ValueError("la prédiction shadow ne peut précéder son cutoff")
        if _SHA256.fullmatch(context_fingerprint) is None:
            raise ValueError("fingerprint de contexte invalide")
        models = cast(Table, ModelVersionRow.__table__)
        shadows = cast(Table, ShadowPredictionRow.__table__)
        with self._engine.begin() as connection:
            challenger = (
                connection.execute(
                    select(models).where(models.c.id == model_version_id).with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if challenger is None or challenger["status"] != CANDIDATE:
                raise ValueError("une prédiction shadow exige un challenger candidate")
            champion_id = connection.execute(
                select(models.c.id)
                .where(
                    models.c.game == challenger["game"],
                    models.c.market == challenger["market"],
                    models.c.segment == challenger["segment"],
                    models.c.status == CHAMPION,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if champion_id is None:
                raise ValueError("une prédiction shadow exige un champion actif")
            document = {
                "champion_model_version_id": str(champion_id),
                "context_fingerprint": context_fingerprint,
                "cutoff_at": cutoff_at.isoformat(),
                "event_id": str(event_id),
                "model_version_id": str(model_version_id),
                "p_high": str(p_high),
                "p_low": str(p_low),
                "predicted_at": predicted_at.isoformat(),
                "probability": str(probability),
            }
            fingerprint = _content_hash(document)
            prediction_id = uuid5(NAMESPACE_URL, f"metiquo:shadow:{fingerprint}")
            connection.execute(
                insert(shadows)
                .values(
                    id=prediction_id,
                    model_version_id=model_version_id,
                    champion_model_version_id=champion_id,
                    event_id=event_id,
                    cutoff_at=cutoff_at,
                    predicted_at=predicted_at,
                    probability=probability,
                    p_low=p_low,
                    p_high=p_high,
                    context_fingerprint=context_fingerprint,
                    prediction_fingerprint=fingerprint,
                )
                .on_conflict_do_nothing(index_elements=[shadows.c.prediction_fingerprint])
            )
            row = (
                connection.execute(
                    select(shadows).where(shadows.c.prediction_fingerprint == fingerprint)
                )
                .mappings()
                .one()
            )
        return _stored_shadow(row)

    def status_events(self, model_version_id: UUID) -> tuple[ModelStatusEvent, ...]:
        events = cast(Table, ModelStatusEventRow.__table__)
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(events)
                    .where(events.c.model_version_id == model_version_id)
                    .order_by(events.c.occurred_at, events.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(_stored_event(row) for row in rows)


def _record_event(
    connection: Connection,
    events: Table,
    *,
    model_version_id: UUID,
    related_model_version_id: UUID | None,
    action: str,
    from_status: str,
    to_status: str,
    actor: str,
    reason: str,
    evidence: Mapping[str, object],
    occurred_at: datetime,
) -> UUID:
    document = {
        "action": action,
        "actor": actor,
        "evidence": dict(evidence),
        "from_status": from_status,
        "model_version_id": str(model_version_id),
        "occurred_at": occurred_at.isoformat(),
        "reason": reason,
        "related_model_version_id": (
            str(related_model_version_id) if related_model_version_id is not None else None
        ),
        "to_status": to_status,
    }
    fingerprint = _content_hash(document)
    event_id = uuid5(NAMESPACE_URL, f"metiquo:model-status-event:{fingerprint}")
    connection.execute(
        insert(events).values(
            id=event_id,
            model_version_id=model_version_id,
            related_model_version_id=related_model_version_id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            reason=reason,
            evidence=dict(evidence),
            occurred_at=occurred_at,
            transition_fingerprint=fingerprint,
        )
    )
    return event_id


def _stored_event(row: RowMapping) -> ModelStatusEvent:
    return ModelStatusEvent(
        event_id=cast(UUID, row["id"]),
        model_version_id=cast(UUID, row["model_version_id"]),
        related_model_version_id=cast(UUID | None, row["related_model_version_id"]),
        action=cast(str, row["action"]),
        from_status=cast(str, row["from_status"]),
        to_status=cast(str, row["to_status"]),
        actor=cast(str, row["actor"]),
        reason=cast(str, row["reason"]),
        evidence=cast(Mapping[str, object], row["evidence"]),
        occurred_at=cast(datetime, row["occurred_at"]),
        transition_fingerprint=cast(str, row["transition_fingerprint"]),
    )


def _stored_shadow(row: RowMapping) -> ShadowPrediction:
    return ShadowPrediction(
        prediction_id=cast(UUID, row["id"]),
        model_version_id=cast(UUID, row["model_version_id"]),
        champion_model_version_id=cast(UUID, row["champion_model_version_id"]),
        event_id=cast(UUID, row["event_id"]),
        cutoff_at=cast(datetime, row["cutoff_at"]),
        predicted_at=cast(datetime, row["predicted_at"]),
        probability=cast(Decimal, row["probability"]),
        p_low=cast(Decimal, row["p_low"]),
        p_high=cast(Decimal, row["p_high"]),
        context_fingerprint=cast(str, row["context_fingerprint"]),
        prediction_fingerprint=cast(str, row["prediction_fingerprint"]),
    )


def _validate_decision(actor: str, reason: str) -> None:
    if not actor.strip() or not reason.strip():
        raise ValueError("acteur et motif explicites sont requis")


def _probability(value: Decimal) -> Decimal:
    if not value.is_finite() or not 0 <= value <= 1:
        raise ValueError("une probabilité doit être finie dans [0,1]")
    return value.quantize(_PROBABILITY_QUANTUM, rounding=ROUND_HALF_EVEN)


def _content_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
