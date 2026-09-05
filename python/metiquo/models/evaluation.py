"""Rapport probabiliste complet, segmenté et auditable."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

from metiquo.models.baselines import BaselinePrediction, evaluate_binary_probabilities
from metiquo.models.calibration import CalibratorArtifact
from metiquo.models.uncertainty import UncertaintyArtifact
from metiquo.models.validation import WalkForwardExample, WalkForwardPlan

EVALUATION_REPORT_VERSION = "probabilistic-segment-report-v1"
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_QUANTUM = Decimal("0.000001")
_LOG_EPSILON = 0.00000001


@dataclass(frozen=True, slots=True)
class EvaluationReportParameters:
    calibration_bins: int = 10
    minimum_segment_samples: int = 30
    log_loss_drift_threshold: Decimal = Decimal("0.100000")
    calibration_drift_threshold: Decimal = Decimal("0.100000")
    interval_coverage_drift_threshold: Decimal = Decimal("0.100000")
    abstention_drift_threshold: Decimal = Decimal("0.100000")
    outsider_probability_threshold: Decimal = Decimal("0.500000")
    version: str = EVALUATION_REPORT_VERSION

    def __post_init__(self) -> None:
        if self.calibration_bins < 2 or self.minimum_segment_samples < 1:
            raise ValueError("bins et taille minimale de segment invalides")
        probabilities = (
            self.log_loss_drift_threshold,
            self.calibration_drift_threshold,
            self.interval_coverage_drift_threshold,
            self.abstention_drift_threshold,
            self.outsider_probability_threshold,
        )
        if any(not value.is_finite() or not 0 <= value <= 1 for value in probabilities):
            raise ValueError("les seuils du rapport doivent être finis dans [0,1]")
        if not self.version.strip():
            raise ValueError("la version du rapport est requise")

    def document(self) -> dict[str, object]:
        return {
            "abstention_drift_threshold": str(self.abstention_drift_threshold),
            "calibration_bins": self.calibration_bins,
            "calibration_drift_threshold": str(self.calibration_drift_threshold),
            "interval_coverage_drift_threshold": str(self.interval_coverage_drift_threshold),
            "log_loss_drift_threshold": str(self.log_loss_drift_threshold),
            "minimum_segment_samples": self.minimum_segment_samples,
            "outsider_probability_threshold": str(self.outsider_probability_threshold),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """Contexte disponible au cutoff, sans cote inventée."""

    data_coverage: Decimal = Decimal(1)
    training_domain_distance: Decimal = Decimal()
    observed_market_probability: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.data_coverage.is_finite() or not 0 <= self.data_coverage <= 1:
            raise ValueError("data_coverage doit être dans [0,1]")
        if not self.training_domain_distance.is_finite() or self.training_domain_distance < 0:
            raise ValueError("training_domain_distance doit être positif")
        if self.observed_market_probability is not None and (
            not self.observed_market_probability.is_finite()
            or not 0 <= self.observed_market_probability <= 1
        ):
            raise ValueError("la probabilité marché observée doit être dans [0,1]")


@dataclass(frozen=True, slots=True)
class EvaluationMetricReport:
    sample_count: int
    positive_count: int
    negative_count: int
    log_loss: Decimal
    brier_score: Decimal
    roc_auc: Decimal | None
    calibration_ece: Decimal
    calibration_slope: Decimal
    calibration_intercept: Decimal
    sharpness: Decimal | None
    interval_coverage: Decimal | None
    interval_evaluated_count: int
    abstention_count: int
    abstention_rate: Decimal

    def __post_init__(self) -> None:
        if self.sample_count < 1 or self.positive_count + self.negative_count != self.sample_count:
            raise ValueError("les effectifs de métriques sont incohérents")
        if not 0 <= self.abstention_count <= self.sample_count:
            raise ValueError("le nombre d'abstentions est incohérent")
        if self.interval_evaluated_count != self.sample_count - self.abstention_count:
            raise ValueError("le dénominateur de couverture est incohérent")
        probabilities = (self.roc_auc, self.interval_coverage, self.abstention_rate)
        if any(value is not None and not 0 <= value <= 1 for value in probabilities):
            raise ValueError("une métrique probabiliste est hors de [0,1]")

    def document(self) -> dict[str, object]:
        return {
            "abstention_count": self.abstention_count,
            "abstention_rate": str(self.abstention_rate),
            "brier_score": str(self.brier_score),
            "calibration_ece": str(self.calibration_ece),
            "calibration_intercept": str(self.calibration_intercept),
            "calibration_slope": str(self.calibration_slope),
            "interval_coverage": (
                str(self.interval_coverage) if self.interval_coverage is not None else None
            ),
            "interval_evaluated_count": self.interval_evaluated_count,
            "log_loss": str(self.log_loss),
            "negative_count": self.negative_count,
            "positive_count": self.positive_count,
            "roc_auc": str(self.roc_auc) if self.roc_auc is not None else None,
            "sample_count": self.sample_count,
            "sharpness": str(self.sharpness) if self.sharpness is not None else None,
        }


@dataclass(frozen=True, slots=True)
class EvaluationSegmentReport:
    dimension: str
    value: str
    sample_count: int
    metrics: EvaluationMetricReport
    low_sample: bool
    drift_detected: bool
    drift_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.sample_count != self.metrics.sample_count:
            raise ValueError("l'effectif du segment ne correspond pas à ses métriques")
        if self.low_sample and (self.drift_detected or self.drift_reasons):
            raise ValueError("un faible échantillon ne peut conclure à une dérive")
        if self.drift_detected != bool(self.drift_reasons):
            raise ValueError("les raisons de dérive doivent correspondre au statut")

    def document(self) -> dict[str, object]:
        return {
            "dimension": self.dimension,
            "drift_detected": self.drift_detected,
            "drift_reasons": list(self.drift_reasons),
            "low_sample": self.low_sample,
            "metrics": self.metrics.document(),
            "sample_count": self.sample_count,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class OutsiderRobustnessReport:
    outsider_sample_count: int
    reference_sample_count: int
    outsider_metrics: EvaluationMetricReport | None
    reference_metrics: EvaluationMetricReport | None
    log_loss_delta: Decimal | None
    calibration_ece_delta: Decimal | None
    low_sample: bool
    degraded: bool | None

    def document(self) -> dict[str, object]:
        return {
            "calibration_ece_delta": (
                str(self.calibration_ece_delta) if self.calibration_ece_delta is not None else None
            ),
            "degraded": self.degraded,
            "log_loss_delta": (
                str(self.log_loss_delta) if self.log_loss_delta is not None else None
            ),
            "low_sample": self.low_sample,
            "outsider_metrics": (
                self.outsider_metrics.document() if self.outsider_metrics is not None else None
            ),
            "outsider_sample_count": self.outsider_sample_count,
            "reference_metrics": (
                self.reference_metrics.document() if self.reference_metrics is not None else None
            ),
            "reference_sample_count": self.reference_sample_count,
        }


@dataclass(frozen=True, slots=True)
class PromotionMetricPolicy:
    primary_metrics: tuple[str, ...] = (
        "log_loss",
        "brier_score",
        "calibration_ece",
    )
    secondary_metrics: tuple[str, ...] = ("roc_auc", "accuracy")
    guard_metrics: tuple[str, ...] = (
        "interval_coverage",
        "sharpness",
        "abstention_rate",
    )

    def assert_valid_basis(self, metric_names: Sequence[str]) -> None:
        requested = {name.strip() for name in metric_names if name.strip()}
        if not requested:
            raise ValueError("au moins une métrique de promotion est requise")
        if not requested.intersection(self.primary_metrics):
            raise ValueError(
                "une promotion exige une métrique probabiliste primaire; "
                "accuracy ou ROC-AUC seules sont interdites"
            )

    def document(self) -> dict[str, object]:
        return {
            "guard_metrics": list(self.guard_metrics),
            "primary_metrics": list(self.primary_metrics),
            "secondary_metrics": list(self.secondary_metrics),
        }


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    report_id: UUID
    dataset_id: UUID
    calibrator_artifact_id: UUID
    uncertainty_artifact_id: UUID
    walk_forward_fingerprint: str
    evaluation_split: str
    parameters: EvaluationReportParameters
    overall: EvaluationMetricReport
    segments: tuple[EvaluationSegmentReport, ...]
    outsider_robustness: OutsiderRobustnessReport | None
    observed_odds_count: int
    drifted_segment_count: int
    promotion_policy: PromotionMetricPolicy
    code_commit: str
    report_fingerprint: str

    def __post_init__(self) -> None:
        if self.overall.sample_count < 1 or self.observed_odds_count < 0:
            raise ValueError("les effectifs du rapport sont invalides")
        if self.drifted_segment_count != sum(item.drift_detected for item in self.segments):
            raise ValueError("le compteur de segments en dérive est incohérent")
        expected_fingerprint = _content_hash(self.document())
        if self.report_fingerprint != expected_fingerprint:
            raise ValueError("le fingerprint du rapport ne correspond pas à son contenu")
        expected_id = uuid5(NAMESPACE_URL, f"metiquo:evaluation-report:{expected_fingerprint}")
        if self.report_id != expected_id:
            raise ValueError("l'identifiant du rapport ne correspond pas à son fingerprint")

    def document(self) -> dict[str, object]:
        return {
            "calibrator_artifact_id": str(self.calibrator_artifact_id),
            "code_commit": self.code_commit,
            "dataset_id": str(self.dataset_id),
            "drifted_segment_count": self.drifted_segment_count,
            "evaluation_split": self.evaluation_split,
            "observed_odds_count": self.observed_odds_count,
            "odds_policy": "observed_only",
            "overall": self.overall.document(),
            "outsider_robustness": (
                self.outsider_robustness.document()
                if self.outsider_robustness is not None
                else None
            ),
            "parameters": self.parameters.document(),
            "promotion_policy": self.promotion_policy.document(),
            "segments": [item.document() for item in self.segments],
            "uncertainty_artifact_id": str(self.uncertainty_artifact_id),
            "walk_forward_fingerprint": self.walk_forward_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class _EvaluatedPrediction:
    prediction: BaselinePrediction
    example: WalkForwardExample
    p_low: Decimal
    p_high: Decimal
    abstained: bool
    market_probability: Decimal | None


class EvaluationReportBuilder:
    """Évaluer la preuve calibrée sans accéder au test final."""

    def __init__(
        self,
        *,
        code_commit: str,
        parameters: EvaluationReportParameters | None = None,
    ) -> None:
        if _COMMIT.fullmatch(code_commit) is None:
            raise ValueError("code_commit doit être un hash git hexadécimal")
        self._code_commit = code_commit
        self._parameters = parameters or EvaluationReportParameters()

    def build(
        self,
        plan: WalkForwardPlan,
        *,
        calibrator: CalibratorArtifact,
        uncertainty: UncertaintyArtifact,
        contexts: Mapping[UUID, EvaluationContext] | None = None,
    ) -> EvaluationReport:
        if calibrator.walk_forward_fingerprint != plan.fingerprint:
            raise ValueError("le calibrateur et le plan walk-forward ne correspondent pas")
        if uncertainty.calibrator_artifact_id != calibrator.artifact_id:
            raise ValueError("l'incertitude ne référence pas le calibrateur demandé")
        predictions = calibrator.oos_predictions
        if not predictions:
            raise ValueError("le rapport exige des prédictions calibrées OOS")
        prediction_ids = tuple(item.example_id for item in predictions)
        if len(prediction_ids) != len(set(prediction_ids)):
            raise ValueError("les prédictions calibrées doivent être uniques")
        plan.assert_tuning_scope(prediction_ids)
        final_ids = {item.example_id for item in plan.final_test}
        if final_ids.intersection(prediction_ids):
            raise ValueError("le test final doit rester absent du rapport de sélection")
        resolved_contexts = contexts or {}
        unknown_contexts = set(resolved_contexts) - set(prediction_ids)
        if unknown_contexts:
            raise ValueError("un contexte d'évaluation ne correspond à aucune prédiction OOS")
        examples = {item.example_id: item for item in plan.oof_validation}
        evaluated: list[_EvaluatedPrediction] = []
        for prediction in predictions:
            example = examples[prediction.example_id]
            if prediction.cutoff_at != example.cutoff_at or prediction.label != example.label:
                raise ValueError("la preuve calibrée ne correspond pas à l'exemple walk-forward")
            context = resolved_contexts.get(prediction.example_id, EvaluationContext())
            estimate = uncertainty.estimate_calibrated(
                prediction.probability,
                data_coverage=context.data_coverage,
                training_domain_distance=context.training_domain_distance,
            )
            evaluated.append(
                _EvaluatedPrediction(
                    prediction=prediction,
                    example=example,
                    p_low=estimate.p_low,
                    p_high=estimate.p_high,
                    abstained="ABSTENTION_REQUIRED" in estimate.reasons,
                    market_probability=context.observed_market_probability,
                )
            )
        overall = _evaluate(evaluated, bin_count=self._parameters.calibration_bins)
        segments = _segments(evaluated, overall=overall, parameters=self._parameters)
        outsider = _outsider_report(evaluated, parameters=self._parameters)
        odds_count = sum(item.market_probability is not None for item in evaluated)
        promotion_policy = PromotionMetricPolicy()
        content = {
            "calibrator_artifact_id": str(calibrator.artifact_id),
            "code_commit": self._code_commit,
            "dataset_id": str(calibrator.dataset_id),
            "drifted_segment_count": sum(item.drift_detected for item in segments),
            "evaluation_split": "calibration_oos",
            "observed_odds_count": odds_count,
            "odds_policy": "observed_only",
            "overall": overall.document(),
            "outsider_robustness": outsider.document() if outsider is not None else None,
            "parameters": self._parameters.document(),
            "promotion_policy": promotion_policy.document(),
            "segments": [item.document() for item in segments],
            "uncertainty_artifact_id": str(uncertainty.artifact_id),
            "walk_forward_fingerprint": plan.fingerprint,
        }
        fingerprint = _content_hash(content)
        return EvaluationReport(
            report_id=uuid5(NAMESPACE_URL, f"metiquo:evaluation-report:{fingerprint}"),
            dataset_id=calibrator.dataset_id,
            calibrator_artifact_id=calibrator.artifact_id,
            uncertainty_artifact_id=uncertainty.artifact_id,
            walk_forward_fingerprint=plan.fingerprint,
            evaluation_split="calibration_oos",
            parameters=self._parameters,
            overall=overall,
            segments=segments,
            outsider_robustness=outsider,
            observed_odds_count=odds_count,
            drifted_segment_count=sum(item.drift_detected for item in segments),
            promotion_policy=promotion_policy,
            code_commit=self._code_commit,
            report_fingerprint=fingerprint,
        )


def _evaluate(
    values: Sequence[_EvaluatedPrediction],
    *,
    bin_count: int,
) -> EvaluationMetricReport:
    if not values:
        raise ValueError("au moins une observation est requise")
    predictions = tuple(item.prediction for item in values)
    core = evaluate_binary_probabilities(predictions, bin_count=bin_count)
    positive_count = sum(item.prediction.label for item in values)
    eligible = tuple(item for item in values if not item.abstained)
    covered = sum(
        item.p_low <= Decimal(int(item.prediction.label)) <= item.p_high for item in eligible
    )
    sharpness = (
        _metric(
            sum((item.p_high - item.p_low for item in eligible), Decimal()) / Decimal(len(eligible))
        )
        if eligible
        else None
    )
    interval_coverage = _metric(Decimal(covered) / Decimal(len(eligible))) if eligible else None
    slope, intercept = _calibration_regression(predictions)
    abstention_count = len(values) - len(eligible)
    return EvaluationMetricReport(
        sample_count=len(values),
        positive_count=positive_count,
        negative_count=len(values) - positive_count,
        log_loss=core.log_loss,
        brier_score=core.brier_score,
        roc_auc=_roc_auc(predictions),
        calibration_ece=core.calibration_ece,
        calibration_slope=slope,
        calibration_intercept=intercept,
        sharpness=sharpness,
        interval_coverage=interval_coverage,
        interval_evaluated_count=len(eligible),
        abstention_count=abstention_count,
        abstention_rate=_metric(Decimal(abstention_count) / Decimal(len(values))),
    )


def _segments(
    values: Sequence[_EvaluatedPrediction],
    *,
    overall: EvaluationMetricReport,
    parameters: EvaluationReportParameters,
) -> tuple[EvaluationSegmentReport, ...]:
    grouped: defaultdict[tuple[str, str], list[_EvaluatedPrediction]] = defaultdict(list)
    for item in values:
        for dimension, value in _segment_values(item):
            grouped[(dimension, value)].append(item)
    reports: list[EvaluationSegmentReport] = []
    for (dimension, value), observations in sorted(grouped.items()):
        metrics = _evaluate(observations, bin_count=parameters.calibration_bins)
        low_sample = len(observations) < parameters.minimum_segment_samples
        reasons = () if low_sample else _drift_reasons(metrics, overall, parameters)
        reports.append(
            EvaluationSegmentReport(
                dimension=dimension,
                value=value,
                sample_count=len(observations),
                metrics=metrics,
                low_sample=low_sample,
                drift_detected=bool(reasons),
                drift_reasons=reasons,
            )
        )
    return tuple(reports)


def _segment_values(item: _EvaluatedPrediction) -> tuple[tuple[str, str], ...]:
    features = item.example.feature_values
    league = _text(features.get("context.league"))
    if league is None and item.example.competition_id is not None:
        league = str(item.example.competition_id)
    stage = _text(features.get("context.stage"))
    best_of = features.get("context.best_of")
    game_format = (
        f"BO{best_of}"
        if isinstance(best_of, int) and not isinstance(best_of, bool) and best_of > 0
        else "unknown"
    )
    values: list[tuple[str, str]] = [
        ("format", game_format),
        ("league", league or "unknown"),
        ("patch", item.example.patch or "unknown"),
        ("stage", stage or "unknown"),
    ]
    if item.market_probability is not None:
        values.append(("odds_bucket", _odds_bucket(item.market_probability)))
    return tuple(values)


def _drift_reasons(
    metrics: EvaluationMetricReport,
    overall: EvaluationMetricReport,
    parameters: EvaluationReportParameters,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if metrics.log_loss - overall.log_loss > parameters.log_loss_drift_threshold:
        reasons.append("LOG_LOSS_DRIFT")
    if metrics.calibration_ece - overall.calibration_ece > parameters.calibration_drift_threshold:
        reasons.append("CALIBRATION_DRIFT")
    if (
        metrics.interval_coverage is not None
        and overall.interval_coverage is not None
        and overall.interval_coverage - metrics.interval_coverage
        > parameters.interval_coverage_drift_threshold
    ):
        reasons.append("INTERVAL_COVERAGE_DRIFT")
    if metrics.abstention_rate - overall.abstention_rate > parameters.abstention_drift_threshold:
        reasons.append("ABSTENTION_DRIFT")
    return tuple(reasons)


def _outsider_report(
    values: Sequence[_EvaluatedPrediction],
    *,
    parameters: EvaluationReportParameters,
) -> OutsiderRobustnessReport | None:
    observed = tuple(item for item in values if item.market_probability is not None)
    if not observed:
        return None
    outsiders = tuple(
        item
        for item in observed
        if cast(Decimal, item.market_probability) < parameters.outsider_probability_threshold
    )
    reference = tuple(
        item
        for item in observed
        if cast(Decimal, item.market_probability) >= parameters.outsider_probability_threshold
    )
    outsider_metrics = (
        _evaluate(outsiders, bin_count=parameters.calibration_bins) if outsiders else None
    )
    reference_metrics = (
        _evaluate(reference, bin_count=parameters.calibration_bins) if reference else None
    )
    low_sample = (
        len(outsiders) < parameters.minimum_segment_samples
        or len(reference) < parameters.minimum_segment_samples
    )
    if outsider_metrics is None or reference_metrics is None:
        log_loss_delta = None
        calibration_delta = None
        degraded = None
    else:
        log_loss_delta = _metric(outsider_metrics.log_loss - reference_metrics.log_loss)
        calibration_delta = _metric(
            outsider_metrics.calibration_ece - reference_metrics.calibration_ece
        )
        degraded = (
            None
            if low_sample
            else (
                log_loss_delta > parameters.log_loss_drift_threshold
                or calibration_delta > parameters.calibration_drift_threshold
            )
        )
    return OutsiderRobustnessReport(
        outsider_sample_count=len(outsiders),
        reference_sample_count=len(reference),
        outsider_metrics=outsider_metrics,
        reference_metrics=reference_metrics,
        log_loss_delta=log_loss_delta,
        calibration_ece_delta=calibration_delta,
        low_sample=low_sample,
        degraded=degraded,
    )


def _roc_auc(predictions: Sequence[BaselinePrediction]) -> Decimal | None:
    positive_count = sum(item.label for item in predictions)
    negative_count = len(predictions) - positive_count
    if positive_count == 0 or negative_count == 0:
        return None
    ordered = sorted(predictions, key=lambda item: item.probability)
    rank = 1
    positive_rank_sum = Decimal()
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end].probability == ordered[cursor].probability:
            end += 1
        mean_rank = (Decimal(rank) + Decimal(rank + end - cursor - 1)) / Decimal(2)
        positive_rank_sum += mean_rank * sum(item.label for item in ordered[cursor:end])
        rank += end - cursor
        cursor = end
    numerator = positive_rank_sum - Decimal(positive_count * (positive_count + 1)) / Decimal(2)
    return _metric(numerator / Decimal(positive_count * negative_count))


def _calibration_regression(
    predictions: Sequence[BaselinePrediction],
) -> tuple[Decimal, Decimal]:
    labels = [int(item.label) for item in predictions]
    if len(set(labels)) < 2:
        probability = (sum(labels) + 0.5) / (len(labels) + 1)
        return Decimal(), _metric(Decimal(str(_logit(probability))))
    model = LogisticRegression(C=1_000_000, max_iter=1_000, random_state=0, solver="lbfgs")
    model.fit([[_logit(float(item.probability))] for item in predictions], labels)
    slope = float(cast(Sequence[Sequence[float]], model.coef_)[0][0])
    intercept = float(cast(Sequence[float], model.intercept_)[0])
    return _metric(Decimal(str(slope))), _metric(Decimal(str(intercept)))


def _logit(probability: float) -> float:
    clipped = min(max(probability, _LOG_EPSILON), 1 - _LOG_EPSILON)
    return math.log(clipped / (1 - clipped))


def _odds_bucket(probability: Decimal) -> str:
    if probability < Decimal("0.400000"):
        return "under_40_pct"
    if probability <= Decimal("0.600000"):
        return "40_to_60_pct"
    return "over_60_pct"


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _metric(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("une métrique doit être finie")
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def _content_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
