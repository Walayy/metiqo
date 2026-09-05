"""Baseline rating pré-game transformée en probabilité et artefact OOF."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from types import MappingProxyType
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.ml_models import RatingArtifact as RatingArtifactRow
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime
from metiquo.models.baselines import (
    OOF_VALIDATION,
    RATING,
    BaselinePrediction,
    BaselineRun,
    BinaryMetricReport,
    build_baseline_run,
    evaluate_binary_probabilities,
)
from metiquo.models.datasets import GAME_WINNER_MARKET
from metiquo.models.validation import (
    FoldProbabilities,
    OutOfFoldPredictions,
    WalkForwardExample,
    WalkForwardPlan,
    collect_oof_predictions,
)

RATING_ARTIFACT_VERSION = "rating-probability-v1"
RATING_FEATURE = "rating.difference"
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_SCALE_QUANTUM = Decimal("0.0001")
_PROBABILITY_QUANTUM = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class RatingSearchParameters:
    """Grille explicite autorisée pour le tuning sur validations temporelles."""

    candidate_scales: tuple[Decimal, ...] = (
        Decimal("200"),
        Decimal("300"),
        Decimal("400"),
        Decimal("600"),
        Decimal("800"),
    )
    rating_feature: str = RATING_FEATURE
    artifact_version: str = RATING_ARTIFACT_VERSION

    def __post_init__(self) -> None:
        if not self.candidate_scales:
            raise ValueError("au moins une échelle candidate est requise")
        scales = tuple(_scale(value) for value in self.candidate_scales)
        if any(not value.is_finite() or value <= 0 for value in scales):
            raise ValueError("les échelles candidates doivent être finies et positives")
        if len(scales) != len(set(scales)):
            raise ValueError("les échelles candidates doivent être uniques")
        if self.rating_feature != RATING_FEATURE:
            raise ValueError(f"la baseline rating exige la feature {RATING_FEATURE}")
        if not self.artifact_version.strip():
            raise ValueError("la version d'artefact rating est requise")
        object.__setattr__(self, "candidate_scales", scales)

    def document(self) -> dict[str, object]:
        return {
            "candidate_scales": [str(value) for value in self.candidate_scales],
            "rating_feature": self.rating_feature,
            "selection_metric": "log_loss",
            "selection_scope": OOF_VALIDATION,
        }


@dataclass(frozen=True, slots=True)
class RatingArtifact:
    artifact_id: UUID
    dataset_id: UUID
    market: str
    artifact_version: str
    walk_forward_fingerprint: str
    rating_feature: str
    selected_scale: Decimal
    candidate_scales: tuple[Decimal, ...]
    selection_metric: str
    selection_scope: str
    candidate_metrics: Mapping[str, BinaryMetricReport]
    artifact_fingerprint: str
    code_commit: str
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", normalize_utc_datetime(self.created_at))

    def content_document(self) -> dict[str, object]:
        return {
            "artifact_version": self.artifact_version,
            "candidate_metrics": {
                key: value.document() for key, value in sorted(self.candidate_metrics.items())
            },
            "candidate_scales": [str(value) for value in self.candidate_scales],
            "code_commit": self.code_commit,
            "dataset_id": str(self.dataset_id),
            "market": self.market,
            "rating_feature": self.rating_feature,
            "selected_scale": str(self.selected_scale),
            "selection_metric": self.selection_metric,
            "selection_scope": self.selection_scope,
            "walk_forward_fingerprint": self.walk_forward_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class RatingTrainingResult:
    artifact: RatingArtifact
    run: BaselineRun


class RatingBaselineTrainer:
    """Sélectionner la conversion Elo sur OOF, sans jamais consulter le test final."""

    def __init__(
        self,
        *,
        code_commit: str,
        search: RatingSearchParameters | None = None,
        calibration_bins: int = 10,
        clock: Clock | None = None,
    ) -> None:
        if _COMMIT.fullmatch(code_commit) is None:
            raise ValueError("code_commit doit être un hash git hexadécimal")
        if calibration_bins < 2:
            raise ValueError("au moins deux bins de calibration sont requis")
        self._code_commit = code_commit
        self._search = search or RatingSearchParameters()
        self._calibration_bins = calibration_bins
        self._clock = clock or SystemClock()

    def train(self, plan: WalkForwardPlan, *, dataset_id: UUID) -> RatingTrainingResult:
        """Évaluer toute la grille sur les mêmes OOF et figer le meilleur log loss."""

        oof_by_scale = {
            scale: self._oof(plan, scale=scale) for scale in self._search.candidate_scales
        }
        metrics = {
            str(scale): evaluate_binary_probabilities(
                _baseline_predictions(oof),
                bin_count=self._calibration_bins,
            )
            for scale, oof in oof_by_scale.items()
        }
        selected_scale = min(
            self._search.candidate_scales,
            key=lambda value: (metrics[str(value)].log_loss, value),
        )
        created_at = self._clock.now().value
        artifact = self._artifact(
            dataset_id=dataset_id,
            plan=plan,
            selected_scale=selected_scale,
            metrics=metrics,
            created_at=created_at,
        )
        run = build_baseline_run(
            dataset_id=dataset_id,
            artifact_id=artifact.artifact_id,
            plan=plan,
            baseline_name=RATING,
            baseline_version=self._search.artifact_version,
            parameters={
                **self._search.document(),
                "artifact_fingerprint": artifact.artifact_fingerprint,
                "selected_scale": str(selected_scale),
            },
            oof=oof_by_scale[selected_scale],
            code_commit=self._code_commit,
            calibration_bins=self._calibration_bins,
            created_at=created_at,
        )
        return RatingTrainingResult(artifact=artifact, run=run)

    def _oof(self, plan: WalkForwardPlan, *, scale: Decimal) -> OutOfFoldPredictions:
        folds = tuple(
            FoldProbabilities(
                fold_index=fold.fold_index,
                probabilities=MappingProxyType(
                    {
                        item.example_id: rating_win_probability(
                            _rating_difference(item, self._search.rating_feature),
                            scale=scale,
                        )
                        for item in fold.validation
                    }
                ),
            )
            for fold in plan.folds
        )
        return collect_oof_predictions(plan, folds)

    def _artifact(
        self,
        *,
        dataset_id: UUID,
        plan: WalkForwardPlan,
        selected_scale: Decimal,
        metrics: Mapping[str, BinaryMetricReport],
        created_at: datetime,
    ) -> RatingArtifact:
        content = {
            "artifact_version": self._search.artifact_version,
            "candidate_metrics": {key: value.document() for key, value in sorted(metrics.items())},
            "candidate_scales": [str(value) for value in self._search.candidate_scales],
            "code_commit": self._code_commit,
            "dataset_id": str(dataset_id),
            "market": GAME_WINNER_MARKET,
            "rating_feature": self._search.rating_feature,
            "selected_scale": str(selected_scale),
            "selection_metric": "log_loss",
            "selection_scope": OOF_VALIDATION,
            "walk_forward_fingerprint": plan.fingerprint,
        }
        fingerprint = _content_hash(content)
        return RatingArtifact(
            artifact_id=uuid5(NAMESPACE_URL, f"metiquo:rating-artifact:{fingerprint}"),
            dataset_id=dataset_id,
            market=GAME_WINNER_MARKET,
            artifact_version=self._search.artifact_version,
            walk_forward_fingerprint=plan.fingerprint,
            rating_feature=self._search.rating_feature,
            selected_scale=selected_scale,
            candidate_scales=self._search.candidate_scales,
            selection_metric="log_loss",
            selection_scope=OOF_VALIDATION,
            candidate_metrics=MappingProxyType(dict(metrics)),
            artifact_fingerprint=fingerprint,
            code_commit=self._code_commit,
            created_at=created_at,
        )


class RatingArtifactRepository:
    """Persister un artefact rating immuable avant son run associé."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def record(self, artifact: RatingArtifact) -> RatingArtifact:
        _validate_artifact(artifact)
        artifacts = cast(Table, RatingArtifactRow.__table__)
        with self._engine.begin() as connection:
            connection.execute(
                insert(artifacts)
                .values(
                    id=artifact.artifact_id,
                    dataset_id=artifact.dataset_id,
                    market=artifact.market,
                    artifact_version=artifact.artifact_version,
                    walk_forward_fingerprint=artifact.walk_forward_fingerprint,
                    rating_feature=artifact.rating_feature,
                    selected_scale=artifact.selected_scale,
                    candidate_scales=[str(value) for value in artifact.candidate_scales],
                    selection_metric=artifact.selection_metric,
                    selection_scope=artifact.selection_scope,
                    candidate_metrics={
                        key: value.document()
                        for key, value in sorted(artifact.candidate_metrics.items())
                    },
                    artifact_fingerprint=artifact.artifact_fingerprint,
                    code_commit=artifact.code_commit,
                    created_at=artifact.created_at,
                )
                .on_conflict_do_nothing(index_elements=[artifacts.c.artifact_fingerprint])
            )
        stored = self.get_by_fingerprint(artifact.artifact_fingerprint)
        if stored is None:
            raise RuntimeError("l'artefact rating n'a pas été enregistré")
        return stored

    def get(self, artifact_id: UUID) -> RatingArtifact | None:
        artifacts = cast(Table, RatingArtifactRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(artifacts).where(artifacts.c.id == artifact_id))
                .mappings()
                .one_or_none()
            )
        return self._stored(row) if row is not None else None

    def get_by_fingerprint(self, fingerprint: str) -> RatingArtifact | None:
        artifacts = cast(Table, RatingArtifactRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(artifacts).where(artifacts.c.artifact_fingerprint == fingerprint)
                )
                .mappings()
                .one_or_none()
            )
        return self._stored(row) if row is not None else None

    @staticmethod
    def _stored(row: RowMapping) -> RatingArtifact:
        documents = cast(Mapping[str, Mapping[str, object]], row["candidate_metrics"])
        return RatingArtifact(
            artifact_id=cast(UUID, row["id"]),
            dataset_id=cast(UUID, row["dataset_id"]),
            market=cast(str, row["market"]),
            artifact_version=cast(str, row["artifact_version"]),
            walk_forward_fingerprint=cast(str, row["walk_forward_fingerprint"]),
            rating_feature=cast(str, row["rating_feature"]),
            selected_scale=cast(Decimal, row["selected_scale"]),
            candidate_scales=tuple(
                Decimal(value) for value in cast(list[str], row["candidate_scales"])
            ),
            selection_metric=cast(str, row["selection_metric"]),
            selection_scope=cast(str, row["selection_scope"]),
            candidate_metrics=MappingProxyType(
                {key: _metrics_from_document(value) for key, value in documents.items()}
            ),
            artifact_fingerprint=cast(str, row["artifact_fingerprint"]),
            code_commit=cast(str, row["code_commit"]),
            created_at=cast(datetime, row["created_at"]),
        )


def rating_win_probability(rating_difference: Decimal, *, scale: Decimal) -> Decimal:
    """Convertir un écart pré-game en probabilité Elo bornée et symétrique."""

    if not rating_difference.is_finite():
        raise ValueError("l'écart de rating doit être fini")
    normalized_scale = _scale(scale)
    if not normalized_scale.is_finite() or normalized_scale <= 0:
        raise ValueError("l'échelle de probabilité doit être finie et positive")
    ratio = rating_difference / normalized_scale
    if ratio >= 100:
        return Decimal(1)
    if ratio <= -100:
        return Decimal()
    probability = 1.0 / (1.0 + math.pow(10.0, -float(ratio)))
    return Decimal(str(probability)).quantize(_PROBABILITY_QUANTUM, rounding=ROUND_HALF_EVEN)


def _rating_difference(example: WalkForwardExample, field: str) -> Decimal:
    value = example.feature_values.get(field)
    if value is None or isinstance(value, bool):
        raise ValueError(f"feature rating requise absente: {field}")
    try:
        difference = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"feature rating invalide: {field}") from error
    if not difference.is_finite():
        raise ValueError(f"feature rating non finie: {field}")
    return difference


def _baseline_predictions(oof: OutOfFoldPredictions) -> tuple[BaselinePrediction, ...]:
    return tuple(
        BaselinePrediction(
            example_id=item.example_id,
            fold_index=item.fold_index,
            cutoff_at=item.cutoff_at,
            label=item.label,
            probability=item.probability,
        )
        for item in oof.predictions
    )


def _validate_artifact(artifact: RatingArtifact) -> None:
    if artifact.market != GAME_WINNER_MARKET:
        raise ValueError("seul le marché game_winner est pris en charge")
    if artifact.rating_feature != RATING_FEATURE:
        raise ValueError("la feature rating de l'artefact est invalide")
    if artifact.selection_metric != "log_loss" or artifact.selection_scope != OOF_VALIDATION:
        raise ValueError("la sélection rating doit utiliser le log loss OOF")
    if artifact.selected_scale not in artifact.candidate_scales:
        raise ValueError("l'échelle sélectionnée doit appartenir à la grille")
    if set(artifact.candidate_metrics) != {str(value) for value in artifact.candidate_scales}:
        raise ValueError("chaque échelle candidate exige ses métriques")
    sample_counts = {item.sample_count for item in artifact.candidate_metrics.values()}
    if len(sample_counts) != 1 or next(iter(sample_counts), 0) < 1:
        raise ValueError("les candidates doivent couvrir le même échantillon OOF non vide")
    expected_scale = min(
        artifact.candidate_scales,
        key=lambda value: (artifact.candidate_metrics[str(value)].log_loss, value),
    )
    if artifact.selected_scale != expected_scale:
        raise ValueError("l'échelle sélectionnée n'est pas le meilleur log loss OOF")
    if not _FINGERPRINT.fullmatch(artifact.walk_forward_fingerprint):
        raise ValueError("fingerprint walk-forward invalide")
    if _COMMIT.fullmatch(artifact.code_commit) is None:
        raise ValueError("code_commit invalide")
    fingerprint = _content_hash(artifact.content_document())
    if artifact.artifact_fingerprint != fingerprint:
        raise ValueError("le fingerprint de l'artefact ne correspond pas à son contenu")
    expected_id = uuid5(NAMESPACE_URL, f"metiquo:rating-artifact:{fingerprint}")
    if artifact.artifact_id != expected_id:
        raise ValueError("l'identifiant de l'artefact ne correspond pas à son fingerprint")


def _metrics_from_document(document: Mapping[str, object]) -> BinaryMetricReport:
    from metiquo.models.baselines import ReliabilityBin

    calibration = cast(Mapping[str, object], document["calibration"])
    reliability = cast(list[Mapping[str, object]], calibration["reliability"])
    return BinaryMetricReport(
        sample_count=int(cast(int, document["sample_count"])),
        log_loss=Decimal(cast(str, document["log_loss"])),
        brier_score=Decimal(cast(str, document["brier_score"])),
        calibration_ece=Decimal(cast(str, calibration["ece"])),
        calibration_bins=tuple(
            ReliabilityBin(
                lower_bound=Decimal(cast(str, item["lower_bound"])),
                upper_bound=Decimal(cast(str, item["upper_bound"])),
                count=int(cast(int, item["count"])),
                mean_probability=Decimal(cast(str, item["mean_probability"])),
                observed_frequency=Decimal(cast(str, item["observed_frequency"])),
                absolute_gap=Decimal(cast(str, item["absolute_gap"])),
            )
            for item in reliability
        ),
        bin_count=int(cast(int, calibration["bin_count"])),
    )


def _scale(value: Decimal) -> Decimal:
    if not value.is_finite():
        return value
    try:
        return value.quantize(_SCALE_QUANTUM, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as error:
        raise ValueError("l'échelle de probabilité doit être représentable") from error


def _content_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
