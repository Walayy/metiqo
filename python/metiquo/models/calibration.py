"""Calibration temporelle de second niveau, séparée du modèle source."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import groupby
from types import MappingProxyType
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sklearn.isotonic import IsotonicRegression  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sqlalchemy import Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.ml_models import CalibratorArtifact as CalibratorArtifactRow
from metiquo.db.ml_models import CalibratorOosPrediction as CalibratorOosPredictionRow
from metiquo.db.ml_models import TrainingDatasetExample
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime
from metiquo.models.baselines import (
    BaselinePrediction,
    BinaryMetricReport,
    binary_metric_report_from_document,
    evaluate_binary_probabilities,
)
from metiquo.models.benchmark import TabularBenchmarkRun
from metiquo.models.datasets import GAME_WINNER_MARKET
from metiquo.models.ensemble import EnsembleCandidateRun
from metiquo.models.validation import WalkForwardPlan

PLATT = "platt"
ISOTONIC = "isotonic"
CALIBRATOR_VERSION = "temporal-oos-calibrator-v1"
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_METRIC_QUANTUM = Decimal("0.000001")
_EPSILON = 0.00000001


@dataclass(frozen=True, slots=True)
class CalibrationSearchParameters:
    minimum_fit_periods: int = 10
    validation_periods: int = 5
    calibration_bins: int = 10
    segment_min_samples: int = 10
    drift_ece_threshold: Decimal = Decimal("0.150000")
    seed: int = 20260906
    version: str = CALIBRATOR_VERSION

    def __post_init__(self) -> None:
        if (
            min(
                self.minimum_fit_periods,
                self.validation_periods,
                self.segment_min_samples,
            )
            < 1
        ):
            raise ValueError("les fenêtres et échantillons de calibration doivent être positifs")
        if self.calibration_bins < 2 or self.seed < 0:
            raise ValueError("bins ou seed de calibration invalides")
        if not self.drift_ece_threshold.is_finite() or not 0 <= self.drift_ece_threshold <= 1:
            raise ValueError("le seuil ECE de dérive doit être dans [0,1]")
        if not self.version.strip():
            raise ValueError("la version du calibrateur est requise")

    def document(self) -> dict[str, object]:
        return {
            "calibration_bins": self.calibration_bins,
            "drift_ece_threshold": str(self.drift_ece_threshold),
            "minimum_fit_periods": self.minimum_fit_periods,
            "segment_min_samples": self.segment_min_samples,
            "seed": self.seed,
            "validation_periods": self.validation_periods,
        }


@dataclass(frozen=True, slots=True)
class CalibrationCandidateEvaluation:
    method: str
    metrics: BinaryMetricReport
    calibration_slope: Decimal
    calibration_intercept: Decimal
    oos_predictions_fingerprint: str

    def document(self) -> dict[str, object]:
        return {
            "calibration_intercept": str(self.calibration_intercept),
            "calibration_slope": str(self.calibration_slope),
            "method": self.method,
            "metrics": self.metrics.document(),
            "oos_predictions_fingerprint": self.oos_predictions_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class CalibrationSegmentReport:
    dimension: str
    value: str
    sample_count: int
    metrics: BinaryMetricReport
    low_sample: bool
    drift_detected: bool

    def document(self) -> dict[str, object]:
        return {
            "dimension": self.dimension,
            "drift_detected": self.drift_detected,
            "low_sample": self.low_sample,
            "metrics": self.metrics.document(),
            "sample_count": self.sample_count,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class CalibratorArtifact:
    artifact_id: UUID
    dataset_id: UUID
    benchmark_run_id: UUID
    ensemble_run_id: UUID | None
    market: str
    source_kind: str
    calibrator_version: str
    walk_forward_fingerprint: str
    method: str
    parameters: Mapping[str, object]
    search: CalibrationSearchParameters
    candidate_evaluations: Mapping[str, CalibrationCandidateEvaluation]
    metrics: BinaryMetricReport
    calibration_slope: Decimal
    calibration_intercept: Decimal
    segment_reports: tuple[CalibrationSegmentReport, ...]
    oos_predictions_fingerprint: str
    artifact_fingerprint: str
    code_commit: str
    created_at: datetime
    oos_predictions: tuple[BaselinePrediction, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", normalize_utc_datetime(self.created_at))

    def calibrate(self, probability: Decimal) -> Decimal:
        """Appliquer l'artefact de déploiement à une probabilité brute."""

        if not probability.is_finite() or not 0 <= probability <= 1:
            raise ValueError("la probabilité brute doit être dans [0,1]")
        return _stored_probability(_apply_parameters(self.method, self.parameters, probability))


class CalibratorTrainer:
    """Comparer Platt et isotonic sur des blocs futurs distincts du fit."""

    def __init__(
        self,
        *,
        code_commit: str,
        search: CalibrationSearchParameters | None = None,
        clock: Clock | None = None,
    ) -> None:
        if _COMMIT.fullmatch(code_commit) is None:
            raise ValueError("code_commit doit être un hash git hexadécimal")
        self._code_commit = code_commit
        self._search = search or CalibrationSearchParameters()
        self._clock = clock or SystemClock()

    def train(
        self,
        plan: WalkForwardPlan,
        *,
        benchmark: TabularBenchmarkRun,
        ensemble: EnsembleCandidateRun,
    ) -> CalibratorArtifact:
        source_kind = "ensemble" if ensemble.enabled else "tabular"
        source = ensemble.predictions if ensemble.enabled else benchmark.predictions
        ensemble_run_id = ensemble.run_id if ensemble.enabled else None
        if (
            benchmark.dataset_id != ensemble.dataset_id
            or benchmark.run_id != ensemble.benchmark_run_id
            or benchmark.walk_forward_fingerprint != plan.fingerprint
            or ensemble.walk_forward_fingerprint != plan.fingerprint
        ):
            raise ValueError("plan, benchmark et ensemble doivent partager le même périmètre")
        allowed = {item.example_id for item in plan.oof_validation}
        final_ids = {item.example_id for item in plan.final_test}
        source_ids = {item.example_id for item in source}
        if source_ids != allowed or source_ids & final_ids:
            raise ValueError("la calibration est limitée aux prédictions OOF hors test final")

        prediction_sets = {
            method: _temporal_oos_predictions(
                source,
                method=method,
                search=self._search,
            )
            for method in (PLATT, ISOTONIC)
        }
        candidates = {
            method: _candidate_evaluation(
                method,
                predictions,
                calibration_bins=self._search.calibration_bins,
                seed=self._search.seed,
            )
            for method, predictions in prediction_sets.items()
        }
        selected_method = min(
            candidates,
            key=lambda method: (
                candidates[method].metrics.log_loss,
                candidates[method].metrics.calibration_ece,
                candidates[method].metrics.brier_score,
                method,
            ),
        )
        selected = candidates[selected_method]
        oos_predictions = prediction_sets[selected_method]
        parameters = _fit_parameters(
            selected_method,
            source,
            seed=self._search.seed,
        )
        segments = evaluate_calibration_segments(
            oos_predictions,
            plan=plan,
            bin_count=self._search.calibration_bins,
            minimum_sample=self._search.segment_min_samples,
            drift_ece_threshold=self._search.drift_ece_threshold,
        )
        predictions_fingerprint = _content_hash([item.document() for item in oos_predictions])
        content = _artifact_content(
            dataset_id=benchmark.dataset_id,
            benchmark_run_id=benchmark.run_id,
            ensemble_run_id=ensemble_run_id,
            market=GAME_WINNER_MARKET,
            source_kind=source_kind,
            calibrator_version=self._search.version,
            walk_forward_fingerprint=plan.fingerprint,
            method=selected_method,
            parameters=parameters,
            search=self._search,
            candidate_evaluations=candidates,
            metrics=selected.metrics,
            calibration_slope=selected.calibration_slope,
            calibration_intercept=selected.calibration_intercept,
            segment_reports=segments,
            oos_predictions_fingerprint=predictions_fingerprint,
            code_commit=self._code_commit,
        )
        fingerprint = _content_hash(content)
        return CalibratorArtifact(
            artifact_id=uuid5(NAMESPACE_URL, f"metiquo:calibrator:{fingerprint}"),
            dataset_id=benchmark.dataset_id,
            benchmark_run_id=benchmark.run_id,
            ensemble_run_id=ensemble_run_id,
            market=GAME_WINNER_MARKET,
            source_kind=source_kind,
            calibrator_version=self._search.version,
            walk_forward_fingerprint=plan.fingerprint,
            method=selected_method,
            parameters=MappingProxyType(parameters),
            search=self._search,
            candidate_evaluations=MappingProxyType(candidates),
            metrics=selected.metrics,
            calibration_slope=selected.calibration_slope,
            calibration_intercept=selected.calibration_intercept,
            segment_reports=segments,
            oos_predictions_fingerprint=predictions_fingerprint,
            artifact_fingerprint=fingerprint,
            code_commit=self._code_commit,
            created_at=self._clock.now().value,
            oos_predictions=oos_predictions,
        )


def _temporal_oos_predictions(
    source: Sequence[BaselinePrediction],
    *,
    method: str,
    search: CalibrationSearchParameters,
) -> tuple[BaselinePrediction, ...]:
    ordered = tuple(sorted(source, key=lambda item: (item.cutoff_at, item.example_id)))
    periods = tuple(
        tuple(group) for _key, group in groupby(ordered, key=lambda item: item.cutoff_at)
    )
    if len(periods) <= search.minimum_fit_periods:
        raise ValueError("pas assez de périodes OOF pour séparer fit et validation calibration")
    predictions: list[BaselinePrediction] = []
    cursor = search.minimum_fit_periods
    calibration_fold = 0
    while cursor < len(periods):
        validation_end = min(cursor + search.validation_periods, len(periods))
        train = tuple(item for period in periods[:cursor] for item in period)
        validation = tuple(item for period in periods[cursor:validation_end] for item in period)
        if max(item.cutoff_at for item in train) >= min(item.cutoff_at for item in validation):
            raise ValueError("le fit du calibrateur doit précéder strictement sa validation")
        parameters = _fit_parameters(method, train, seed=search.seed)
        predictions.extend(
            BaselinePrediction(
                example_id=item.example_id,
                fold_index=calibration_fold,
                cutoff_at=item.cutoff_at,
                label=item.label,
                probability=_apply_parameters(method, parameters, item.probability),
            )
            for item in validation
        )
        calibration_fold += 1
        cursor = validation_end
    return tuple(predictions)


def _fit_parameters(
    method: str,
    source: Sequence[BaselinePrediction],
    *,
    seed: int,
) -> dict[str, object]:
    if not source:
        raise ValueError("un calibrateur exige des prédictions de fit")
    labels = [int(item.label) for item in source]
    if method == PLATT:
        if len(set(labels)) < 2:
            probability = (sum(labels) + 0.5) / (len(labels) + 1)
            return {
                "coefficient": "0.000000",
                "intercept": str(_metric(Decimal(str(_logit(probability))))),
            }
        model = LogisticRegression(
            C=1_000_000,
            max_iter=1_000,
            random_state=seed,
            solver="lbfgs",
        )
        model.fit([[_logit(float(item.probability))] for item in source], labels)
        coefficient = float(cast(Sequence[Sequence[float]], model.coef_)[0][0])
        intercept = float(cast(Sequence[float], model.intercept_)[0])
        return {
            "coefficient": str(_metric(Decimal(str(coefficient)))),
            "intercept": str(_metric(Decimal(str(intercept)))),
        }
    if method == ISOTONIC:
        model = IsotonicRegression(
            increasing=True,
            out_of_bounds="clip",
            y_min=_EPSILON,
            y_max=1 - _EPSILON,
        )
        model.fit([float(item.probability) for item in source], labels)
        x_thresholds = cast(Sequence[float], model.X_thresholds_)
        y_thresholds = cast(Sequence[float], model.y_thresholds_)
        return {
            "x_thresholds": [
                str(_stored_probability(Decimal(str(value)))) for value in x_thresholds
            ],
            "y_thresholds": [
                str(_stored_probability(Decimal(str(value)))) for value in y_thresholds
            ],
        }
    raise ValueError(f"méthode de calibration inconnue: {method}")


def _apply_parameters(
    method: str,
    parameters: Mapping[str, object],
    probability: Decimal,
) -> Decimal:
    value = min(max(float(probability), _EPSILON), 1 - _EPSILON)
    if method == PLATT:
        coefficient = float(cast(str, parameters["coefficient"]))
        intercept = float(cast(str, parameters["intercept"]))
        return Decimal(str(_sigmoid(coefficient * _logit(value) + intercept)))
    if method == ISOTONIC:
        xs = [float(value) for value in cast(Sequence[str], parameters["x_thresholds"])]
        ys = [float(value) for value in cast(Sequence[str], parameters["y_thresholds"])]
        if len(xs) != len(ys) or not xs:
            raise ValueError("paramètres isotoniques invalides")
        if value <= xs[0]:
            return Decimal(str(ys[0]))
        if value >= xs[-1]:
            return Decimal(str(ys[-1]))
        for index in range(1, len(xs)):
            if value <= xs[index]:
                width = xs[index] - xs[index - 1]
                if width == 0:
                    return Decimal(str(ys[index]))
                ratio = (value - xs[index - 1]) / width
                return Decimal(str(ys[index - 1] + ratio * (ys[index] - ys[index - 1])))
    raise ValueError(f"méthode de calibration inconnue: {method}")


def _candidate_evaluation(
    method: str,
    predictions: tuple[BaselinePrediction, ...],
    *,
    calibration_bins: int,
    seed: int,
) -> CalibrationCandidateEvaluation:
    slope, intercept = _calibration_regression(predictions, seed=seed)
    return CalibrationCandidateEvaluation(
        method=method,
        metrics=evaluate_binary_probabilities(predictions, bin_count=calibration_bins),
        calibration_slope=slope,
        calibration_intercept=intercept,
        oos_predictions_fingerprint=_content_hash([item.document() for item in predictions]),
    )


def _calibration_regression(
    predictions: Sequence[BaselinePrediction],
    *,
    seed: int,
) -> tuple[Decimal, Decimal]:
    labels = [int(item.label) for item in predictions]
    if len(set(labels)) < 2:
        probability = (sum(labels) + 0.5) / (len(labels) + 1)
        return Decimal(), _metric(Decimal(str(_logit(probability))))
    model = LogisticRegression(
        C=1_000_000,
        max_iter=1_000,
        random_state=seed,
        solver="lbfgs",
    )
    model.fit([[_logit(float(item.probability))] for item in predictions], labels)
    slope = float(cast(Sequence[Sequence[float]], model.coef_)[0][0])
    intercept = float(cast(Sequence[float], model.intercept_)[0])
    return _metric(Decimal(str(slope))), _metric(Decimal(str(intercept)))


def evaluate_calibration_segments(
    predictions: Sequence[BaselinePrediction],
    *,
    plan: WalkForwardPlan,
    bin_count: int,
    minimum_sample: int,
    drift_ece_threshold: Decimal,
) -> tuple[CalibrationSegmentReport, ...]:
    """Calculer les métriques par patch et compétition, avec compteurs explicites."""

    examples = {item.example_id: item for item in plan.oof_validation}
    grouped: dict[tuple[str, str], list[BaselinePrediction]] = {}
    for prediction in predictions:
        example = examples.get(prediction.example_id)
        if example is None:
            raise ValueError("une prédiction calibrée est extérieure aux OOF du plan")
        values = (
            ("patch", example.patch or "unknown"),
            (
                "competition",
                str(example.competition_id) if example.competition_id is not None else "unknown",
            ),
        )
        for dimension, value in values:
            grouped.setdefault((dimension, value), []).append(prediction)
    reports: list[CalibrationSegmentReport] = []
    for (dimension, value), items in sorted(grouped.items()):
        metrics = evaluate_binary_probabilities(items, bin_count=bin_count)
        reports.append(
            CalibrationSegmentReport(
                dimension=dimension,
                value=value,
                sample_count=len(items),
                metrics=metrics,
                low_sample=len(items) < minimum_sample,
                drift_detected=(
                    len(items) >= minimum_sample and metrics.calibration_ece > drift_ece_threshold
                ),
            )
        )
    return tuple(reports)


class CalibratorArtifactRepository:
    """Persister séparément calibrateur et preuve de sélection OOS."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def record(self, artifact: CalibratorArtifact) -> CalibratorArtifact:
        _validate_artifact(artifact)
        artifacts = cast(Table, CalibratorArtifactRow.__table__)
        predictions = cast(Table, CalibratorOosPredictionRow.__table__)
        dataset_examples = cast(Table, TrainingDatasetExample.__table__)
        with self._engine.begin() as connection:
            allowed_ids = set(
                connection.execute(
                    select(dataset_examples.c.event_id).where(
                        dataset_examples.c.dataset_id == artifact.dataset_id
                    )
                ).scalars()
            )
            if not {item.example_id for item in artifact.oos_predictions} <= allowed_ids:
                raise ValueError("le calibrateur ne peut référencer que son dataset")
            inserted = connection.execute(
                insert(artifacts)
                .values(
                    id=artifact.artifact_id,
                    dataset_id=artifact.dataset_id,
                    benchmark_run_id=artifact.benchmark_run_id,
                    ensemble_run_id=artifact.ensemble_run_id,
                    market=artifact.market,
                    source_kind=artifact.source_kind,
                    calibrator_version=artifact.calibrator_version,
                    walk_forward_fingerprint=artifact.walk_forward_fingerprint,
                    method=artifact.method,
                    parameters={
                        "deployment": dict(artifact.parameters),
                        "search": artifact.search.document(),
                    },
                    candidate_evaluations={
                        key: value.document()
                        for key, value in sorted(artifact.candidate_evaluations.items())
                    },
                    metrics=artifact.metrics.document(),
                    calibration_slope=artifact.calibration_slope,
                    calibration_intercept=artifact.calibration_intercept,
                    segment_reports=[item.document() for item in artifact.segment_reports],
                    oos_prediction_count=len(artifact.oos_predictions),
                    oos_predictions_fingerprint=artifact.oos_predictions_fingerprint,
                    artifact_fingerprint=artifact.artifact_fingerprint,
                    code_commit=artifact.code_commit,
                    created_at=artifact.created_at,
                )
                .on_conflict_do_nothing(index_elements=[artifacts.c.artifact_fingerprint])
                .returning(artifacts.c.id)
            ).scalar_one_or_none()
            if inserted is not None:
                connection.execute(
                    insert(predictions),
                    [
                        {
                            "artifact_id": artifact.artifact_id,
                            "position": position,
                            "example_id": item.example_id,
                            "fold_index": item.fold_index,
                            "cutoff_at": item.cutoff_at,
                            "label": item.label,
                            "probability": item.probability,
                        }
                        for position, item in enumerate(artifact.oos_predictions)
                    ],
                )
        stored = self.get_by_fingerprint(artifact.artifact_fingerprint)
        if stored is None:
            raise RuntimeError("le calibrateur n'a pas été enregistré")
        return stored

    def get(self, artifact_id: UUID) -> CalibratorArtifact | None:
        artifacts = cast(Table, CalibratorArtifactRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(artifacts).where(artifacts.c.id == artifact_id))
                .mappings()
                .one_or_none()
            )
        return self._stored(row) if row is not None else None

    def get_by_fingerprint(self, fingerprint: str) -> CalibratorArtifact | None:
        artifacts = cast(Table, CalibratorArtifactRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(artifacts).where(artifacts.c.artifact_fingerprint == fingerprint)
                )
                .mappings()
                .one_or_none()
            )
        return self._stored(row) if row is not None else None

    def _stored(self, row: RowMapping) -> CalibratorArtifact:
        predictions = cast(Table, CalibratorOosPredictionRow.__table__)
        with self._engine.connect() as connection:
            prediction_rows = (
                connection.execute(
                    select(predictions)
                    .where(predictions.c.artifact_id == row["id"])
                    .order_by(predictions.c.position)
                )
                .mappings()
                .all()
            )
        parameter_document = cast(Mapping[str, object], row["parameters"])
        search_document = cast(Mapping[str, object], parameter_document["search"])
        candidate_documents = cast(Mapping[str, Mapping[str, object]], row["candidate_evaluations"])
        segment_documents = cast(Sequence[Mapping[str, object]], row["segment_reports"])
        return CalibratorArtifact(
            artifact_id=cast(UUID, row["id"]),
            dataset_id=cast(UUID, row["dataset_id"]),
            benchmark_run_id=cast(UUID, row["benchmark_run_id"]),
            ensemble_run_id=cast(UUID | None, row["ensemble_run_id"]),
            market=cast(str, row["market"]),
            source_kind=cast(str, row["source_kind"]),
            calibrator_version=cast(str, row["calibrator_version"]),
            walk_forward_fingerprint=cast(str, row["walk_forward_fingerprint"]),
            method=cast(str, row["method"]),
            parameters=MappingProxyType(
                dict(cast(Mapping[str, object], parameter_document["deployment"]))
            ),
            search=_search_from_document(
                search_document,
                version=cast(str, row["calibrator_version"]),
            ),
            candidate_evaluations=MappingProxyType(
                {key: _candidate_from_document(value) for key, value in candidate_documents.items()}
            ),
            metrics=binary_metric_report_from_document(cast(Mapping[str, object], row["metrics"])),
            calibration_slope=cast(Decimal, row["calibration_slope"]),
            calibration_intercept=cast(Decimal, row["calibration_intercept"]),
            segment_reports=tuple(_segment_from_document(value) for value in segment_documents),
            oos_predictions_fingerprint=cast(str, row["oos_predictions_fingerprint"]),
            artifact_fingerprint=cast(str, row["artifact_fingerprint"]),
            code_commit=cast(str, row["code_commit"]),
            created_at=cast(datetime, row["created_at"]),
            oos_predictions=tuple(
                BaselinePrediction(
                    example_id=cast(UUID, item["example_id"]),
                    fold_index=cast(int, item["fold_index"]),
                    cutoff_at=cast(datetime, item["cutoff_at"]),
                    label=cast(bool, item["label"]),
                    probability=cast(Decimal, item["probability"]),
                )
                for item in prediction_rows
            ),
        )


def _validate_artifact(artifact: CalibratorArtifact) -> None:
    if artifact.market != GAME_WINNER_MARKET or artifact.method not in {PLATT, ISOTONIC}:
        raise ValueError("marché ou méthode de calibration invalide")
    if artifact.source_kind == "tabular":
        if artifact.ensemble_run_id is not None:
            raise ValueError("une source tabulaire ne référence pas un ensemble")
    elif artifact.source_kind == "ensemble":
        if artifact.ensemble_run_id is None:
            raise ValueError("une source ensemble exige son run")
    else:
        raise ValueError("source de calibration invalide")
    if set(artifact.candidate_evaluations) != {PLATT, ISOTONIC}:
        raise ValueError("Platt et isotonic doivent être comparés")
    selected = artifact.candidate_evaluations[artifact.method]
    if (
        selected.metrics != artifact.metrics
        or selected.calibration_slope != artifact.calibration_slope
        or selected.calibration_intercept != artifact.calibration_intercept
    ):
        raise ValueError("le candidat sélectionné ne correspond pas à l'artefact")
    expected_method = min(
        artifact.candidate_evaluations,
        key=lambda method: (
            artifact.candidate_evaluations[method].metrics.log_loss,
            artifact.candidate_evaluations[method].metrics.calibration_ece,
            artifact.candidate_evaluations[method].metrics.brier_score,
            method,
        ),
    )
    if expected_method != artifact.method:
        raise ValueError("la méthode choisie ne correspond pas aux métriques OOS")
    metrics = evaluate_binary_probabilities(
        artifact.oos_predictions,
        bin_count=artifact.metrics.bin_count,
    )
    if metrics != artifact.metrics:
        raise ValueError("les métriques ne correspondent pas aux probabilités calibrées")
    if (
        _content_hash([item.document() for item in artifact.oos_predictions])
        != artifact.oos_predictions_fingerprint
    ):
        raise ValueError("le fingerprint des prédictions calibrées est invalide")
    for value in (
        artifact.walk_forward_fingerprint,
        artifact.oos_predictions_fingerprint,
        artifact.artifact_fingerprint,
    ):
        if _FINGERPRINT.fullmatch(value) is None:
            raise ValueError("fingerprint du calibrateur invalide")
    if _COMMIT.fullmatch(artifact.code_commit) is None:
        raise ValueError("commit du calibrateur invalide")
    fingerprint = _content_hash(
        _artifact_content(
            dataset_id=artifact.dataset_id,
            benchmark_run_id=artifact.benchmark_run_id,
            ensemble_run_id=artifact.ensemble_run_id,
            market=artifact.market,
            source_kind=artifact.source_kind,
            calibrator_version=artifact.calibrator_version,
            walk_forward_fingerprint=artifact.walk_forward_fingerprint,
            method=artifact.method,
            parameters=artifact.parameters,
            search=artifact.search,
            candidate_evaluations=artifact.candidate_evaluations,
            metrics=artifact.metrics,
            calibration_slope=artifact.calibration_slope,
            calibration_intercept=artifact.calibration_intercept,
            segment_reports=artifact.segment_reports,
            oos_predictions_fingerprint=artifact.oos_predictions_fingerprint,
            code_commit=artifact.code_commit,
        )
    )
    if fingerprint != artifact.artifact_fingerprint:
        raise ValueError("le fingerprint du calibrateur ne correspond pas à son contenu")
    if artifact.artifact_id != uuid5(NAMESPACE_URL, f"metiquo:calibrator:{fingerprint}"):
        raise ValueError("l'identifiant du calibrateur est invalide")


def _artifact_content(
    *,
    dataset_id: UUID,
    benchmark_run_id: UUID,
    ensemble_run_id: UUID | None,
    market: str,
    source_kind: str,
    calibrator_version: str,
    walk_forward_fingerprint: str,
    method: str,
    parameters: Mapping[str, object],
    search: CalibrationSearchParameters,
    candidate_evaluations: Mapping[str, CalibrationCandidateEvaluation],
    metrics: BinaryMetricReport,
    calibration_slope: Decimal,
    calibration_intercept: Decimal,
    segment_reports: Sequence[CalibrationSegmentReport],
    oos_predictions_fingerprint: str,
    code_commit: str,
) -> dict[str, object]:
    return {
        "benchmark_run_id": str(benchmark_run_id),
        "calibration_intercept": str(calibration_intercept),
        "calibration_slope": str(calibration_slope),
        "calibrator_version": calibrator_version,
        "candidate_evaluations": {
            key: value.document() for key, value in sorted(candidate_evaluations.items())
        },
        "code_commit": code_commit,
        "dataset_id": str(dataset_id),
        "ensemble_run_id": str(ensemble_run_id) if ensemble_run_id is not None else None,
        "market": market,
        "method": method,
        "metrics": metrics.document(),
        "oos_predictions_fingerprint": oos_predictions_fingerprint,
        "parameters": dict(parameters),
        "search": search.document(),
        "segment_reports": [item.document() for item in segment_reports],
        "source_kind": source_kind,
        "walk_forward_fingerprint": walk_forward_fingerprint,
    }


def _search_from_document(
    document: Mapping[str, object],
    *,
    version: str,
) -> CalibrationSearchParameters:
    return CalibrationSearchParameters(
        minimum_fit_periods=int(cast(int, document["minimum_fit_periods"])),
        validation_periods=int(cast(int, document["validation_periods"])),
        calibration_bins=int(cast(int, document["calibration_bins"])),
        segment_min_samples=int(cast(int, document["segment_min_samples"])),
        drift_ece_threshold=Decimal(cast(str, document["drift_ece_threshold"])),
        seed=int(cast(int, document["seed"])),
        version=version,
    )


def _candidate_from_document(
    document: Mapping[str, object],
) -> CalibrationCandidateEvaluation:
    return CalibrationCandidateEvaluation(
        method=cast(str, document["method"]),
        metrics=binary_metric_report_from_document(cast(Mapping[str, object], document["metrics"])),
        calibration_slope=Decimal(cast(str, document["calibration_slope"])),
        calibration_intercept=Decimal(cast(str, document["calibration_intercept"])),
        oos_predictions_fingerprint=cast(str, document["oos_predictions_fingerprint"]),
    )


def _segment_from_document(document: Mapping[str, object]) -> CalibrationSegmentReport:
    return CalibrationSegmentReport(
        dimension=cast(str, document["dimension"]),
        value=cast(str, document["value"]),
        sample_count=int(cast(int, document["sample_count"])),
        metrics=binary_metric_report_from_document(cast(Mapping[str, object], document["metrics"])),
        low_sample=cast(bool, document["low_sample"]),
        drift_detected=cast(bool, document["drift_detected"]),
    )


def _logit(probability: float) -> float:
    clipped = min(max(probability, _EPSILON), 1 - _EPSILON)
    return math.log(clipped / (1 - clipped))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1 + exponential)


def _stored_probability(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)


def _metric(value: Decimal) -> Decimal:
    return value.quantize(_METRIC_QUANTUM, rounding=ROUND_HALF_EVEN)


def _content_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
