"""Benchmark tabulaire CPU déterministe sur folds walk-forward communs."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sklearn.ensemble import (  # type: ignore[import-untyped]
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
)
from sqlalchemy import Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.ml_models import (
    TabularBenchmarkPrediction as TabularBenchmarkPredictionRow,
)
from metiquo.db.ml_models import TabularBenchmarkRun as TabularBenchmarkRunRow
from metiquo.db.ml_models import TrainingDatasetExample
from metiquo.features import (
    PreprocessorParameters,
    TrainingFeatureRow,
    TrainOnlyPreprocessor,
    TransformedFeatureRow,
)
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
from metiquo.models.datasets import GAME_WINNER_MARKET
from metiquo.models.validation import (
    FoldProbabilities,
    PreparedFold,
    WalkForwardPlan,
    collect_oof_predictions,
    prepare_walk_forward,
)

TABULAR_BENCHMARK_VERSION = "tabular-benchmark-v1"
HIST_GRADIENT_BOOSTING = "hist_gradient_boosting"
GRADIENT_BOOSTING = "gradient_boosting"
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_BASELINES = frozenset({COMPETITION_PRIOR, RECENT_FORM, RATING})
_FORBIDDEN_TOKENS = frozenset({"bookmaker", "market_odds", "odds"})


@dataclass(frozen=True, slots=True)
class TabularFeatureSpec:
    """Sous-ensemble fermé et versionné du feature set P3."""

    numeric_fields: tuple[str, ...] = (
        "rating.difference",
        "form.team_a.ewm_win_rate",
        "form.team_b.ewm_win_rate",
        "side.team_a.adjusted_differential",
        "side.team_b.adjusted_differential",
        "economy.team_a.kills_per_minute",
        "economy.team_b.kills_per_minute",
        "roster.team_a.confidence",
        "roster.team_b.confidence",
        "context.best_of",
    )
    categorical_fields: tuple[str, ...] = (
        "context.patch",
        "context.phase",
        "context.region",
        "side.target.team_a",
    )
    version: str = "game-winner-tabular-features-v1"

    def __post_init__(self) -> None:
        if not self.numeric_fields:
            raise ValueError("au moins une feature numérique est requise")
        fields = (*self.numeric_fields, *self.categorical_fields)
        if len(fields) != len(set(fields)):
            raise ValueError("les features tabulaires doivent être uniques")
        if any(token in field.casefold() for field in fields for token in _FORBIDDEN_TOKENS):
            raise ValueError("les features de cote/bookmaker sont interdites")
        if not self.version.strip():
            raise ValueError("la version des features tabulaires est requise")

    def document(self) -> dict[str, object]:
        return {
            "categorical_fields": list(self.categorical_fields),
            "numeric_fields": list(self.numeric_fields),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class TabularBenchmarkParameters:
    """Configuration CPU et seed commune aux candidats."""

    seed: int = 20260906
    calibration_bins: int = 10
    version: str = TABULAR_BENCHMARK_VERSION

    def __post_init__(self) -> None:
        if self.seed < 0:
            raise ValueError("le seed doit être positif")
        if self.calibration_bins < 2:
            raise ValueError("au moins deux bins de calibration sont requis")
        if not self.version.strip():
            raise ValueError("la version du benchmark est requise")


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    name: str
    hyperparameters: Mapping[str, object]
    metrics: BinaryMetricReport
    fold_metrics: Mapping[int, BinaryMetricReport]
    worst_fold_log_loss: Decimal
    fallback_folds: tuple[int, ...]
    predictions_fingerprint: str
    predictions: tuple[BaselinePrediction, ...]

    def document(self) -> dict[str, object]:
        return {
            "fallback_folds": list(self.fallback_folds),
            "fold_metrics": {
                str(key): value.document() for key, value in sorted(self.fold_metrics.items())
            },
            "hyperparameters": dict(self.hyperparameters),
            "metrics": self.metrics.document(),
            "name": self.name,
            "predictions_fingerprint": self.predictions_fingerprint,
            "worst_fold_log_loss": str(self.worst_fold_log_loss),
        }


@dataclass(frozen=True, slots=True)
class BaselineGateComparison:
    baseline_run_id: UUID
    baseline_name: str
    log_loss_gain: Decimal
    calibration_ece_gain: Decimal
    worst_fold_log_loss_gain: Decimal
    passed: bool

    def document(self) -> dict[str, object]:
        return {
            "baseline_name": self.baseline_name,
            "baseline_run_id": str(self.baseline_run_id),
            "calibration_ece_gain": str(self.calibration_ece_gain),
            "log_loss_gain": str(self.log_loss_gain),
            "passed": self.passed,
            "worst_fold_log_loss_gain": str(self.worst_fold_log_loss_gain),
        }


@dataclass(frozen=True, slots=True)
class PromotionGateReport:
    promotable: bool
    policy_version: str
    comparisons: tuple[BaselineGateComparison, ...]
    failures: tuple[str, ...]

    def document(self) -> dict[str, object]:
        return {
            "comparisons": [item.document() for item in self.comparisons],
            "failures": list(self.failures),
            "policy_version": self.policy_version,
            "promotable": self.promotable,
        }


@dataclass(frozen=True, slots=True)
class TabularBenchmarkRun:
    run_id: UUID
    dataset_id: UUID
    market: str
    benchmark_version: str
    walk_forward_fingerprint: str
    feature_spec: TabularFeatureSpec
    seed: int
    candidates: Mapping[str, CandidateEvaluation]
    selected_candidate: str
    baseline_run_ids: tuple[UUID, ...]
    promotion_gate: PromotionGateReport
    predictions_fingerprint: str
    run_fingerprint: str
    code_commit: str
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", normalize_utc_datetime(self.created_at))

    @property
    def selected(self) -> CandidateEvaluation:
        return self.candidates[self.selected_candidate]

    @property
    def predictions(self) -> tuple[BaselinePrediction, ...]:
        return self.selected.predictions


class _ProbabilisticClassifier(Protocol):
    def fit(self, x: Sequence[Sequence[float]], y: Sequence[int]) -> object: ...

    def predict_proba(self, x: Sequence[Sequence[float]]) -> object: ...


@dataclass(frozen=True, slots=True)
class _Candidate:
    name: str
    hyperparameters: Mapping[str, object]
    factory: Callable[[], _ProbabilisticClassifier]


class TabularBenchmarkRunner:
    """Comparer deux boosters scikit-learn sur les mêmes transformations et folds."""

    def __init__(
        self,
        *,
        code_commit: str,
        features: TabularFeatureSpec | None = None,
        parameters: TabularBenchmarkParameters | None = None,
        clock: Clock | None = None,
    ) -> None:
        if _COMMIT.fullmatch(code_commit) is None:
            raise ValueError("code_commit doit être un hash git hexadécimal")
        self._code_commit = code_commit
        self._features = features or TabularFeatureSpec()
        self._parameters = parameters or TabularBenchmarkParameters()
        self._clock = clock or SystemClock()

    def benchmark(
        self,
        plan: WalkForwardPlan,
        *,
        dataset_id: UUID,
        baseline_runs: Sequence[BaselineRun],
    ) -> TabularBenchmarkRun:
        """Entraîner chaque fold sur son passé et publier le choix métrique."""

        baseline_comparison = assert_baseline_runs_comparable(baseline_runs)
        if (
            baseline_comparison.dataset_id != dataset_id
            or baseline_comparison.walk_forward_fingerprint != plan.fingerprint
        ):
            raise ValueError("les baselines doivent partager le dataset et le plan du benchmark")
        if {run.baseline_name for run in baseline_runs} != _REQUIRED_BASELINES:
            raise ValueError("prior, forme récente et rating sont tous requis")
        prepared = prepare_walk_forward(
            plan,
            rows=_training_rows(plan, self._features),
            preprocessor=TrainOnlyPreprocessor(
                PreprocessorParameters(
                    numeric_fields=self._features.numeric_fields,
                    categorical_fields=self._features.categorical_fields,
                    version=f"train-only-preprocessor:{self._features.version}",
                )
            ),
        )
        evaluations = {
            candidate.name: self._evaluate_candidate(plan, prepared.folds, candidate)
            for candidate in self._candidates()
        }
        selected_name = _selected_candidate(evaluations)
        selected = evaluations[selected_name]
        gate = _promotion_gate(selected, baseline_runs)
        baseline_ids = tuple(
            run.run_id for run in sorted(baseline_runs, key=lambda item: item.baseline_name)
        )
        fingerprint = _content_hash(
            _benchmark_content(
                dataset_id=dataset_id,
                market=GAME_WINNER_MARKET,
                benchmark_version=self._parameters.version,
                walk_forward_fingerprint=plan.fingerprint,
                feature_spec=self._features,
                seed=self._parameters.seed,
                candidates=evaluations,
                selected_candidate=selected_name,
                baseline_run_ids=baseline_ids,
                promotion_gate=gate,
                predictions_fingerprint=selected.predictions_fingerprint,
                code_commit=self._code_commit,
            )
        )
        return TabularBenchmarkRun(
            run_id=uuid5(NAMESPACE_URL, f"metiquo:tabular-benchmark:{fingerprint}"),
            dataset_id=dataset_id,
            market=GAME_WINNER_MARKET,
            benchmark_version=self._parameters.version,
            walk_forward_fingerprint=plan.fingerprint,
            feature_spec=self._features,
            seed=self._parameters.seed,
            candidates=MappingProxyType(evaluations),
            selected_candidate=selected_name,
            baseline_run_ids=baseline_ids,
            promotion_gate=gate,
            predictions_fingerprint=selected.predictions_fingerprint,
            run_fingerprint=fingerprint,
            code_commit=self._code_commit,
            created_at=self._clock.now().value,
        )

    def _evaluate_candidate(
        self,
        plan: WalkForwardPlan,
        folds: Sequence[PreparedFold],
        candidate: _Candidate,
    ) -> CandidateEvaluation:
        fold_probabilities: list[FoldProbabilities] = []
        fallback_folds: list[int] = []
        for fold in folds:
            train_x = [_vector(row) for row in fold.transformed_train]
            validation_x = [_vector(row) for row in fold.transformed_validation]
            train_y = [int(item.label) for item in fold.split.train]
            if len(set(train_y)) < 2:
                probability = (Decimal(sum(train_y)) + Decimal("0.5")) / (
                    Decimal(len(train_y)) + Decimal(1)
                )
                values = {item.example_id: probability for item in fold.split.validation}
                fallback_folds.append(fold.split.fold_index)
            else:
                model = candidate.factory()
                model.fit(train_x, train_y)
                raw = cast(Sequence[Sequence[float]], model.predict_proba(validation_x))
                values = {
                    item.example_id: _probability(raw[index][1])
                    for index, item in enumerate(fold.split.validation)
                }
            fold_probabilities.append(
                FoldProbabilities(
                    fold_index=fold.split.fold_index,
                    probabilities=MappingProxyType(values),
                )
            )
        collected = collect_oof_predictions(plan, fold_probabilities)
        predictions = tuple(
            BaselinePrediction(
                example_id=item.example_id,
                fold_index=item.fold_index,
                cutoff_at=item.cutoff_at,
                label=item.label,
                probability=item.probability,
            )
            for item in collected.predictions
        )
        fold_metrics = _fold_metrics(predictions, self._parameters.calibration_bins)
        return CandidateEvaluation(
            name=candidate.name,
            hyperparameters=candidate.hyperparameters,
            metrics=evaluate_binary_probabilities(
                predictions,
                bin_count=self._parameters.calibration_bins,
            ),
            fold_metrics=MappingProxyType(fold_metrics),
            worst_fold_log_loss=max(item.log_loss for item in fold_metrics.values()),
            fallback_folds=tuple(fallback_folds),
            predictions_fingerprint=_prediction_fingerprint(predictions),
            predictions=predictions,
        )

    def _candidates(self) -> tuple[_Candidate, ...]:
        seed = self._parameters.seed
        histogram: dict[str, object] = {
            "early_stopping": False,
            "l2_regularization": 1.0,
            "learning_rate": 0.05,
            "max_iter": 80,
            "max_leaf_nodes": 15,
            "min_samples_leaf": 5,
            "random_state": seed,
        }
        classic: dict[str, object] = {
            "learning_rate": 0.05,
            "loss": "log_loss",
            "max_depth": 2,
            "min_samples_leaf": 3,
            "n_estimators": 80,
            "random_state": seed,
            "subsample": 1.0,
        }
        return (
            _Candidate(
                name=HIST_GRADIENT_BOOSTING,
                hyperparameters=MappingProxyType(histogram),
                factory=lambda: cast(
                    _ProbabilisticClassifier,
                    HistGradientBoostingClassifier(**histogram),
                ),
            ),
            _Candidate(
                name=GRADIENT_BOOSTING,
                hyperparameters=MappingProxyType(classic),
                factory=lambda: cast(
                    _ProbabilisticClassifier,
                    GradientBoostingClassifier(**classic),
                ),
            ),
        )


class TabularBenchmarkRepository:
    """Publier et relire un benchmark avec toutes ses probabilités OOF."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def record(self, run: TabularBenchmarkRun) -> TabularBenchmarkRun:
        _validate_benchmark(run)
        baseline_repository = BaselineRunRepository(engine=self._engine)
        baseline_runs = tuple(
            baseline
            for run_id in run.baseline_run_ids
            if (baseline := baseline_repository.get(run_id)) is not None
        )
        if len(baseline_runs) != len(run.baseline_run_ids):
            raise ValueError("toutes les baselines du benchmark doivent être publiées")
        comparison = assert_baseline_runs_comparable(baseline_runs)
        if (
            comparison.dataset_id != run.dataset_id
            or comparison.walk_forward_fingerprint != run.walk_forward_fingerprint
            or {item.baseline_name for item in baseline_runs} != _REQUIRED_BASELINES
        ):
            raise ValueError("les baselines publiées ne correspondent pas au benchmark")
        if _promotion_gate(run.selected, baseline_runs) != run.promotion_gate:
            raise ValueError("la décision de promotion ne correspond pas aux baselines publiées")

        runs = cast(Table, TabularBenchmarkRunRow.__table__)
        predictions = cast(Table, TabularBenchmarkPredictionRow.__table__)
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
                raise ValueError("le benchmark ne peut référencer que les exemples de son dataset")
            inserted = connection.execute(
                insert(runs)
                .values(
                    id=run.run_id,
                    dataset_id=run.dataset_id,
                    market=run.market,
                    benchmark_version=run.benchmark_version,
                    walk_forward_fingerprint=run.walk_forward_fingerprint,
                    feature_spec=run.feature_spec.document(),
                    candidate_evaluations={
                        key: value.document() for key, value in sorted(run.candidates.items())
                    },
                    candidate_count=len(run.candidates),
                    selected_candidate=run.selected_candidate,
                    baseline_run_ids=[str(value) for value in run.baseline_run_ids],
                    promotion_gate=run.promotion_gate.document(),
                    promotable=run.promotion_gate.promotable,
                    seed=run.seed,
                    predictions_per_candidate=len(run.predictions),
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
                            "candidate_name": candidate_name,
                            "position": position,
                            "example_id": item.example_id,
                            "fold_index": item.fold_index,
                            "cutoff_at": item.cutoff_at,
                            "label": item.label,
                            "probability": item.probability,
                        }
                        for candidate_name, candidate in sorted(run.candidates.items())
                        for position, item in enumerate(candidate.predictions)
                    ],
                )
        stored = self.get_by_fingerprint(run.run_fingerprint)
        if stored is None:
            raise RuntimeError("le benchmark tabulaire n'a pas été enregistré")
        return stored

    def get(self, run_id: UUID) -> TabularBenchmarkRun | None:
        runs = cast(Table, TabularBenchmarkRunRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one_or_none()
            )
        return self._stored(row) if row is not None else None

    def get_by_fingerprint(self, fingerprint: str) -> TabularBenchmarkRun | None:
        runs = cast(Table, TabularBenchmarkRunRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(runs).where(runs.c.run_fingerprint == fingerprint))
                .mappings()
                .one_or_none()
            )
        return self._stored(row) if row is not None else None

    def _stored(self, row: RowMapping) -> TabularBenchmarkRun:
        predictions = cast(Table, TabularBenchmarkPredictionRow.__table__)
        with self._engine.connect() as connection:
            prediction_rows = (
                connection.execute(
                    select(predictions)
                    .where(predictions.c.run_id == row["id"])
                    .order_by(predictions.c.candidate_name, predictions.c.position)
                )
                .mappings()
                .all()
            )
        grouped: dict[str, list[BaselinePrediction]] = {}
        for item in prediction_rows:
            grouped.setdefault(cast(str, item["candidate_name"]), []).append(
                BaselinePrediction(
                    example_id=cast(UUID, item["example_id"]),
                    fold_index=cast(int, item["fold_index"]),
                    cutoff_at=cast(datetime, item["cutoff_at"]),
                    label=cast(bool, item["label"]),
                    probability=cast(Decimal, item["probability"]),
                )
            )
        candidate_documents = cast(Mapping[str, Mapping[str, object]], row["candidate_evaluations"])
        candidates = {
            name: _candidate_from_document(document, tuple(grouped.get(name, ())))
            for name, document in sorted(candidate_documents.items())
        }
        feature_document = cast(Mapping[str, object], row["feature_spec"])
        return TabularBenchmarkRun(
            run_id=cast(UUID, row["id"]),
            dataset_id=cast(UUID, row["dataset_id"]),
            market=cast(str, row["market"]),
            benchmark_version=cast(str, row["benchmark_version"]),
            walk_forward_fingerprint=cast(str, row["walk_forward_fingerprint"]),
            feature_spec=TabularFeatureSpec(
                numeric_fields=tuple(cast(Sequence[str], feature_document["numeric_fields"])),
                categorical_fields=tuple(
                    cast(Sequence[str], feature_document["categorical_fields"])
                ),
                version=cast(str, feature_document["version"]),
            ),
            seed=cast(int, row["seed"]),
            candidates=MappingProxyType(candidates),
            selected_candidate=cast(str, row["selected_candidate"]),
            baseline_run_ids=tuple(
                UUID(value) for value in cast(Sequence[str], row["baseline_run_ids"])
            ),
            promotion_gate=_gate_from_document(cast(Mapping[str, object], row["promotion_gate"])),
            predictions_fingerprint=cast(str, row["predictions_fingerprint"]),
            run_fingerprint=cast(str, row["run_fingerprint"]),
            code_commit=cast(str, row["code_commit"]),
            created_at=cast(datetime, row["created_at"]),
        )


def _training_rows(
    plan: WalkForwardPlan,
    features: TabularFeatureSpec,
) -> tuple[TrainingFeatureRow, ...]:
    development = {
        item.example_id: item for fold in plan.folds for item in (*fold.train, *fold.validation)
    }
    return tuple(
        TrainingFeatureRow(
            row_id=item.example_id,
            event_time=item.cutoff_at,
            numeric={
                field: _optional_decimal(item.feature_values.get(field))
                for field in features.numeric_fields
            },
            categorical={
                field: value if isinstance((value := item.feature_values.get(field)), str) else None
                for field in features.categorical_fields
            },
        )
        for item in sorted(
            development.values(), key=lambda value: (value.cutoff_at, value.example_id)
        )
    )


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _vector(row: TransformedFeatureRow) -> list[float]:
    values: list[float] = []
    for _name, value in sorted(row.values.items()):
        if value is None:
            values.append(0.0)
        elif isinstance(value, bool):
            values.append(float(int(value)))
        elif isinstance(value, (Decimal, int, float)):
            values.append(float(value))
        else:
            raise ValueError("le préprocesseur a produit une valeur non numérique")
    return values


def _probability(value: float) -> Decimal:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("le candidat doit produire une probabilité finie dans [0,1]")
    return Decimal(str(value))


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


def _selected_candidate(candidates: Mapping[str, CandidateEvaluation]) -> str:
    return min(
        candidates,
        key=lambda name: (
            candidates[name].metrics.log_loss,
            candidates[name].metrics.calibration_ece,
            candidates[name].worst_fold_log_loss,
            name,
        ),
    )


def _promotion_gate(
    candidate: CandidateEvaluation,
    baselines: Sequence[BaselineRun],
) -> PromotionGateReport:
    comparisons: list[BaselineGateComparison] = []
    failures: list[str] = []
    for baseline in sorted(baselines, key=lambda item: item.baseline_name):
        baseline_worst = max(
            report.log_loss
            for report in _fold_metrics(baseline.predictions, baseline.metrics.bin_count).values()
        )
        log_gain = baseline.metrics.log_loss - candidate.metrics.log_loss
        calibration_gain = baseline.metrics.calibration_ece - candidate.metrics.calibration_ece
        robustness_gain = baseline_worst - candidate.worst_fold_log_loss
        passed = log_gain > 0 and calibration_gain > 0 and robustness_gain > 0
        comparisons.append(
            BaselineGateComparison(
                baseline_run_id=baseline.run_id,
                baseline_name=baseline.baseline_name,
                log_loss_gain=log_gain,
                calibration_ece_gain=calibration_gain,
                worst_fold_log_loss_gain=robustness_gain,
                passed=passed,
            )
        )
        if not passed:
            failures.append(f"BASELINE_NOT_BEATEN:{baseline.baseline_name}")
    return PromotionGateReport(
        promotable=not failures,
        policy_version="complex-model-promotion-v1",
        comparisons=tuple(comparisons),
        failures=tuple(failures),
    )


def _validate_benchmark(run: TabularBenchmarkRun) -> None:
    if run.market != GAME_WINNER_MARKET:
        raise ValueError("seul le marché game_winner est pris en charge")
    if not run.benchmark_version.strip() or run.seed < 0:
        raise ValueError("la version et le seed du benchmark sont invalides")
    if _COMMIT.fullmatch(run.code_commit) is None:
        raise ValueError("code_commit invalide")
    for fingerprint in (
        run.walk_forward_fingerprint,
        run.predictions_fingerprint,
        run.run_fingerprint,
    ):
        if _FINGERPRINT.fullmatch(fingerprint) is None:
            raise ValueError("fingerprint du benchmark invalide")
    if set(run.candidates) != {GRADIENT_BOOSTING, HIST_GRADIENT_BOOSTING}:
        raise ValueError("les deux candidats tabulaires attendus sont requis")
    if len(run.baseline_run_ids) != 3 or len(set(run.baseline_run_ids)) != 3:
        raise ValueError("trois baselines distinctes sont requises")

    expected_scope: tuple[tuple[UUID, int, datetime, bool], ...] | None = None
    for name, candidate in run.candidates.items():
        if candidate.name != name:
            raise ValueError("le nom d'un candidat ne correspond pas à sa clé")
        if candidate.hyperparameters.get("random_state") != run.seed:
            raise ValueError("chaque candidat doit conserver le seed du benchmark")
        if not candidate.predictions:
            raise ValueError("chaque candidat doit publier ses prédictions OOF")
        scope = tuple(
            (item.example_id, item.fold_index, item.cutoff_at, item.label)
            for item in candidate.predictions
        )
        if expected_scope is None:
            expected_scope = scope
        elif scope != expected_scope:
            raise ValueError("les candidats doivent couvrir exactement les mêmes exemples OOF")
        if _prediction_fingerprint(candidate.predictions) != candidate.predictions_fingerprint:
            raise ValueError("le fingerprint d'un candidat ne correspond pas à ses prédictions")
        metrics = evaluate_binary_probabilities(
            candidate.predictions,
            bin_count=candidate.metrics.bin_count,
        )
        if metrics != candidate.metrics:
            raise ValueError("les métriques d'un candidat ne correspondent pas à ses prédictions")
        fold_metrics = _fold_metrics(candidate.predictions, candidate.metrics.bin_count)
        if dict(candidate.fold_metrics) != fold_metrics:
            raise ValueError("les métriques par fold ne correspondent pas aux prédictions")
        if candidate.worst_fold_log_loss != max(item.log_loss for item in fold_metrics.values()):
            raise ValueError("la robustesse temporelle du candidat est incohérente")
        if not set(candidate.fallback_folds) <= set(fold_metrics):
            raise ValueError("un fold de fallback est absent des prédictions")

    if run.selected_candidate != _selected_candidate(run.candidates):
        raise ValueError("le candidat sélectionné ne correspond pas à la politique métrique")
    if run.predictions_fingerprint != run.selected.predictions_fingerprint:
        raise ValueError("le fingerprint publié ne correspond pas au candidat sélectionné")
    comparisons = run.promotion_gate.comparisons
    if (
        len(comparisons) != 3
        or {item.baseline_run_id for item in comparisons} != set(run.baseline_run_ids)
        or {item.baseline_name for item in comparisons} != _REQUIRED_BASELINES
    ):
        raise ValueError("le gate doit comparer les trois baselines du benchmark")
    expected_failures = tuple(
        f"BASELINE_NOT_BEATEN:{item.baseline_name}" for item in comparisons if not item.passed
    )
    if run.promotion_gate.failures != expected_failures or run.promotion_gate.promotable != (
        not expected_failures
    ):
        raise ValueError("la décision de promotion est incohérente")

    expected_fingerprint = _content_hash(
        _benchmark_content(
            dataset_id=run.dataset_id,
            market=run.market,
            benchmark_version=run.benchmark_version,
            walk_forward_fingerprint=run.walk_forward_fingerprint,
            feature_spec=run.feature_spec,
            seed=run.seed,
            candidates=run.candidates,
            selected_candidate=run.selected_candidate,
            baseline_run_ids=run.baseline_run_ids,
            promotion_gate=run.promotion_gate,
            predictions_fingerprint=run.predictions_fingerprint,
            code_commit=run.code_commit,
        )
    )
    if expected_fingerprint != run.run_fingerprint:
        raise ValueError("le fingerprint du benchmark ne correspond pas à son contenu")
    if run.run_id != uuid5(NAMESPACE_URL, f"metiquo:tabular-benchmark:{expected_fingerprint}"):
        raise ValueError("l'identifiant du benchmark ne correspond pas à son contenu")


def _candidate_from_document(
    document: Mapping[str, object],
    predictions: tuple[BaselinePrediction, ...],
) -> CandidateEvaluation:
    fold_documents = cast(Mapping[str, Mapping[str, object]], document["fold_metrics"])
    return CandidateEvaluation(
        name=cast(str, document["name"]),
        hyperparameters=MappingProxyType(
            dict(cast(Mapping[str, object], document["hyperparameters"]))
        ),
        metrics=binary_metric_report_from_document(cast(Mapping[str, object], document["metrics"])),
        fold_metrics=MappingProxyType(
            {
                int(index): binary_metric_report_from_document(metrics)
                for index, metrics in fold_documents.items()
            }
        ),
        worst_fold_log_loss=Decimal(cast(str, document["worst_fold_log_loss"])),
        fallback_folds=tuple(cast(Sequence[int], document["fallback_folds"])),
        predictions_fingerprint=cast(str, document["predictions_fingerprint"]),
        predictions=predictions,
    )


def _gate_from_document(document: Mapping[str, object]) -> PromotionGateReport:
    comparison_documents = cast(Sequence[Mapping[str, object]], document["comparisons"])
    return PromotionGateReport(
        promotable=cast(bool, document["promotable"]),
        policy_version=cast(str, document["policy_version"]),
        comparisons=tuple(
            BaselineGateComparison(
                baseline_run_id=UUID(cast(str, item["baseline_run_id"])),
                baseline_name=cast(str, item["baseline_name"]),
                log_loss_gain=Decimal(cast(str, item["log_loss_gain"])),
                calibration_ece_gain=Decimal(cast(str, item["calibration_ece_gain"])),
                worst_fold_log_loss_gain=Decimal(cast(str, item["worst_fold_log_loss_gain"])),
                passed=cast(bool, item["passed"]),
            )
            for item in comparison_documents
        ),
        failures=tuple(cast(Sequence[str], document["failures"])),
    )


def _benchmark_content(
    *,
    dataset_id: UUID,
    market: str,
    benchmark_version: str,
    walk_forward_fingerprint: str,
    feature_spec: TabularFeatureSpec,
    seed: int,
    candidates: Mapping[str, CandidateEvaluation],
    selected_candidate: str,
    baseline_run_ids: Sequence[UUID],
    promotion_gate: PromotionGateReport,
    predictions_fingerprint: str,
    code_commit: str,
) -> dict[str, object]:
    return {
        "baseline_run_ids": [str(value) for value in baseline_run_ids],
        "benchmark_version": benchmark_version,
        "candidates": {key: value.document() for key, value in sorted(candidates.items())},
        "code_commit": code_commit,
        "dataset_id": str(dataset_id),
        "feature_spec": feature_spec.document(),
        "market": market,
        "predictions_fingerprint": predictions_fingerprint,
        "promotion_gate": promotion_gate.document(),
        "seed": seed,
        "selected_candidate": selected_candidate,
        "walk_forward_fingerprint": walk_forward_fingerprint,
    }


def _prediction_fingerprint(predictions: Sequence[BaselinePrediction]) -> str:
    return _content_hash([item.document() for item in predictions])


def _content_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
