"""Candidat d'ensemble rating/tabulaire choisi uniquement sur OOF temporelles."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from types import MappingProxyType
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.ml_models import (
    EnsembleCandidatePrediction as EnsembleCandidatePredictionRow,
)
from metiquo.db.ml_models import EnsembleCandidateRun as EnsembleCandidateRunRow
from metiquo.db.ml_models import TrainingDatasetExample
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime
from metiquo.models.baselines import (
    COMPETITION_PRIOR,
    RATING,
    RECENT_FORM,
    BaselinePrediction,
    BaselineRun,
    BaselineRunRepository,
    BinaryMetricReport,
    assert_baseline_runs_comparable,
    binary_metric_report_from_document,
    evaluate_binary_probabilities,
)
from metiquo.models.benchmark import (
    TabularBenchmarkRepository,
    TabularBenchmarkRun,
)
from metiquo.models.datasets import GAME_WINNER_MARKET

ENSEMBLE_CANDIDATE_VERSION = "rating-tabular-ensemble-v1"
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_BASELINES = frozenset({COMPETITION_PRIOR, RECENT_FORM, RATING})
_WEIGHT_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class EnsembleSearchParameters:
    """Grille de poids intérieure, sélectionnée sur les seules OOF."""

    rating_weights: tuple[Decimal, ...] = tuple(
        Decimal(index) / Decimal(10) for index in range(1, 10)
    )
    calibration_bins: int = 10
    version: str = ENSEMBLE_CANDIDATE_VERSION

    def __post_init__(self) -> None:
        try:
            weights = tuple(
                value.quantize(_WEIGHT_QUANTUM, rounding=ROUND_HALF_EVEN)
                for value in self.rating_weights
            )
        except InvalidOperation as error:
            raise ValueError("les poids doivent être représentables") from error
        if not weights or any(not value.is_finite() or not 0 < value < 1 for value in weights):
            raise ValueError("les poids rating doivent être finis et strictement dans ]0,1[")
        if len(weights) != len(set(weights)):
            raise ValueError("les poids rating doivent être uniques")
        if self.calibration_bins < 2:
            raise ValueError("au moins deux bins de calibration sont requis")
        if not self.version.strip():
            raise ValueError("la version de l'ensemble est requise")
        object.__setattr__(self, "rating_weights", tuple(sorted(weights)))


@dataclass(frozen=True, slots=True)
class EnsembleWeightEvaluation:
    rating_weight: Decimal
    metrics: BinaryMetricReport
    worst_fold_log_loss: Decimal

    def document(self) -> dict[str, object]:
        return {
            "metrics": self.metrics.document(),
            "rating_weight": str(self.rating_weight),
            "worst_fold_log_loss": str(self.worst_fold_log_loss),
        }


@dataclass(frozen=True, slots=True)
class EnsembleReferenceComparison:
    reference_id: UUID
    reference_kind: str
    reference_name: str
    log_loss_gain: Decimal
    calibration_ece_gain: Decimal
    worst_fold_log_loss_gain: Decimal
    passed: bool

    def document(self) -> dict[str, object]:
        return {
            "calibration_ece_gain": str(self.calibration_ece_gain),
            "log_loss_gain": str(self.log_loss_gain),
            "passed": self.passed,
            "reference_id": str(self.reference_id),
            "reference_kind": self.reference_kind,
            "reference_name": self.reference_name,
            "worst_fold_log_loss_gain": str(self.worst_fold_log_loss_gain),
        }


@dataclass(frozen=True, slots=True)
class EnsembleDecision:
    enabled: bool
    policy_version: str
    comparisons: tuple[EnsembleReferenceComparison, ...]
    reasons: tuple[str, ...]

    def document(self) -> dict[str, object]:
        return {
            "comparisons": [item.document() for item in self.comparisons],
            "enabled": self.enabled,
            "policy_version": self.policy_version,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class EnsembleCandidateRun:
    run_id: UUID
    dataset_id: UUID
    benchmark_run_id: UUID
    rating_run_id: UUID
    market: str
    ensemble_version: str
    walk_forward_fingerprint: str
    candidate_weights: tuple[Decimal, ...]
    candidate_evaluations: Mapping[str, EnsembleWeightEvaluation]
    selected_rating_weight: Decimal
    baseline_run_ids: tuple[UUID, ...]
    decision: EnsembleDecision
    metrics: BinaryMetricReport
    worst_fold_log_loss: Decimal
    predictions_fingerprint: str
    run_fingerprint: str
    code_commit: str
    created_at: datetime
    predictions: tuple[BaselinePrediction, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", normalize_utc_datetime(self.created_at))

    @property
    def enabled(self) -> bool:
        return self.decision.enabled


class EnsembleCandidateEvaluator:
    """Évaluer les mélanges, puis documenter explicitement activation ou refus."""

    def __init__(
        self,
        *,
        code_commit: str,
        search: EnsembleSearchParameters | None = None,
        clock: Clock | None = None,
    ) -> None:
        if _COMMIT.fullmatch(code_commit) is None:
            raise ValueError("code_commit doit être un hash git hexadécimal")
        self._code_commit = code_commit
        self._search = search or EnsembleSearchParameters()
        self._clock = clock or SystemClock()

    def evaluate(
        self,
        benchmark: TabularBenchmarkRun,
        *,
        baseline_runs: Sequence[BaselineRun],
    ) -> EnsembleCandidateRun:
        return _build_run(
            benchmark,
            baseline_runs=baseline_runs,
            search=self._search,
            code_commit=self._code_commit,
            created_at=self._clock.now().value,
        )


def _build_run(
    benchmark: TabularBenchmarkRun,
    *,
    baseline_runs: Sequence[BaselineRun],
    search: EnsembleSearchParameters,
    code_commit: str,
    created_at: datetime,
) -> EnsembleCandidateRun:
    comparison = assert_baseline_runs_comparable(baseline_runs)
    if {run.baseline_name for run in baseline_runs} != _REQUIRED_BASELINES:
        raise ValueError("prior, forme récente et rating sont tous requis")
    baseline_ids = tuple(
        run.run_id for run in sorted(baseline_runs, key=lambda item: item.baseline_name)
    )
    if (
        comparison.dataset_id != benchmark.dataset_id
        or comparison.walk_forward_fingerprint != benchmark.walk_forward_fingerprint
        or baseline_ids != benchmark.baseline_run_ids
    ):
        raise ValueError("le benchmark et les baselines doivent partager le même périmètre OOF")
    rating = next(run for run in baseline_runs if run.baseline_name == RATING)
    _assert_same_scope(rating.predictions, benchmark.predictions)

    predictions_by_weight = {
        weight: _blend_predictions(
            rating.predictions,
            benchmark.predictions,
            rating_weight=weight,
        )
        for weight in search.rating_weights
    }
    evaluations = {
        str(weight): _evaluate_weight(
            weight,
            predictions,
            calibration_bins=search.calibration_bins,
        )
        for weight, predictions in predictions_by_weight.items()
    }
    selected_key = min(
        evaluations,
        key=lambda key: (
            evaluations[key].metrics.log_loss,
            evaluations[key].metrics.calibration_ece,
            evaluations[key].worst_fold_log_loss,
            evaluations[key].rating_weight,
        ),
    )
    selected = evaluations[selected_key]
    predictions = predictions_by_weight[selected.rating_weight]
    decision = _decision(
        selected,
        benchmark=benchmark,
        baseline_runs=baseline_runs,
    )
    predictions_fingerprint = _content_hash([item.document() for item in predictions])
    content = _run_content(
        dataset_id=benchmark.dataset_id,
        benchmark_run_id=benchmark.run_id,
        rating_run_id=rating.run_id,
        market=GAME_WINNER_MARKET,
        ensemble_version=search.version,
        walk_forward_fingerprint=benchmark.walk_forward_fingerprint,
        candidate_weights=search.rating_weights,
        candidate_evaluations=evaluations,
        selected_rating_weight=selected.rating_weight,
        baseline_run_ids=baseline_ids,
        decision=decision,
        metrics=selected.metrics,
        worst_fold_log_loss=selected.worst_fold_log_loss,
        predictions_fingerprint=predictions_fingerprint,
        code_commit=code_commit,
    )
    fingerprint = _content_hash(content)
    return EnsembleCandidateRun(
        run_id=uuid5(NAMESPACE_URL, f"metiquo:ensemble-candidate:{fingerprint}"),
        dataset_id=benchmark.dataset_id,
        benchmark_run_id=benchmark.run_id,
        rating_run_id=rating.run_id,
        market=GAME_WINNER_MARKET,
        ensemble_version=search.version,
        walk_forward_fingerprint=benchmark.walk_forward_fingerprint,
        candidate_weights=search.rating_weights,
        candidate_evaluations=MappingProxyType(evaluations),
        selected_rating_weight=selected.rating_weight,
        baseline_run_ids=baseline_ids,
        decision=decision,
        metrics=selected.metrics,
        worst_fold_log_loss=selected.worst_fold_log_loss,
        predictions_fingerprint=predictions_fingerprint,
        run_fingerprint=fingerprint,
        code_commit=code_commit,
        created_at=created_at,
        predictions=predictions,
    )


class EnsembleCandidateRepository:
    """Persister une décision d'ensemble et sa preuve OOF append-only."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def record(self, run: EnsembleCandidateRun) -> EnsembleCandidateRun:
        _validate_run(run)
        benchmark = TabularBenchmarkRepository(engine=self._engine).get(run.benchmark_run_id)
        if benchmark is None:
            raise ValueError("le benchmark tabulaire source est introuvable")
        baseline_repository = BaselineRunRepository(engine=self._engine)
        baselines = tuple(
            baseline
            for run_id in run.baseline_run_ids
            if (baseline := baseline_repository.get(run_id)) is not None
        )
        if len(baselines) != 3:
            raise ValueError("les trois baselines sources doivent être publiées")
        rebuilt = _build_run(
            benchmark,
            baseline_runs=baselines,
            search=EnsembleSearchParameters(
                rating_weights=run.candidate_weights,
                calibration_bins=run.metrics.bin_count,
                version=run.ensemble_version,
            ),
            code_commit=run.code_commit,
            created_at=run.created_at,
        )
        if rebuilt != run:
            raise ValueError("le run d'ensemble ne correspond pas à ses sources publiées")

        runs = cast(Table, EnsembleCandidateRunRow.__table__)
        predictions = cast(Table, EnsembleCandidatePredictionRow.__table__)
        dataset_examples = cast(Table, TrainingDatasetExample.__table__)
        with self._engine.begin() as connection:
            allowed_ids = set(
                connection.execute(
                    select(dataset_examples.c.event_id).where(
                        dataset_examples.c.dataset_id == run.dataset_id
                    )
                ).scalars()
            )
            if not {item.example_id for item in run.predictions} <= allowed_ids:
                raise ValueError("l'ensemble ne peut référencer que les exemples de son dataset")
            inserted = connection.execute(
                insert(runs)
                .values(
                    id=run.run_id,
                    dataset_id=run.dataset_id,
                    benchmark_run_id=run.benchmark_run_id,
                    rating_run_id=run.rating_run_id,
                    market=run.market,
                    ensemble_version=run.ensemble_version,
                    walk_forward_fingerprint=run.walk_forward_fingerprint,
                    candidate_weights=[str(value) for value in run.candidate_weights],
                    candidate_evaluations={
                        key: value.document()
                        for key, value in sorted(run.candidate_evaluations.items())
                    },
                    selected_rating_weight=run.selected_rating_weight,
                    baseline_run_ids=[str(value) for value in run.baseline_run_ids],
                    decision=run.decision.document(),
                    enabled=run.enabled,
                    metrics=run.metrics.document(),
                    worst_fold_log_loss=run.worst_fold_log_loss,
                    prediction_count=len(run.predictions),
                    predictions_fingerprint=run.predictions_fingerprint,
                    run_fingerprint=run.run_fingerprint,
                    code_commit=run.code_commit,
                    created_at=run.created_at,
                )
                .on_conflict_do_nothing(index_elements=[runs.c.run_fingerprint])
                .returning(runs.c.id)
            ).scalar_one_or_none()
            if inserted is not None:
                connection.execute(
                    insert(predictions),
                    [
                        {
                            "run_id": run.run_id,
                            "position": position,
                            "example_id": item.example_id,
                            "fold_index": item.fold_index,
                            "cutoff_at": item.cutoff_at,
                            "label": item.label,
                            "probability": item.probability,
                        }
                        for position, item in enumerate(run.predictions)
                    ],
                )
        stored = self.get_by_fingerprint(run.run_fingerprint)
        if stored is None:
            raise RuntimeError("le run d'ensemble n'a pas été enregistré")
        return stored

    def get(self, run_id: UUID) -> EnsembleCandidateRun | None:
        runs = cast(Table, EnsembleCandidateRunRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one_or_none()
            )
        return self._stored(row) if row is not None else None

    def get_by_fingerprint(self, fingerprint: str) -> EnsembleCandidateRun | None:
        runs = cast(Table, EnsembleCandidateRunRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(runs).where(runs.c.run_fingerprint == fingerprint))
                .mappings()
                .one_or_none()
            )
        return self._stored(row) if row is not None else None

    def _stored(self, row: RowMapping) -> EnsembleCandidateRun:
        predictions = cast(Table, EnsembleCandidatePredictionRow.__table__)
        with self._engine.connect() as connection:
            prediction_rows = (
                connection.execute(
                    select(predictions)
                    .where(predictions.c.run_id == row["id"])
                    .order_by(predictions.c.position)
                )
                .mappings()
                .all()
            )
        candidate_documents = cast(Mapping[str, Mapping[str, object]], row["candidate_evaluations"])
        return EnsembleCandidateRun(
            run_id=cast(UUID, row["id"]),
            dataset_id=cast(UUID, row["dataset_id"]),
            benchmark_run_id=cast(UUID, row["benchmark_run_id"]),
            rating_run_id=cast(UUID, row["rating_run_id"]),
            market=cast(str, row["market"]),
            ensemble_version=cast(str, row["ensemble_version"]),
            walk_forward_fingerprint=cast(str, row["walk_forward_fingerprint"]),
            candidate_weights=tuple(
                Decimal(value) for value in cast(Sequence[str], row["candidate_weights"])
            ),
            candidate_evaluations=MappingProxyType(
                {
                    key: _weight_evaluation_from_document(document)
                    for key, document in candidate_documents.items()
                }
            ),
            selected_rating_weight=cast(Decimal, row["selected_rating_weight"]),
            baseline_run_ids=tuple(
                UUID(value) for value in cast(Sequence[str], row["baseline_run_ids"])
            ),
            decision=_decision_from_document(cast(Mapping[str, object], row["decision"])),
            metrics=binary_metric_report_from_document(cast(Mapping[str, object], row["metrics"])),
            worst_fold_log_loss=cast(Decimal, row["worst_fold_log_loss"]),
            predictions_fingerprint=cast(str, row["predictions_fingerprint"]),
            run_fingerprint=cast(str, row["run_fingerprint"]),
            code_commit=cast(str, row["code_commit"]),
            created_at=cast(datetime, row["created_at"]),
            predictions=tuple(
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


def _blend_predictions(
    rating: Sequence[BaselinePrediction],
    tabular: Sequence[BaselinePrediction],
    *,
    rating_weight: Decimal,
) -> tuple[BaselinePrediction, ...]:
    _assert_same_scope(rating, tabular)
    tabular_weight = Decimal(1) - rating_weight
    return tuple(
        BaselinePrediction(
            example_id=rating_item.example_id,
            fold_index=rating_item.fold_index,
            cutoff_at=rating_item.cutoff_at,
            label=rating_item.label,
            probability=(
                rating_weight * rating_item.probability + tabular_weight * tabular_item.probability
            ),
        )
        for rating_item, tabular_item in zip(rating, tabular, strict=True)
    )


def _evaluate_weight(
    weight: Decimal,
    predictions: tuple[BaselinePrediction, ...],
    *,
    calibration_bins: int,
) -> EnsembleWeightEvaluation:
    fold_metrics = _fold_metrics(predictions, calibration_bins)
    return EnsembleWeightEvaluation(
        rating_weight=weight,
        metrics=evaluate_binary_probabilities(predictions, bin_count=calibration_bins),
        worst_fold_log_loss=max(item.log_loss for item in fold_metrics.values()),
    )


def _decision(
    selected: EnsembleWeightEvaluation,
    *,
    benchmark: TabularBenchmarkRun,
    baseline_runs: Sequence[BaselineRun],
) -> EnsembleDecision:
    references = [
        (
            "baseline",
            baseline.run_id,
            baseline.baseline_name,
            baseline.metrics,
            max(
                item.log_loss
                for item in _fold_metrics(baseline.predictions, baseline.metrics.bin_count).values()
            ),
        )
        for baseline in sorted(baseline_runs, key=lambda item: item.baseline_name)
    ]
    references.append(
        (
            "tabular",
            benchmark.run_id,
            benchmark.selected_candidate,
            benchmark.selected.metrics,
            benchmark.selected.worst_fold_log_loss,
        )
    )
    comparisons: list[EnsembleReferenceComparison] = []
    reasons: list[str] = []
    if not benchmark.promotion_gate.promotable:
        reasons.append("TABULAR_NOT_PROMOTABLE")
    for kind, reference_id, name, metrics, worst_fold in references:
        log_gain = metrics.log_loss - selected.metrics.log_loss
        calibration_gain = metrics.calibration_ece - selected.metrics.calibration_ece
        robustness_gain = worst_fold - selected.worst_fold_log_loss
        passed = log_gain > 0 and calibration_gain > 0 and robustness_gain > 0
        comparisons.append(
            EnsembleReferenceComparison(
                reference_id=reference_id,
                reference_kind=kind,
                reference_name=name,
                log_loss_gain=log_gain,
                calibration_ece_gain=calibration_gain,
                worst_fold_log_loss_gain=robustness_gain,
                passed=passed,
            )
        )
        if not passed:
            reasons.append(f"REFERENCE_NOT_BEATEN:{kind}:{name}")
    return EnsembleDecision(
        enabled=not reasons,
        policy_version="ensemble-oof-promotion-v1",
        comparisons=tuple(comparisons),
        reasons=tuple(reasons),
    )


def _assert_same_scope(
    left: Sequence[BaselinePrediction],
    right: Sequence[BaselinePrediction],
) -> None:
    left_scope = tuple(
        (item.example_id, item.fold_index, item.cutoff_at, item.label) for item in left
    )
    right_scope = tuple(
        (item.example_id, item.fold_index, item.cutoff_at, item.label) for item in right
    )
    if left_scope != right_scope:
        raise ValueError("rating et tabulaire doivent couvrir exactement les mêmes OOF")


def _fold_metrics(
    predictions: Sequence[BaselinePrediction],
    bin_count: int,
) -> dict[int, BinaryMetricReport]:
    grouped: dict[int, list[BaselinePrediction]] = {}
    for item in predictions:
        grouped.setdefault(item.fold_index, []).append(item)
    return {
        fold_index: evaluate_binary_probabilities(values, bin_count=bin_count)
        for fold_index, values in sorted(grouped.items())
    }


def _validate_run(run: EnsembleCandidateRun) -> None:
    if run.market != GAME_WINNER_MARKET:
        raise ValueError("seul le marché game_winner est pris en charge")
    if not run.ensemble_version.strip() or _COMMIT.fullmatch(run.code_commit) is None:
        raise ValueError("version ou commit d'ensemble invalide")
    if len(run.baseline_run_ids) != 3 or len(set(run.baseline_run_ids)) != 3:
        raise ValueError("trois baselines distinctes sont requises")
    if run.rating_run_id not in run.baseline_run_ids:
        raise ValueError("la baseline rating doit appartenir aux sources")
    expected_keys = {str(value) for value in run.candidate_weights}
    if set(run.candidate_evaluations) != expected_keys:
        raise ValueError("chaque poids candidat exige son évaluation")
    selected = run.candidate_evaluations.get(str(run.selected_rating_weight))
    if selected is None or selected.rating_weight != run.selected_rating_weight:
        raise ValueError("le poids sélectionné doit appartenir à la grille")
    expected_weight = min(
        run.candidate_evaluations,
        key=lambda key: (
            run.candidate_evaluations[key].metrics.log_loss,
            run.candidate_evaluations[key].metrics.calibration_ece,
            run.candidate_evaluations[key].worst_fold_log_loss,
            run.candidate_evaluations[key].rating_weight,
        ),
    )
    if str(run.selected_rating_weight) != expected_weight:
        raise ValueError("le poids sélectionné ne correspond pas aux métriques OOF")
    if run.metrics != selected.metrics or run.worst_fold_log_loss != selected.worst_fold_log_loss:
        raise ValueError("les métriques publiées ne correspondent pas au poids sélectionné")
    if (
        evaluate_binary_probabilities(run.predictions, bin_count=run.metrics.bin_count)
        != run.metrics
    ):
        raise ValueError("les métriques ne correspondent pas aux prédictions d'ensemble")
    if (
        max(
            item.log_loss for item in _fold_metrics(run.predictions, run.metrics.bin_count).values()
        )
        != run.worst_fold_log_loss
    ):
        raise ValueError("la robustesse temporelle ne correspond pas aux prédictions")
    if _content_hash([item.document() for item in run.predictions]) != run.predictions_fingerprint:
        raise ValueError("le fingerprint des prédictions d'ensemble est invalide")
    if run.enabled != (not run.decision.reasons):
        raise ValueError("la décision d'activation est incohérente")
    if len(run.decision.comparisons) != 4:
        raise ValueError("l'ensemble doit être comparé aux trois baselines et au tabulaire")
    for fingerprint in (
        run.walk_forward_fingerprint,
        run.predictions_fingerprint,
        run.run_fingerprint,
    ):
        if _FINGERPRINT.fullmatch(fingerprint) is None:
            raise ValueError("fingerprint d'ensemble invalide")
    fingerprint = _content_hash(
        _run_content(
            dataset_id=run.dataset_id,
            benchmark_run_id=run.benchmark_run_id,
            rating_run_id=run.rating_run_id,
            market=run.market,
            ensemble_version=run.ensemble_version,
            walk_forward_fingerprint=run.walk_forward_fingerprint,
            candidate_weights=run.candidate_weights,
            candidate_evaluations=run.candidate_evaluations,
            selected_rating_weight=run.selected_rating_weight,
            baseline_run_ids=run.baseline_run_ids,
            decision=run.decision,
            metrics=run.metrics,
            worst_fold_log_loss=run.worst_fold_log_loss,
            predictions_fingerprint=run.predictions_fingerprint,
            code_commit=run.code_commit,
        )
    )
    if fingerprint != run.run_fingerprint:
        raise ValueError("le fingerprint du run d'ensemble est invalide")
    if run.run_id != uuid5(NAMESPACE_URL, f"metiquo:ensemble-candidate:{fingerprint}"):
        raise ValueError("l'identifiant du run d'ensemble est invalide")


def _run_content(
    *,
    dataset_id: UUID,
    benchmark_run_id: UUID,
    rating_run_id: UUID,
    market: str,
    ensemble_version: str,
    walk_forward_fingerprint: str,
    candidate_weights: Sequence[Decimal],
    candidate_evaluations: Mapping[str, EnsembleWeightEvaluation],
    selected_rating_weight: Decimal,
    baseline_run_ids: Sequence[UUID],
    decision: EnsembleDecision,
    metrics: BinaryMetricReport,
    worst_fold_log_loss: Decimal,
    predictions_fingerprint: str,
    code_commit: str,
) -> dict[str, object]:
    return {
        "baseline_run_ids": [str(value) for value in baseline_run_ids],
        "benchmark_run_id": str(benchmark_run_id),
        "candidate_evaluations": {
            key: value.document() for key, value in sorted(candidate_evaluations.items())
        },
        "candidate_weights": [str(value) for value in candidate_weights],
        "code_commit": code_commit,
        "dataset_id": str(dataset_id),
        "decision": decision.document(),
        "ensemble_version": ensemble_version,
        "market": market,
        "metrics": metrics.document(),
        "predictions_fingerprint": predictions_fingerprint,
        "rating_run_id": str(rating_run_id),
        "selected_rating_weight": str(selected_rating_weight),
        "walk_forward_fingerprint": walk_forward_fingerprint,
        "worst_fold_log_loss": str(worst_fold_log_loss),
    }


def _weight_evaluation_from_document(
    document: Mapping[str, object],
) -> EnsembleWeightEvaluation:
    return EnsembleWeightEvaluation(
        rating_weight=Decimal(cast(str, document["rating_weight"])),
        metrics=binary_metric_report_from_document(cast(Mapping[str, object], document["metrics"])),
        worst_fold_log_loss=Decimal(cast(str, document["worst_fold_log_loss"])),
    )


def _decision_from_document(document: Mapping[str, object]) -> EnsembleDecision:
    comparisons = cast(Sequence[Mapping[str, object]], document["comparisons"])
    return EnsembleDecision(
        enabled=cast(bool, document["enabled"]),
        policy_version=cast(str, document["policy_version"]),
        comparisons=tuple(
            EnsembleReferenceComparison(
                reference_id=UUID(cast(str, item["reference_id"])),
                reference_kind=cast(str, item["reference_kind"]),
                reference_name=cast(str, item["reference_name"]),
                log_loss_gain=Decimal(cast(str, item["log_loss_gain"])),
                calibration_ece_gain=Decimal(cast(str, item["calibration_ece_gain"])),
                worst_fold_log_loss_gain=Decimal(cast(str, item["worst_fold_log_loss_gain"])),
                passed=cast(bool, item["passed"]),
            )
            for item in comparisons
        ),
        reasons=tuple(cast(Sequence[str], document["reasons"])),
    )


def _content_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
