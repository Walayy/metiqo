"""Gate d'entraînement game winner et artefact d'inférence reproductible."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from types import MappingProxyType
from typing import Protocol, cast
from uuid import UUID

from sklearn.ensemble import (  # type: ignore[import-untyped]
    GradientBoostingClassifier,
    HistGradientBoostingClassifier,
)
from sqlalchemy import Engine, Table, select

from metiquo.contracts.enums import GameTitle, MarketType
from metiquo.db.ml_models import TrainingDataset
from metiquo.features import (
    FeatureCutoff,
    PreprocessorParameters,
    TrainingFeatureRow,
    TrainOnlyPreprocessor,
    TransformedFeatureRow,
)
from metiquo.foundation.time import Clock, SystemClock
from metiquo.models.baselines import BaselineEvaluator, BaselineRun, BaselineRunRepository
from metiquo.models.benchmark import (
    GRADIENT_BOOSTING,
    HIST_GRADIENT_BOOSTING,
    TabularBenchmarkParameters,
    TabularBenchmarkRepository,
    TabularBenchmarkRun,
    TabularBenchmarkRunner,
    TabularFeatureSpec,
)
from metiquo.models.calibration import (
    CalibrationSearchParameters,
    CalibratorArtifact,
    CalibratorArtifactRepository,
    CalibratorTrainer,
    calibrate_probability,
)
from metiquo.models.datasets import (
    GAME_WINNER_MARKET,
    GameWinnerDatasetBuilder,
    StoredTrainingDataset,
)
from metiquo.models.ensemble import (
    EnsembleCandidateEvaluator,
    EnsembleCandidateRepository,
    EnsembleCandidateRun,
)
from metiquo.models.evaluation import EvaluationReport, EvaluationReportBuilder
from metiquo.models.lifecycle import ModelLifecycle
from metiquo.models.rating import (
    RatingArtifact,
    RatingArtifactRepository,
    RatingBaselineTrainer,
    rating_win_probability,
)
from metiquo.models.registry import (
    CANDIDATE,
    ModelArtifactStore,
    ModelRegistration,
    ModelRegistry,
)
from metiquo.models.uncertainty import UncertaintyArtifact, UncertaintyArtifactBuilder
from metiquo.models.validation import (
    TrainingExampleRepository,
    WalkForwardConfig,
    WalkForwardExample,
    WalkForwardPlan,
    WalkForwardSplitter,
)

REPRODUCIBLE_ARTIFACT_VERSION = "game-winner-reproducible-v1"
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_FEATURE_QUANTUM = Decimal("0.000001")


class _ProbabilisticClassifier(Protocol):
    def fit(self, x: Sequence[Sequence[float]], y: Sequence[int]) -> object: ...

    def predict_proba(self, x: Sequence[Sequence[float]]) -> object: ...


@dataclass(frozen=True, slots=True)
class ReproducedPrediction:
    dataset_id: UUID
    example_id: UUID
    feature_snapshot_id: UUID
    raw_probability: Decimal
    calibrated_probability: Decimal
    artifact_fingerprint: str

    def document(self) -> dict[str, object]:
        return {
            "artifact_fingerprint": self.artifact_fingerprint,
            "calibrated_probability": str(self.calibrated_probability),
            "dataset_id": str(self.dataset_id),
            "example_id": str(self.example_id),
            "feature_snapshot_id": str(self.feature_snapshot_id),
            "raw_probability": str(self.raw_probability),
        }


@dataclass(frozen=True, slots=True)
class TrainingGateResult:
    model_version_id: UUID
    model_status: str
    dataset_id: UUID
    dataset_hash: str
    plan: WalkForwardPlan
    baselines: tuple[BaselineRun, ...]
    benchmark: TabularBenchmarkRun
    ensemble: EnsembleCandidateRun
    calibrator: CalibratorArtifact
    uncertainty: UncertaintyArtifact
    evaluation: EvaluationReport
    reproduction: ReproducedPrediction

    @property
    def gate_passed(self) -> bool:
        return self.benchmark.promotion_gate.promotable

    def document(self) -> dict[str, object]:
        return {
            "baselineRuns": [
                {
                    "metrics": item.metrics.document(),
                    "name": item.baseline_name,
                    "runId": str(item.run_id),
                }
                for item in sorted(self.baselines, key=lambda value: value.baseline_name)
            ],
            "benchmark": {
                "gate": self.benchmark.promotion_gate.document(),
                "metrics": self.benchmark.selected.metrics.document(),
                "runId": str(self.benchmark.run_id),
                "selectedCandidate": self.benchmark.selected_candidate,
            },
            "calibration": {
                "artifactId": str(self.calibrator.artifact_id),
                "method": self.calibrator.method,
                "metrics": self.calibrator.metrics.document(),
            },
            "datasetHash": self.dataset_hash,
            "datasetId": str(self.dataset_id),
            "evaluation": self.evaluation.document(),
            "gatePassed": self.gate_passed,
            "modelStatus": self.model_status,
            "modelVersionId": str(self.model_version_id),
            "reproduction": self.reproduction.document(),
            "walkForward": {
                "finalTestExamples": len(self.plan.final_test),
                "fingerprint": self.plan.fingerprint,
                "folds": len(self.plan.folds),
                "initialTrainExamples": len(self.plan.initial_train),
                "oofValidationExamples": len(self.plan.oof_validation),
            },
        }


class GameWinnerTrainingWorkflow:
    """Assembler et publier toutes les preuves du gate P4 sans auto-promotion."""

    def __init__(
        self,
        *,
        engine: Engine,
        artifacts: ModelArtifactStore,
        code_commit: str,
        dataset_id: UUID | None = None,
        walk_forward: WalkForwardConfig | None = None,
        features: TabularFeatureSpec | None = None,
        clock: Clock | None = None,
    ) -> None:
        if _COMMIT.fullmatch(code_commit) is None:
            raise ValueError("code_commit doit être un hash git hexadécimal")
        self._engine = engine
        self._artifacts = artifacts
        self._code_commit = code_commit
        self._dataset_id = dataset_id
        self._walk_forward = walk_forward or WalkForwardConfig(
            minimum_train_periods=20,
            validation_periods=10,
            final_test_periods=10,
        )
        self._features = features or TabularFeatureSpec()
        self._clock = clock or SystemClock()

    def train(self, game_title: GameTitle, market_type: MarketType) -> UUID:
        """Satisfaire la frontière ML-016 et renvoyer la version créée."""

        if (
            game_title is not GameTitle.LEAGUE_OF_LEGENDS
            or market_type is not MarketType.MATCH_WINNER
        ):
            raise ValueError("seul lol/game_winner est pris en charge")
        return self.run().model_version_id

    def run(self) -> TrainingGateResult:
        dataset = self._load_dataset()
        examples = TrainingExampleRepository(engine=self._engine).load(dataset)
        plan = WalkForwardSplitter(self._walk_forward).split(examples)

        simple_baselines = BaselineEvaluator(
            code_commit=self._code_commit,
            clock=self._clock,
        ).evaluate(plan, dataset_id=dataset.dataset_id)
        rating = RatingBaselineTrainer(
            code_commit=self._code_commit,
            clock=self._clock,
        ).train(plan, dataset_id=dataset.dataset_id)
        rating_repository = RatingArtifactRepository(engine=self._engine)
        rating_repository.record(rating.artifact)
        baseline_repository = BaselineRunRepository(engine=self._engine)
        baselines = tuple(
            baseline_repository.record(item) for item in (*simple_baselines, rating.run)
        )

        benchmark = TabularBenchmarkRunner(
            code_commit=self._code_commit,
            features=self._features,
            parameters=TabularBenchmarkParameters(),
            clock=self._clock,
        ).benchmark(plan, dataset_id=dataset.dataset_id, baseline_runs=baselines)
        benchmark = TabularBenchmarkRepository(engine=self._engine).record(benchmark)
        ensemble = EnsembleCandidateEvaluator(
            code_commit=self._code_commit,
            clock=self._clock,
        ).evaluate(benchmark, baseline_runs=baselines)
        ensemble = EnsembleCandidateRepository(engine=self._engine).record(ensemble)
        calibrator = CalibratorTrainer(
            code_commit=self._code_commit,
            search=CalibrationSearchParameters(),
            clock=self._clock,
        ).train(plan, benchmark=benchmark, ensemble=ensemble)
        calibrator = CalibratorArtifactRepository(engine=self._engine).record(calibrator)
        uncertainty = UncertaintyArtifactBuilder(
            code_commit=self._code_commit,
            clock=self._clock,
        ).build(calibrator)
        evaluation = EvaluationReportBuilder(code_commit=self._code_commit).build(
            plan,
            calibrator=calibrator,
            uncertainty=uncertainty,
        )
        artifact_payload, reproduction = build_reproducible_artifact(
            dataset,
            plan=plan,
            benchmark=benchmark,
            rating=rating.artifact,
            ensemble=ensemble,
            calibrator=calibrator,
            uncertainty=uncertainty,
        )
        algorithm = "rating_tabular_ensemble" if ensemble.enabled else benchmark.selected_candidate
        hyperparameters = {
            **dict(benchmark.selected.hyperparameters),
            "ensemble_enabled": ensemble.enabled,
            "rating_weight": str(ensemble.selected_rating_weight),
        }
        gate_reason = (
            "walk-forward gates passed; manual promotion required"
            if benchmark.promotion_gate.promotable
            else "walk-forward gates failed; candidate blocked"
        )
        registry = ModelRegistry(
            engine=self._engine,
            artifacts=self._artifacts,
            clock=self._clock,
        )
        version = registry.register(
            ModelRegistration(
                algorithm=algorithm,
                hyperparameters=MappingProxyType(hyperparameters),
                registered_by="model-train",
                reason=gate_reason,
                code_commit=self._code_commit,
            ),
            evaluation=evaluation,
            uncertainty=uncertainty,
            artifact_payload=artifact_payload,
        )
        status = version.status
        if not benchmark.promotion_gate.promotable and status == CANDIDATE:
            status = (
                ModelLifecycle(engine=self._engine, clock=self._clock)
                .block(
                    version.model_version_id,
                    actor="model-train",
                    reason=";".join(benchmark.promotion_gate.failures),
                )
                .status
            )
        return TrainingGateResult(
            model_version_id=version.model_version_id,
            model_status=status,
            dataset_id=dataset.dataset_id,
            dataset_hash=dataset.dataset_hash,
            plan=plan,
            baselines=baselines,
            benchmark=benchmark,
            ensemble=ensemble,
            calibrator=calibrator,
            uncertainty=uncertainty,
            evaluation=evaluation,
            reproduction=reproduction,
        )

    def _load_dataset(self) -> StoredTrainingDataset:
        dataset_id = self._dataset_id or _latest_dataset_id(self._engine)
        if dataset_id is None:
            raise ValueError("aucun dataset game_winner versionné n'est disponible")
        dataset = GameWinnerDatasetBuilder(
            engine=self._engine,
            code_commit=self._code_commit,
        ).get(dataset_id)
        if dataset is None or dataset.market != GAME_WINNER_MARKET:
            raise ValueError("dataset game_winner introuvable")
        return dataset


def build_reproducible_artifact(
    dataset: StoredTrainingDataset,
    *,
    plan: WalkForwardPlan,
    benchmark: TabularBenchmarkRun,
    rating: RatingArtifact,
    ensemble: EnsembleCandidateRun,
    calibrator: CalibratorArtifact,
    uncertainty: UncertaintyArtifact,
) -> tuple[bytes, ReproducedPrediction]:
    """Figer recette, train, préprocesseur et exemple final sans son label."""

    if not plan.final_test:
        raise ValueError("un exemple de test final est requis pour la preuve")
    if any(
        value != dataset.dataset_id
        for value in (benchmark.dataset_id, rating.dataset_id, calibrator.dataset_id)
    ):
        raise ValueError("les artefacts doivent tous référencer le dataset exact")
    features = benchmark.feature_spec
    development = tuple(
        sorted(
            {
                item.example_id: item for item in (*plan.initial_train, *plan.oof_validation)
            }.values(),
            key=lambda item: (item.cutoff_at, item.example_id),
        )
    )
    preprocessor = TrainOnlyPreprocessor(
        PreprocessorParameters(
            numeric_fields=features.numeric_fields,
            categorical_fields=features.categorical_fields,
            version=f"train-only-preprocessor:{features.version}",
        )
    )
    training_rows = tuple(_training_row(item, features) for item in development)
    final_example = min(plan.final_test, key=lambda item: (item.cutoff_at, item.example_id))
    preprocessor_artifact = preprocessor.fit(
        training_rows,
        cutoff=FeatureCutoff(final_example.cutoff_at),
    )
    transformed_training = tuple(
        preprocessor.transform(preprocessor_artifact, item) for item in training_rows
    )
    transformed_final = preprocessor.transform(
        preprocessor_artifact,
        _training_row(final_example, features),
    )
    vectors = tuple(_vector(item) for item in transformed_training)
    labels = tuple(int(item.label) for item in development)
    tabular_probability, fallback = _fit_probability(
        benchmark.selected_candidate,
        benchmark.selected.hyperparameters,
        vectors,
        labels,
        _vector(transformed_final),
    )
    raw_probability = _source_probability(
        tabular_probability,
        final_example,
        rating=rating,
        ensemble=ensemble,
    )
    calibrated_probability = calibrate_probability(
        calibrator.method,
        calibrator.parameters,
        raw_probability,
    )
    vector_names = tuple(sorted(transformed_final.values))
    content: dict[str, object] = {
        "benchmark": {
            "run_id": str(benchmark.run_id),
            "walk_forward_fingerprint": benchmark.walk_forward_fingerprint,
        },
        "calibrator": {
            "artifact_id": str(calibrator.artifact_id),
            "method": calibrator.method,
            "parameters": dict(calibrator.parameters),
        },
        "dataset": {
            "dataset_hash": dataset.dataset_hash,
            "dataset_id": str(dataset.dataset_id),
            "feature_set_version": dataset.feature_set_version,
        },
        "ensemble": {
            "enabled": ensemble.enabled,
            "rating_feature": rating.rating_feature,
            "rating_scale": str(rating.selected_scale),
            "rating_weight": str(ensemble.selected_rating_weight),
        },
        "feature_spec": features.document(),
        "model": {
            "algorithm": benchmark.selected_candidate,
            "fallback_probability": str(fallback) if fallback is not None else None,
            "hyperparameters": dict(benchmark.selected.hyperparameters),
            "labels": list(labels),
            "training_example_ids": [str(item.example_id) for item in development],
            "training_vectors": [[repr(value) for value in row] for row in vectors],
        },
        "prediction_example": {
            "calibrated_probability": str(calibrated_probability),
            "example_id": str(final_example.example_id),
            "feature_snapshot_id": str(final_example.feature_snapshot_id),
            "raw_probability": str(raw_probability),
        },
        "preprocessor": {
            "categorical": {
                key: dict(value) for key, value in sorted(preprocessor_artifact.categorical.items())
            },
            "fingerprint": preprocessor_artifact.fingerprint,
            "numeric": {
                key: {
                    "mean": str(value.mean) if value.mean is not None else None,
                    "standard_deviation": (
                        str(value.standard_deviation)
                        if value.standard_deviation is not None
                        else None
                    ),
                }
                for key, value in sorted(preprocessor_artifact.numeric.items())
            },
            "vector_names": list(vector_names),
            "version": preprocessor_artifact.version,
        },
        "schema_version": REPRODUCIBLE_ARTIFACT_VERSION,
        "uncertainty": {
            "artifact_id": str(uncertainty.artifact_id),
            "fingerprint": uncertainty.artifact_fingerprint,
        },
    }
    fingerprint = _content_hash(content)
    payload = _json_bytes({**content, "artifact_fingerprint": fingerprint})
    reproduction = reproduce_prediction(
        payload,
        dataset_id=dataset.dataset_id,
        example=final_example,
    )
    if (
        reproduction.raw_probability != raw_probability
        or reproduction.calibrated_probability != calibrated_probability
    ):
        raise RuntimeError("la prédiction n'est pas reproductible depuis l'artefact")
    return payload, reproduction


def reproduce_prediction(
    payload: bytes,
    *,
    dataset_id: UUID,
    example: WalkForwardExample,
) -> ReproducedPrediction:
    """Rejouer l'inférence depuis les seuls octets vérifiés et le snapshot exact."""

    loaded = json.loads(payload)
    if not isinstance(loaded, dict):
        raise ValueError("artefact modèle invalide")
    document = cast(dict[str, object], loaded)
    fingerprint = cast(str, document.get("artifact_fingerprint"))
    content = {key: value for key, value in document.items() if key != "artifact_fingerprint"}
    if fingerprint != _content_hash(content):
        raise ValueError("fingerprint interne de l'artefact invalide")
    if document.get("schema_version") != REPRODUCIBLE_ARTIFACT_VERSION:
        raise ValueError("version d'artefact modèle inconnue")
    dataset = _document(document, "dataset")
    prediction = _document(document, "prediction_example")
    if UUID(cast(str, dataset["dataset_id"])) != dataset_id:
        raise ValueError("le dataset demandé ne correspond pas à l'artefact")
    if UUID(cast(str, prediction["example_id"])) != example.example_id:
        raise ValueError("l'exemple demandé ne correspond pas à la preuve")
    if UUID(cast(str, prediction["feature_snapshot_id"])) != example.feature_snapshot_id:
        raise ValueError("le feature snapshot demandé ne correspond pas à la preuve")

    feature_spec = _document(document, "feature_spec")
    preprocessor = _document(document, "preprocessor")
    vector = _reproduce_vector(feature_spec, preprocessor, example)
    model = _document(document, "model")
    training_vectors = tuple(
        tuple(float(value) for value in row)
        for row in cast(Sequence[Sequence[str]], model["training_vectors"])
    )
    labels = tuple(int(value) for value in cast(Sequence[int], model["labels"]))
    fallback_value = model.get("fallback_probability")
    if fallback_value is None:
        fitted = _classifier(
            cast(str, model["algorithm"]),
            cast(Mapping[str, object], model["hyperparameters"]),
        )
        fitted.fit(training_vectors, labels)
        raw = cast(Sequence[Sequence[float]], fitted.predict_proba((vector,)))
        tabular_probability = _probability(raw[0][1])
    else:
        tabular_probability = Decimal(cast(str, fallback_value))
    ensemble = _document(document, "ensemble")
    raw_probability = tabular_probability
    if cast(bool, ensemble["enabled"]):
        rating_value = _required_decimal(
            example.feature_values.get(cast(str, ensemble["rating_feature"])),
            "rating",
        )
        rating_probability = rating_win_probability(
            rating_value,
            scale=Decimal(cast(str, ensemble["rating_scale"])),
        )
        rating_weight = Decimal(cast(str, ensemble["rating_weight"]))
        raw_probability = (
            rating_weight * rating_probability + (Decimal(1) - rating_weight) * tabular_probability
        )
    calibrator = _document(document, "calibrator")
    calibrated = calibrate_probability(
        cast(str, calibrator["method"]),
        cast(Mapping[str, object], calibrator["parameters"]),
        raw_probability,
    )
    if raw_probability != Decimal(cast(str, prediction["raw_probability"])):
        raise ValueError("la probabilité brute reproduite diverge de la preuve")
    if calibrated != Decimal(cast(str, prediction["calibrated_probability"])):
        raise ValueError("la probabilité calibrée reproduite diverge de la preuve")
    return ReproducedPrediction(
        dataset_id=dataset_id,
        example_id=example.example_id,
        feature_snapshot_id=example.feature_snapshot_id,
        raw_probability=raw_probability,
        calibrated_probability=calibrated,
        artifact_fingerprint=fingerprint,
    )


def _latest_dataset_id(engine: Engine) -> UUID | None:
    datasets = cast(Table, TrainingDataset.__table__)
    with engine.connect() as connection:
        value = connection.execute(
            select(datasets.c.id)
            .where(datasets.c.market == GAME_WINNER_MARKET)
            .order_by(datasets.c.created_at.desc(), datasets.c.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    return cast(UUID | None, value)


def _training_row(
    example: WalkForwardExample,
    features: TabularFeatureSpec,
) -> TrainingFeatureRow:
    return TrainingFeatureRow(
        row_id=example.example_id,
        event_time=example.cutoff_at,
        numeric={
            field: _optional_decimal(example.feature_values.get(field))
            for field in features.numeric_fields
        },
        categorical={
            field: value if isinstance((value := example.feature_values.get(field)), str) else None
            for field in features.categorical_fields
        },
    )


def _fit_probability(
    algorithm: str,
    hyperparameters: Mapping[str, object],
    vectors: Sequence[Sequence[float]],
    labels: Sequence[int],
    prediction_vector: Sequence[float],
) -> tuple[Decimal, Decimal | None]:
    if len(set(labels)) < 2:
        fallback = (Decimal(sum(labels)) + Decimal("0.5")) / (Decimal(len(labels)) + Decimal(1))
        return fallback, fallback
    model = _classifier(algorithm, hyperparameters)
    model.fit(vectors, labels)
    raw = cast(Sequence[Sequence[float]], model.predict_proba((prediction_vector,)))
    return _probability(raw[0][1]), None


def _classifier(
    algorithm: str,
    hyperparameters: Mapping[str, object],
) -> _ProbabilisticClassifier:
    parameters = dict(hyperparameters)
    if algorithm == HIST_GRADIENT_BOOSTING:
        return cast(
            _ProbabilisticClassifier,
            HistGradientBoostingClassifier(**parameters),
        )
    if algorithm == GRADIENT_BOOSTING:
        return cast(
            _ProbabilisticClassifier,
            GradientBoostingClassifier(**parameters),
        )
    raise ValueError(f"algorithme tabulaire inconnu: {algorithm}")


def _source_probability(
    tabular_probability: Decimal,
    example: WalkForwardExample,
    *,
    rating: RatingArtifact,
    ensemble: EnsembleCandidateRun,
) -> Decimal:
    if not ensemble.enabled:
        return tabular_probability
    rating_value = _required_decimal(
        example.feature_values.get(rating.rating_feature),
        rating.rating_feature,
    )
    rating_probability = rating_win_probability(rating_value, scale=rating.selected_scale)
    weight = ensemble.selected_rating_weight
    return weight * rating_probability + (Decimal(1) - weight) * tabular_probability


def _reproduce_vector(
    feature_spec: Mapping[str, object],
    preprocessor: Mapping[str, object],
    example: WalkForwardExample,
) -> tuple[float, ...]:
    values: dict[str, Decimal | int | bool | None] = {}
    numeric = cast(Mapping[str, Mapping[str, object]], preprocessor["numeric"])
    for field in cast(Sequence[str], feature_spec["numeric_fields"]):
        raw = _optional_decimal(example.feature_values.get(field))
        transform = numeric[field]
        mean_value = transform["mean"]
        standard_deviation_value = transform["standard_deviation"]
        scaled = None
        if raw is not None and mean_value is not None and standard_deviation_value is not None:
            scaled = (
                (raw - Decimal(cast(str, mean_value)))
                / Decimal(cast(str, standard_deviation_value))
            ).quantize(_FEATURE_QUANTUM, rounding=ROUND_HALF_EVEN)
        values[f"numeric.{field}.scaled"] = scaled
        values[f"numeric.{field}.available"] = raw is not None
        values[f"numeric.{field}.transform_available"] = scaled is not None
    categorical = cast(Mapping[str, Mapping[str, int]], preprocessor["categorical"])
    for field in cast(Sequence[str], feature_spec["categorical_fields"]):
        raw_value = example.feature_values.get(field)
        raw_category = raw_value if isinstance(raw_value, str) else None
        code = categorical[field].get(raw_category) if raw_category is not None else None
        values[f"categorical.{field}.code"] = code
        values[f"categorical.{field}.available"] = raw_category is not None
        values[f"categorical.{field}.ood"] = raw_category is not None and code is None
    names = tuple(sorted(values))
    if names != tuple(cast(Sequence[str], preprocessor["vector_names"])):
        raise ValueError("le schéma du vecteur ne correspond pas à l'artefact")
    return tuple(_float_value(values[name]) for name in names)


def _vector(row: TransformedFeatureRow) -> tuple[float, ...]:
    return tuple(_float_value(value) for _name, value in sorted(row.values.items()))


def _float_value(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (Decimal, int, float)):
        return float(value)
    raise ValueError("le préprocesseur a produit une valeur non numérique")


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _required_decimal(value: object, name: str) -> Decimal:
    result = _optional_decimal(value)
    if result is None:
        raise ValueError(f"feature requise absente ou invalide: {name}")
    return result


def _probability(value: float) -> Decimal:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("le modèle doit produire une probabilité finie dans [0,1]")
    return Decimal(str(value))


def _document(document: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"section d'artefact invalide: {key}")
    return cast(Mapping[str, object], value)


def _json_bytes(document: object) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _content_hash(document: object) -> str:
    return hashlib.sha256(_json_bytes(document)).hexdigest()
