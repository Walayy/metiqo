"""Baselines OOF auditées et métriques probabilistes communes."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from types import MappingProxyType
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.ml_models import BaselinePrediction as BaselinePredictionRow
from metiquo.db.ml_models import BaselineRun as BaselineRunRow
from metiquo.db.ml_models import RatingArtifact as RatingArtifactRow
from metiquo.db.ml_models import TrainingDatasetExample
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime
from metiquo.models.datasets import GAME_WINNER_MARKET
from metiquo.models.validation import (
    FoldProbabilities,
    OutOfFoldPredictions,
    WalkForwardExample,
    WalkForwardPlan,
    collect_oof_predictions,
)

COMPETITION_PRIOR = "competition_prior"
RECENT_FORM = "recent_form"
RATING = "rating"
OOF_VALIDATION = "oof_validation"
COMPETITION_PRIOR_VERSION = "competition-prior-v1"
RECENT_FORM_VERSION = "recent-form-naive-v1"
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_METRIC_QUANTUM = Decimal("0.000001")
_PROBABILITY_QUANTUM = Decimal("0.00000001")
_LOG_EPSILON = Decimal("0.000000000001")


@dataclass(frozen=True, slots=True)
class CompetitionPriorParameters:
    """Lissage bêta déterministe des fréquences de victoire train-only."""

    alpha: Decimal = Decimal("0.5")
    beta: Decimal = Decimal("0.5")
    version: str = COMPETITION_PRIOR_VERSION

    def __post_init__(self) -> None:
        if (
            not self.alpha.is_finite()
            or not self.beta.is_finite()
            or self.alpha <= 0
            or self.beta <= 0
        ):
            raise ValueError("les paramètres du prior doivent être finis et positifs")
        if not self.version.strip():
            raise ValueError("la version du prior est requise")

    def document(self) -> dict[str, object]:
        return {"alpha": str(self.alpha), "beta": str(self.beta)}


@dataclass(frozen=True, slots=True)
class RecentFormParameters:
    """Champs explicites de la baseline naïve de forme récente."""

    team_a_field: str = "form.team_a.ewm_win_rate"
    team_b_field: str = "form.team_b.ewm_win_rate"
    version: str = RECENT_FORM_VERSION

    def __post_init__(self) -> None:
        if not self.team_a_field.strip() or not self.team_b_field.strip():
            raise ValueError("les champs de forme récente sont requis")
        if not self.version.strip():
            raise ValueError("la version de forme récente est requise")

    def document(self) -> dict[str, object]:
        return {
            "combination": "mean(team_a, 1-team_b)",
            "missing_value_fallback": COMPETITION_PRIOR,
            "team_a_field": self.team_a_field,
            "team_b_field": self.team_b_field,
        }


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower_bound: Decimal
    upper_bound: Decimal
    count: int
    mean_probability: Decimal
    observed_frequency: Decimal
    absolute_gap: Decimal

    def document(self) -> dict[str, object]:
        return {
            "absolute_gap": str(self.absolute_gap),
            "count": self.count,
            "lower_bound": str(self.lower_bound),
            "mean_probability": str(self.mean_probability),
            "observed_frequency": str(self.observed_frequency),
            "upper_bound": str(self.upper_bound),
        }


@dataclass(frozen=True, slots=True)
class BinaryMetricReport:
    sample_count: int
    log_loss: Decimal
    brier_score: Decimal
    calibration_ece: Decimal
    calibration_bins: tuple[ReliabilityBin, ...]
    bin_count: int

    def document(self) -> dict[str, object]:
        return {
            "brier_score": str(self.brier_score),
            "calibration": {
                "bin_count": self.bin_count,
                "ece": str(self.calibration_ece),
                "reliability": [item.document() for item in self.calibration_bins],
            },
            "log_loss": str(self.log_loss),
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True, slots=True)
class BaselinePrediction:
    example_id: UUID
    fold_index: int
    cutoff_at: datetime
    label: bool
    probability: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff_at", normalize_utc_datetime(self.cutoff_at))
        if self.fold_index < 0:
            raise ValueError("l'index de fold doit être positif")
        if not self.probability.is_finite() or not 0 <= self.probability <= 1:
            raise ValueError("une probabilité doit être finie et comprise entre 0 et 1")
        object.__setattr__(self, "probability", _stored_probability(self.probability))

    def document(self) -> dict[str, object]:
        return {
            "cutoff_at": self.cutoff_at.isoformat(),
            "example_id": str(self.example_id),
            "fold_index": self.fold_index,
            "label": self.label,
            "probability": str(_stored_probability(self.probability)),
        }


@dataclass(frozen=True, slots=True)
class BaselineRun:
    run_id: UUID
    dataset_id: UUID
    artifact_id: UUID | None
    market: str
    baseline_name: str
    baseline_version: str
    evaluation_split: str
    walk_forward_fingerprint: str
    parameters: Mapping[str, object]
    metrics: BinaryMetricReport
    predictions_fingerprint: str
    run_fingerprint: str
    code_commit: str
    created_at: datetime
    predictions: tuple[BaselinePrediction, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", normalize_utc_datetime(self.created_at))


@dataclass(frozen=True, slots=True)
class BaselineComparison:
    dataset_id: UUID
    evaluation_split: str
    walk_forward_fingerprint: str
    sample_count: int
    runs: tuple[BaselineRun, ...]


class BaselineEvaluator:
    """Évaluer les baselines sur les validations futures de chaque fold uniquement."""

    def __init__(
        self,
        *,
        code_commit: str,
        prior: CompetitionPriorParameters | None = None,
        recent_form: RecentFormParameters | None = None,
        calibration_bins: int = 10,
        clock: Clock | None = None,
    ) -> None:
        if _COMMIT.fullmatch(code_commit) is None:
            raise ValueError("code_commit doit être un hash git hexadécimal")
        if calibration_bins < 2:
            raise ValueError("au moins deux bins de calibration sont requis")
        self._code_commit = code_commit
        self._prior = prior or CompetitionPriorParameters()
        self._recent_form = recent_form or RecentFormParameters()
        self._calibration_bins = calibration_bins
        self._clock = clock or SystemClock()

    def evaluate(self, plan: WalkForwardPlan, *, dataset_id: UUID) -> tuple[BaselineRun, ...]:
        """Produire deux runs ayant exactement le même périmètre OOF."""

        prior_folds: list[FoldProbabilities] = []
        form_folds: list[FoldProbabilities] = []
        for fold in plan.folds:
            prior = _fit_competition_prior(fold.train, self._prior)
            prior_folds.append(
                FoldProbabilities(
                    fold_index=fold.fold_index,
                    probabilities=MappingProxyType(
                        {
                            item.example_id: prior.probability(item.competition_id)
                            for item in fold.validation
                        }
                    ),
                )
            )
            form_folds.append(
                FoldProbabilities(
                    fold_index=fold.fold_index,
                    probabilities=MappingProxyType(
                        {
                            item.example_id: _recent_form_probability(
                                item,
                                parameters=self._recent_form,
                                fallback=prior.probability(item.competition_id),
                            )
                            for item in fold.validation
                        }
                    ),
                )
            )
        created_at = self._clock.now().value
        runs = (
            self._run(
                dataset_id=dataset_id,
                plan=plan,
                name=COMPETITION_PRIOR,
                version=self._prior.version,
                parameters=self._prior.document(),
                oof=collect_oof_predictions(plan, prior_folds),
                created_at=created_at,
            ),
            self._run(
                dataset_id=dataset_id,
                plan=plan,
                name=RECENT_FORM,
                version=self._recent_form.version,
                parameters=self._recent_form.document(),
                oof=collect_oof_predictions(plan, form_folds),
                created_at=created_at,
            ),
        )
        assert_baseline_runs_comparable(runs)
        return runs

    def _run(
        self,
        *,
        dataset_id: UUID,
        plan: WalkForwardPlan,
        name: str,
        version: str,
        parameters: Mapping[str, object],
        oof: OutOfFoldPredictions,
        created_at: datetime,
    ) -> BaselineRun:
        return build_baseline_run(
            dataset_id=dataset_id,
            artifact_id=None,
            plan=plan,
            baseline_name=name,
            baseline_version=version,
            parameters=parameters,
            oof=oof,
            code_commit=self._code_commit,
            calibration_bins=self._calibration_bins,
            created_at=created_at,
        )


def build_baseline_run(
    *,
    dataset_id: UUID,
    artifact_id: UUID | None,
    plan: WalkForwardPlan,
    baseline_name: str,
    baseline_version: str,
    parameters: Mapping[str, object],
    oof: OutOfFoldPredictions,
    code_commit: str,
    calibration_bins: int,
    created_at: datetime,
) -> BaselineRun:
    """Construire une publication comparable depuis des prédictions OOF exactes."""

    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit doit être un hash git hexadécimal")
    predictions = tuple(
        BaselinePrediction(
            example_id=item.example_id,
            fold_index=item.fold_index,
            cutoff_at=item.cutoff_at,
            label=item.label,
            probability=item.probability,
        )
        for item in oof.predictions
    )
    final_ids = set(oof.final_test_ids)
    if final_ids & {item.example_id for item in predictions}:
        raise ValueError("le test final doit rester absent des runs de baseline")
    metrics = evaluate_binary_probabilities(predictions, bin_count=calibration_bins)
    predictions_fingerprint = _content_hash([item.document() for item in predictions])
    run_fingerprint = _content_hash(
        _run_document(
            dataset_id=dataset_id,
            artifact_id=artifact_id,
            market=GAME_WINNER_MARKET,
            baseline_name=baseline_name,
            baseline_version=baseline_version,
            evaluation_split=OOF_VALIDATION,
            walk_forward_fingerprint=plan.fingerprint,
            parameters=parameters,
            metrics=metrics,
            predictions_fingerprint=predictions_fingerprint,
            code_commit=code_commit,
        )
    )
    return BaselineRun(
        run_id=uuid5(NAMESPACE_URL, f"metiquo:baseline-run:{run_fingerprint}"),
        dataset_id=dataset_id,
        artifact_id=artifact_id,
        market=GAME_WINNER_MARKET,
        baseline_name=baseline_name,
        baseline_version=baseline_version,
        evaluation_split=OOF_VALIDATION,
        walk_forward_fingerprint=plan.fingerprint,
        parameters=MappingProxyType(dict(parameters)),
        metrics=metrics,
        predictions_fingerprint=predictions_fingerprint,
        run_fingerprint=run_fingerprint,
        code_commit=code_commit,
        created_at=created_at,
        predictions=predictions,
    )


class BaselineRunRepository:
    """Enregistrer et relire des évaluations publiées append-only."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def record(self, run: BaselineRun) -> BaselineRun:
        _validate_run(run)
        runs = cast(Table, BaselineRunRow.__table__)
        predictions = cast(Table, BaselinePredictionRow.__table__)
        artifacts = cast(Table, RatingArtifactRow.__table__)
        dataset_examples = cast(Table, TrainingDatasetExample.__table__)
        with self._engine.begin() as connection:
            allowed_ids = set(
                connection.execute(
                    select(dataset_examples.c.event_id).where(
                        dataset_examples.c.dataset_id == run.dataset_id
                    )
                ).scalars()
            )
            predicted_ids = {item.example_id for item in run.predictions}
            if not predicted_ids <= allowed_ids:
                raise ValueError("un run ne peut référencer que les exemples de son dataset")
            if run.artifact_id is not None:
                artifact = (
                    connection.execute(
                        select(
                            artifacts.c.dataset_id,
                            artifacts.c.walk_forward_fingerprint,
                            artifacts.c.artifact_fingerprint,
                        ).where(artifacts.c.id == run.artifact_id)
                    )
                    .mappings()
                    .one_or_none()
                )
                if artifact is None:
                    raise ValueError("l'artefact du run rating est introuvable")
                if (
                    artifact["dataset_id"] != run.dataset_id
                    or artifact["walk_forward_fingerprint"] != run.walk_forward_fingerprint
                    or artifact["artifact_fingerprint"]
                    != run.parameters.get("artifact_fingerprint")
                ):
                    raise ValueError(
                        "l'artefact rating ne correspond pas au dataset et au split du run"
                    )
            inserted = connection.execute(
                insert(runs)
                .values(
                    id=run.run_id,
                    dataset_id=run.dataset_id,
                    artifact_id=run.artifact_id,
                    market=run.market,
                    baseline_name=run.baseline_name,
                    baseline_version=run.baseline_version,
                    evaluation_split=run.evaluation_split,
                    walk_forward_fingerprint=run.walk_forward_fingerprint,
                    parameters=dict(run.parameters),
                    metrics=run.metrics.document(),
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
                            "cutoff_at": item.cutoff_at,
                            "example_id": item.example_id,
                            "fold_index": item.fold_index,
                            "label": item.label,
                            "position": position,
                            "probability": _stored_probability(item.probability),
                            "run_id": run.run_id,
                        }
                        for position, item in enumerate(run.predictions)
                    ],
                )
        stored = self.get_by_fingerprint(run.run_fingerprint)
        if stored is None:
            raise RuntimeError("le run de baseline n'a pas été enregistré")
        return stored

    def get(self, run_id: UUID) -> BaselineRun | None:
        runs = cast(Table, BaselineRunRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one_or_none()
            )
        return self._stored(row) if row is not None else None

    def get_by_fingerprint(self, fingerprint: str) -> BaselineRun | None:
        runs = cast(Table, BaselineRunRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(runs).where(runs.c.run_fingerprint == fingerprint))
                .mappings()
                .one_or_none()
            )
        return self._stored(row) if row is not None else None

    def _stored(self, row: RowMapping) -> BaselineRun:
        predictions = cast(Table, BaselinePredictionRow.__table__)
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(predictions)
                    .where(predictions.c.run_id == row["id"])
                    .order_by(predictions.c.position)
                )
                .mappings()
                .all()
            )
        return BaselineRun(
            run_id=cast(UUID, row["id"]),
            dataset_id=cast(UUID, row["dataset_id"]),
            artifact_id=cast(UUID | None, row["artifact_id"]),
            market=cast(str, row["market"]),
            baseline_name=cast(str, row["baseline_name"]),
            baseline_version=cast(str, row["baseline_version"]),
            evaluation_split=cast(str, row["evaluation_split"]),
            walk_forward_fingerprint=cast(str, row["walk_forward_fingerprint"]),
            parameters=MappingProxyType(dict(cast(Mapping[str, object], row["parameters"]))),
            metrics=binary_metric_report_from_document(cast(Mapping[str, object], row["metrics"])),
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
                for item in rows
            ),
        )


def evaluate_binary_probabilities(
    predictions: Sequence[BaselinePrediction],
    *,
    bin_count: int = 10,
) -> BinaryMetricReport:
    """Calculer log loss, Brier et reliability/ECE pour des probabilités binaires."""

    if not predictions:
        raise ValueError("au moins une prédiction est requise")
    if bin_count < 2:
        raise ValueError("au moins deux bins de calibration sont requis")
    ids = tuple(item.example_id for item in predictions)
    if len(ids) != len(set(ids)):
        raise ValueError("les prédictions doivent avoir des identifiants uniques")
    count = Decimal(len(predictions))
    log_loss = Decimal()
    brier = Decimal()
    buckets: defaultdict[int, list[BaselinePrediction]] = defaultdict(list)
    for item in predictions:
        clipped = min(max(item.probability, _LOG_EPSILON), Decimal(1) - _LOG_EPSILON)
        log_loss -= clipped.ln() if item.label else (Decimal(1) - clipped).ln()
        observed = Decimal(int(item.label))
        brier += (item.probability - observed) ** 2
        bucket = min(int(item.probability * bin_count), bin_count - 1)
        buckets[bucket].append(item)
    reliability: list[ReliabilityBin] = []
    ece = Decimal()
    for bucket, items in sorted(buckets.items()):
        item_count = Decimal(len(items))
        mean_probability = sum((item.probability for item in items), Decimal()) / item_count
        observed_frequency = (
            sum((Decimal(int(item.label)) for item in items), Decimal()) / item_count
        )
        gap = abs(mean_probability - observed_frequency)
        ece += gap * item_count / count
        reliability.append(
            ReliabilityBin(
                lower_bound=_metric(Decimal(bucket) / Decimal(bin_count)),
                upper_bound=_metric(Decimal(bucket + 1) / Decimal(bin_count)),
                count=len(items),
                mean_probability=_metric(mean_probability),
                observed_frequency=_metric(observed_frequency),
                absolute_gap=_metric(gap),
            )
        )
    return BinaryMetricReport(
        sample_count=len(predictions),
        log_loss=_metric(log_loss / count),
        brier_score=_metric(brier / count),
        calibration_ece=_metric(ece),
        calibration_bins=tuple(reliability),
        bin_count=bin_count,
    )


def assert_baseline_runs_comparable(runs: Sequence[BaselineRun]) -> BaselineComparison:
    """Refuser une comparaison sur des datasets, splits ou exemples différents."""

    if len(runs) < 2:
        raise ValueError("au moins deux runs sont requis pour une comparaison")
    first = runs[0]
    key = (first.dataset_id, first.evaluation_split, first.walk_forward_fingerprint)
    expected_examples = tuple(
        (item.example_id, item.fold_index, item.cutoff_at, item.label) for item in first.predictions
    )
    names: set[str] = set()
    for run in runs:
        if (run.dataset_id, run.evaluation_split, run.walk_forward_fingerprint) != key:
            raise ValueError("les runs ne partagent pas le même dataset et split walk-forward")
        observed_examples = tuple(
            (item.example_id, item.fold_index, item.cutoff_at, item.label)
            for item in run.predictions
        )
        if observed_examples != expected_examples:
            raise ValueError("les runs ne couvrent pas exactement les mêmes exemples OOF")
        if run.baseline_name in names:
            raise ValueError("une baseline ne peut apparaître deux fois dans une comparaison")
        names.add(run.baseline_name)
    return BaselineComparison(
        dataset_id=first.dataset_id,
        evaluation_split=first.evaluation_split,
        walk_forward_fingerprint=first.walk_forward_fingerprint,
        sample_count=len(expected_examples),
        runs=tuple(runs),
    )


@dataclass(frozen=True, slots=True)
class _CompetitionPrior:
    global_probability: Decimal
    competitions: Mapping[UUID, Decimal]

    def probability(self, competition_id: UUID | None) -> Decimal:
        if competition_id is None:
            return self.global_probability
        return self.competitions.get(competition_id, self.global_probability)


def _fit_competition_prior(
    examples: Sequence[WalkForwardExample],
    parameters: CompetitionPriorParameters,
) -> _CompetitionPrior:
    if not examples:
        raise ValueError("le prior exige un train non vide")
    global_probability = _smoothed_probability(examples, parameters)
    grouped: defaultdict[UUID, list[WalkForwardExample]] = defaultdict(list)
    for item in examples:
        if item.competition_id is not None:
            grouped[item.competition_id].append(item)
    return _CompetitionPrior(
        global_probability=global_probability,
        competitions=MappingProxyType(
            {
                competition_id: _smoothed_probability(values, parameters)
                for competition_id, values in sorted(grouped.items(), key=lambda item: str(item[0]))
            }
        ),
    )


def _smoothed_probability(
    examples: Sequence[WalkForwardExample],
    parameters: CompetitionPriorParameters,
) -> Decimal:
    wins = sum((Decimal(int(item.label)) for item in examples), Decimal())
    return (wins + parameters.alpha) / (Decimal(len(examples)) + parameters.alpha + parameters.beta)


def _recent_form_probability(
    example: WalkForwardExample,
    *,
    parameters: RecentFormParameters,
    fallback: Decimal,
) -> Decimal:
    components: list[Decimal] = []
    team_a = _optional_probability(example.feature_values.get(parameters.team_a_field))
    team_b = _optional_probability(example.feature_values.get(parameters.team_b_field))
    if team_a is not None:
        components.append(team_a)
    if team_b is not None:
        components.append(Decimal(1) - team_b)
    if not components:
        return fallback
    return sum(components, Decimal()) / Decimal(len(components))


def _optional_probability(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        probability = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not probability.is_finite() or not 0 <= probability <= 1:
        return None
    return probability


def _validate_run(run: BaselineRun) -> None:
    if run.market != GAME_WINNER_MARKET:
        raise ValueError("seul le marché game_winner est pris en charge")
    if run.baseline_name not in {COMPETITION_PRIOR, RATING, RECENT_FORM}:
        raise ValueError("baseline inconnue")
    if (run.baseline_name == RATING) != (run.artifact_id is not None):
        raise ValueError("seule la baseline rating exige un artefact lié")
    if run.evaluation_split != OOF_VALIDATION:
        raise ValueError("seules les validations OOF peuvent être publiées")
    if not _FINGERPRINT.fullmatch(run.walk_forward_fingerprint):
        raise ValueError("fingerprint walk-forward invalide")
    if not _FINGERPRINT.fullmatch(run.predictions_fingerprint):
        raise ValueError("fingerprint des prédictions invalide")
    if not _FINGERPRINT.fullmatch(run.run_fingerprint):
        raise ValueError("fingerprint du run invalide")
    if _COMMIT.fullmatch(run.code_commit) is None:
        raise ValueError("code_commit invalide")
    if len(run.predictions) != run.metrics.sample_count:
        raise ValueError("le nombre de prédictions doit correspondre aux métriques")
    if _content_hash([item.document() for item in run.predictions]) != run.predictions_fingerprint:
        raise ValueError("le fingerprint des prédictions ne correspond pas au contenu")
    recomputed_metrics = evaluate_binary_probabilities(
        run.predictions,
        bin_count=run.metrics.bin_count,
    )
    if recomputed_metrics != run.metrics:
        raise ValueError("les métriques publiées ne correspondent pas aux prédictions")
    expected_fingerprint = _content_hash(
        _run_document(
            dataset_id=run.dataset_id,
            artifact_id=run.artifact_id,
            market=run.market,
            baseline_name=run.baseline_name,
            baseline_version=run.baseline_version,
            evaluation_split=run.evaluation_split,
            walk_forward_fingerprint=run.walk_forward_fingerprint,
            parameters=run.parameters,
            metrics=run.metrics,
            predictions_fingerprint=run.predictions_fingerprint,
            code_commit=run.code_commit,
        )
    )
    if run.run_fingerprint != expected_fingerprint:
        raise ValueError("le fingerprint du run ne correspond pas à son contenu")
    expected_id = uuid5(NAMESPACE_URL, f"metiquo:baseline-run:{expected_fingerprint}")
    if run.run_id != expected_id:
        raise ValueError("l'identifiant du run ne correspond pas à son fingerprint")


def _run_document(
    *,
    dataset_id: UUID,
    artifact_id: UUID | None,
    market: str,
    baseline_name: str,
    baseline_version: str,
    evaluation_split: str,
    walk_forward_fingerprint: str,
    parameters: Mapping[str, object],
    metrics: BinaryMetricReport,
    predictions_fingerprint: str,
    code_commit: str,
) -> dict[str, object]:
    document: dict[str, object] = {
        "baseline_name": baseline_name,
        "baseline_version": baseline_version,
        "code_commit": code_commit,
        "dataset_id": str(dataset_id),
        "evaluation_split": evaluation_split,
        "market": market,
        "metrics": metrics.document(),
        "parameters": dict(parameters),
        "predictions_fingerprint": predictions_fingerprint,
        "walk_forward_fingerprint": walk_forward_fingerprint,
    }
    if artifact_id is not None:
        document["artifact_id"] = str(artifact_id)
    return document


def binary_metric_report_from_document(
    document: Mapping[str, object],
) -> BinaryMetricReport:
    """Restaurer le rapport canonique persisté en JSON."""
    calibration = cast(Mapping[str, object], document["calibration"])
    reliability = cast(Sequence[Mapping[str, object]], calibration["reliability"])
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


def _stored_probability(value: Decimal) -> Decimal:
    return value.quantize(_PROBABILITY_QUANTUM, rounding=ROUND_HALF_EVEN)


def _metric(value: Decimal) -> Decimal:
    return value.quantize(_METRIC_QUANTUM, rounding=ROUND_HALF_EVEN)


def _content_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
