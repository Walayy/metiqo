"""Service reproductible de prédictions GAME_WINNER pré-match."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.core_models import Game
from metiquo.db.ml_models import PrematchPrediction as PrematchPredictionRow
from metiquo.features import FULL_FEATURE_SET_VERSION, StoredFeatureSnapshot
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime
from metiquo.markets.game_winner import (
    GameWinnerMarketPlugin,
    GameWinnerProbability,
    PluginDisabledError,
)
from metiquo.models.datasets import GAME_WINNER_MARKET
from metiquo.models.registry import ModelRegistry, ModelVersion
from metiquo.models.uncertainty import UncertaintyArtifact

_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")


@dataclass(frozen=True, slots=True)
class ModelInference:
    raw_team_a_probability: Decimal
    training_domain_distance: Decimal

    def __post_init__(self) -> None:
        if (
            not self.raw_team_a_probability.is_finite()
            or not Decimal() <= self.raw_team_a_probability <= Decimal(1)
        ):
            raise ValueError("la probabilité brute doit être finie dans [0,1]")
        if not self.training_domain_distance.is_finite() or self.training_domain_distance < 0:
            raise ValueError("la distance au domaine d'entraînement doit être positive")


class ProbabilityModel(Protocol):
    def predict(self, features: Mapping[str, object]) -> ModelInference: ...


class ProbabilityModelDecoder(Protocol):
    def decode(self, payload: bytes, *, model: ModelVersion) -> ProbabilityModel: ...


class UncertaintyArtifactSource(Protocol):
    def get(self, artifact_id: UUID) -> UncertaintyArtifact | None: ...


class PredictionFeatureBuilder(Protocol):
    def build_for_prediction(
        self,
        event_id: UUID,
        *,
        cutoff_at: datetime,
    ) -> StoredFeatureSnapshot: ...


@dataclass(frozen=True, slots=True)
class LoadedChampion:
    model: ModelVersion
    uncertainty: UncertaintyArtifact
    predictor: ProbabilityModel


class ChampionRuntimeLoader(Protocol):
    def load(self, *, segment: str = "global") -> LoadedChampion: ...


class RegistryChampionRuntimeLoader:
    """Vérifier le binaire du champion puis reconstruire son runtime."""

    def __init__(
        self,
        *,
        registry: ModelRegistry,
        uncertainty_artifacts: UncertaintyArtifactSource,
        decoder: ProbabilityModelDecoder,
    ) -> None:
        self._registry = registry
        self._uncertainty_artifacts = uncertainty_artifacts
        self._decoder = decoder

    def load(self, *, segment: str = "global") -> LoadedChampion:
        champion = self._registry.current_champion(segment=segment)
        if champion is None:
            raise PluginDisabledError("CHAMPION_MISSING")
        payload = self._registry.load_artifact(champion)
        uncertainty = self._uncertainty_artifacts.get(champion.uncertainty_artifact_id)
        if uncertainty is None:
            raise PluginDisabledError("UNCERTAINTY_ARTIFACT_MISSING")
        return LoadedChampion(
            model=champion,
            uncertainty=uncertainty,
            predictor=self._decoder.decode(payload, model=champion),
        )


@dataclass(frozen=True, slots=True)
class PrematchPredictionRequest:
    event_id: UUID
    cutoff_at: datetime
    segment: str = "global"

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff_at", normalize_utc_datetime(self.cutoff_at))
        if not self.segment.strip():
            raise ValueError("le segment de prédiction est requis")


@dataclass(frozen=True, slots=True)
class StoredPrematchPrediction:
    prediction_id: UUID
    market: str
    event_id: UUID
    team_a_id: UUID
    team_b_id: UUID
    feature_snapshot_id: UUID
    model_version_id: UUID
    calibrator_artifact_id: UUID
    uncertainty_artifact_id: UUID
    cutoff_at: datetime
    predicted_at: datetime
    team_a_probability: Decimal
    team_a_low: Decimal
    team_a_high: Decimal
    team_b_probability: Decimal
    team_b_low: Decimal
    team_b_high: Decimal
    confidence: Decimal
    enabled: bool
    reason_codes: tuple[str, ...]
    code_commit: str
    inference_fingerprint: str
    prediction_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff_at", normalize_utc_datetime(self.cutoff_at))
        object.__setattr__(self, "predicted_at", normalize_utc_datetime(self.predicted_at))
        if self.team_a_probability + self.team_b_probability != Decimal(1):
            raise ValueError("les probabilités persistées doivent sommer à 1")


class PrematchPredictionService:
    """Construire une preuve au cutoff et l'ajouter sans réécriture."""

    def __init__(
        self,
        *,
        engine: Engine,
        features: PredictionFeatureBuilder,
        runtime: ChampionRuntimeLoader,
        code_commit: str,
        plugin: GameWinnerMarketPlugin | None = None,
        clock: Clock | None = None,
    ) -> None:
        if _COMMIT.fullmatch(code_commit) is None:
            raise ValueError("code_commit doit être un hash git hexadécimal")
        self._engine = engine
        self._features = features
        self._runtime = runtime
        self._code_commit = code_commit
        self._plugin = plugin or GameWinnerMarketPlugin()
        self._clock = clock or SystemClock()

    def predict(self, request: PrematchPredictionRequest) -> StoredPrematchPrediction:
        predicted_at = self._clock.now().value
        event_start = self._event_start(request.event_id)
        if request.cutoff_at >= event_start:
            raise ValueError("le cutoff pré-match doit précéder le début de la game")
        if predicted_at >= event_start:
            raise ValueError("une prédiction pré-match doit précéder le début de la game")
        if predicted_at < request.cutoff_at:
            raise ValueError("une prédiction ne peut précéder son cutoff")
        runtime = self._runtime.load(segment=request.segment)
        if runtime.model.feature_set_version != FULL_FEATURE_SET_VERSION:
            raise PluginDisabledError("CHAMPION_FEATURE_SET_MISMATCH")
        if runtime.model.training_cutoff_max >= request.cutoff_at:
            raise PluginDisabledError("CHAMPION_TRAINING_CUTOFF_NOT_PRIOR")
        if runtime.model.registered_at > predicted_at:
            raise PluginDisabledError("CHAMPION_NOT_AVAILABLE_AT_PREDICTION_TIME")
        snapshot = self._features.build_for_prediction(
            request.event_id,
            cutoff_at=request.cutoff_at,
        )
        if snapshot.event_id != request.event_id or snapshot.cutoff_at != request.cutoff_at:
            raise RuntimeError("le snapshot construit ne correspond pas à la demande")
        inference = runtime.predictor.predict(snapshot.values)
        prediction = self._plugin.predict(
            runtime.model,
            runtime.uncertainty,
            raw_team_a_probability=inference.raw_team_a_probability,
            data_coverage=_data_coverage(snapshot.missingness),
            training_domain_distance=inference.training_domain_distance,
        )
        inference_document = {
            "calibrator_artifact_id": str(runtime.model.calibrator_artifact_id),
            "code_commit": self._code_commit,
            "event_id": str(snapshot.event_id),
            "enabled": prediction.enabled,
            "feature_snapshot_id": str(snapshot.snapshot_id),
            "market": GAME_WINNER_MARKET,
            "model_version_id": str(runtime.model.model_version_id),
            "reason_codes": list(prediction.reason_codes),
            "team_a": _probability_document(prediction.team_a),
            "team_b": _probability_document(prediction.team_b),
            "uncertainty_artifact_id": str(runtime.uncertainty.artifact_id),
        }
        inference_fingerprint = _content_hash(inference_document)
        prediction_fingerprint = _content_hash(
            {
                "inference_fingerprint": inference_fingerprint,
                "predicted_at": predicted_at.isoformat(),
            }
        )
        prediction_id = uuid5(
            NAMESPACE_URL,
            f"metiquo:prematch-prediction:{prediction_fingerprint}",
        )
        table = cast(Table, PrematchPredictionRow.__table__)
        values = {
            "id": prediction_id,
            "market": GAME_WINNER_MARKET,
            "event_id": snapshot.event_id,
            "team_a_id": snapshot.team_a_id,
            "team_b_id": snapshot.team_b_id,
            "feature_snapshot_id": snapshot.snapshot_id,
            "model_version_id": runtime.model.model_version_id,
            "calibrator_artifact_id": runtime.model.calibrator_artifact_id,
            "uncertainty_artifact_id": runtime.uncertainty.artifact_id,
            "cutoff_at": request.cutoff_at,
            "predicted_at": predicted_at,
            "team_a_probability": prediction.team_a.p50,
            "team_a_low": prediction.team_a.p_low,
            "team_a_high": prediction.team_a.p_high,
            "team_b_probability": prediction.team_b.p50,
            "team_b_low": prediction.team_b.p_low,
            "team_b_high": prediction.team_b.p_high,
            "confidence": prediction.team_a.confidence,
            "enabled": prediction.enabled,
            "reason_codes": list(prediction.reason_codes),
            "code_commit": self._code_commit,
            "inference_fingerprint": inference_fingerprint,
            "prediction_fingerprint": prediction_fingerprint,
        }
        with self._engine.begin() as connection:
            connection.execute(
                insert(table)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[table.c.prediction_fingerprint])
            )
            row = (
                connection.execute(
                    select(table).where(table.c.prediction_fingerprint == prediction_fingerprint)
                )
                .mappings()
                .one()
            )
        return _stored(row)

    def _event_start(self, event_id: UUID) -> datetime:
        games = cast(Table, Game.__table__)
        with self._engine.connect() as connection:
            start_at = connection.execute(
                select(games.c.start_at).where(games.c.id == event_id)
            ).scalar_one_or_none()
        if not isinstance(start_at, datetime):
            raise ValueError("la game prédite doit avoir un début planifié")
        return normalize_utc_datetime(start_at)

    def list_for_event(self, event_id: UUID) -> tuple[StoredPrematchPrediction, ...]:
        table = cast(Table, PrematchPredictionRow.__table__)
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(table)
                    .where(table.c.event_id == event_id)
                    .order_by(table.c.predicted_at, table.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(_stored(row) for row in rows)


def _data_coverage(missingness: Mapping[str, bool]) -> Decimal:
    if not missingness:
        return Decimal()
    present = sum(not missing for missing in missingness.values())
    return Decimal(present) / Decimal(len(missingness))


def _probability_document(probability: GameWinnerProbability) -> dict[str, object]:
    return {
        "confidence": str(probability.confidence),
        "p50": str(probability.p50),
        "p_high": str(probability.p_high),
        "p_low": str(probability.p_low),
        "selection": probability.selection.value,
    }


def _stored(row: RowMapping) -> StoredPrematchPrediction:
    return StoredPrematchPrediction(
        prediction_id=cast(UUID, row["id"]),
        market=str(row["market"]),
        event_id=cast(UUID, row["event_id"]),
        team_a_id=cast(UUID, row["team_a_id"]),
        team_b_id=cast(UUID, row["team_b_id"]),
        feature_snapshot_id=cast(UUID, row["feature_snapshot_id"]),
        model_version_id=cast(UUID, row["model_version_id"]),
        calibrator_artifact_id=cast(UUID, row["calibrator_artifact_id"]),
        uncertainty_artifact_id=cast(UUID, row["uncertainty_artifact_id"]),
        cutoff_at=cast(datetime, row["cutoff_at"]),
        predicted_at=cast(datetime, row["predicted_at"]),
        team_a_probability=cast(Decimal, row["team_a_probability"]),
        team_a_low=cast(Decimal, row["team_a_low"]),
        team_a_high=cast(Decimal, row["team_a_high"]),
        team_b_probability=cast(Decimal, row["team_b_probability"]),
        team_b_low=cast(Decimal, row["team_b_low"]),
        team_b_high=cast(Decimal, row["team_b_high"]),
        confidence=cast(Decimal, row["confidence"]),
        enabled=bool(row["enabled"]),
        reason_codes=tuple(cast(list[str], row["reason_codes"])),
        code_commit=str(row["code_commit"]),
        inference_fingerprint=str(row["inference_fingerprint"]),
        prediction_fingerprint=str(row["prediction_fingerprint"]),
    )


def _content_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
