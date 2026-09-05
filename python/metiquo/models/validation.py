"""Validation walk-forward stricte et préparation train-only."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from itertools import groupby
from types import MappingProxyType
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, Table, select

from metiquo.db.feature_models import FeatureSnapshot
from metiquo.features import (
    FeatureCutoff,
    TrainingFeatureRow,
    TrainOnlyPreprocessor,
    TrainOnlyPreprocessorArtifact,
    TransformedFeatureRow,
)
from metiquo.foundation.time import normalize_utc_datetime
from metiquo.models.datasets import StoredTrainingDataset


@dataclass(frozen=True, slots=True)
class WalkForwardExample:
    """Exemple ordonné avec les segments nécessaires au rapport temporel."""

    example_id: UUID
    feature_snapshot_id: UUID
    cutoff_at: datetime
    label: bool
    competition_id: UUID | None
    patch: str | None
    international: bool | None
    feature_values: Mapping[str, object]
    missingness: Mapping[str, bool]

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff_at", normalize_utc_datetime(self.cutoff_at))


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    """Découpe principale uniquement chronologique, par groupes de cutoff."""

    minimum_train_periods: int
    validation_periods: int
    final_test_periods: int
    primary_split: str = "walk_forward"
    threshold_tuning_scope: str = "oof_validation"
    version: str = "walk-forward-v1"

    def __post_init__(self) -> None:
        if self.primary_split != "walk_forward":
            raise ValueError("le split principal aléatoire est interdit")
        if self.threshold_tuning_scope != "oof_validation":
            raise ValueError("les seuils doivent être réglés sur la validation OOF")
        if not self.version.strip():
            raise ValueError("la version du protocole walk-forward est requise")
        if (
            min(
                self.minimum_train_periods,
                self.validation_periods,
                self.final_test_periods,
            )
            < 1
        ):
            raise ValueError("chaque fenêtre temporelle exige au moins une période")


@dataclass(frozen=True, slots=True)
class TemporalFold:
    fold_index: int
    train: tuple[WalkForwardExample, ...]
    validation: tuple[WalkForwardExample, ...]
    train_cutoff_max: datetime
    validation_cutoff_min: datetime
    validation_cutoff_max: datetime


@dataclass(frozen=True, slots=True)
class SegmentCounts:
    initial_train: int
    oof_validation: int
    final_test: int

    @property
    def total(self) -> int:
        return self.initial_train + self.oof_validation + self.final_test


@dataclass(frozen=True, slots=True)
class WalkForwardSegmentReport:
    patches: Mapping[str, SegmentCounts]
    international: Mapping[str, SegmentCounts]


@dataclass(frozen=True, slots=True)
class WalkForwardPlan:
    config: WalkForwardConfig
    folds: tuple[TemporalFold, ...]
    initial_train: tuple[WalkForwardExample, ...]
    oof_validation: tuple[WalkForwardExample, ...]
    final_test: tuple[WalkForwardExample, ...]
    segments: WalkForwardSegmentReport
    fingerprint: str

    def assert_tuning_scope(self, example_ids: Sequence[UUID]) -> None:
        requested = set(example_ids)
        allowed = {example.example_id for example in self.oof_validation}
        forbidden = requested - allowed
        if forbidden:
            raise ValueError(
                "le tuning est limité aux prédictions OOF de validation; "
                f"IDs interdits: {sorted(str(value) for value in forbidden)}"
            )


@dataclass(frozen=True, slots=True)
class PreparedFold:
    split: TemporalFold
    preprocessor: TrainOnlyPreprocessorArtifact
    transformed_train: tuple[TransformedFeatureRow, ...]
    transformed_validation: tuple[TransformedFeatureRow, ...]


@dataclass(frozen=True, slots=True)
class PreparedWalkForward:
    folds: tuple[PreparedFold, ...]
    untouched_final_test_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class FoldProbabilities:
    fold_index: int
    probabilities: Mapping[UUID, Decimal]


@dataclass(frozen=True, slots=True)
class OutOfFoldPrediction:
    example_id: UUID
    fold_index: int
    cutoff_at: datetime
    label: bool
    probability: Decimal


@dataclass(frozen=True, slots=True)
class OutOfFoldPredictions:
    predictions: tuple[OutOfFoldPrediction, ...]
    final_test_ids: tuple[UUID, ...]


class TrainingExampleRepository:
    """Relire les vecteurs exacts référencés par un dataset immuable."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def load(self, dataset: StoredTrainingDataset) -> tuple[WalkForwardExample, ...]:
        snapshots = cast(Table, FeatureSnapshot.__table__)
        ids = tuple(example.feature_snapshot_id for example in dataset.examples)
        with self._engine.connect() as connection:
            rows = (
                connection.execute(select(snapshots).where(snapshots.c.id.in_(ids)))
                .mappings()
                .all()
            )
        rows_by_id = {cast(UUID, row["id"]): row for row in rows}
        loaded: list[WalkForwardExample] = []
        for example in dataset.examples:
            row = rows_by_id.get(example.feature_snapshot_id)
            if row is None:
                raise ValueError("feature snapshot du dataset introuvable")
            if (
                row["event_id"] != example.event_id
                or row["cutoff_at"] != example.cutoff_at
                or row["feature_set_id"] != dataset.feature_set_id
            ):
                raise ValueError("le feature snapshot ne correspond plus au manifeste")
            values = dict(cast(Mapping[str, object], row["values"]))
            missingness = dict(cast(Mapping[str, bool], row["missingness"]))
            patch_value = values.get("context.patch")
            phase_value = values.get("context.phase")
            patch = patch_value if isinstance(patch_value, str) else None
            phase = phase_value if isinstance(phase_value, str) else None
            international = (
                True
                if phase == "international"
                else False
                if phase in {"regular", "playoffs"}
                else None
            )
            loaded.append(
                WalkForwardExample(
                    example_id=example.event_id,
                    feature_snapshot_id=example.feature_snapshot_id,
                    cutoff_at=example.cutoff_at,
                    label=example.label_team_a_win,
                    competition_id=example.competition_id,
                    patch=patch,
                    international=international,
                    feature_values=MappingProxyType(values),
                    missingness=MappingProxyType(missingness),
                )
            )
        return tuple(loaded)


class WalkForwardSplitter:
    """Construire des folds expansifs en réservant le test final intact."""

    def __init__(self, config: WalkForwardConfig) -> None:
        self._config = config

    def split(self, examples: Sequence[WalkForwardExample]) -> WalkForwardPlan:
        ordered = tuple(sorted(examples, key=lambda item: (item.cutoff_at, item.example_id)))
        ids = tuple(example.example_id for example in ordered)
        if len(ids) != len(set(ids)):
            raise ValueError("les identifiants d'exemples doivent être uniques")
        periods = tuple(
            tuple(group) for _cutoff, group in groupby(ordered, key=lambda item: item.cutoff_at)
        )
        required = self._config.minimum_train_periods + 1 + self._config.final_test_periods
        if len(periods) < required:
            raise ValueError(
                f"{required} périodes distinctes requises pour le walk-forward, "
                f"{len(periods)} reçues"
            )
        final_periods = periods[-self._config.final_test_periods :]
        development_periods = periods[: -self._config.final_test_periods]
        initial_periods = development_periods[: self._config.minimum_train_periods]
        folds: list[TemporalFold] = []
        cursor = self._config.minimum_train_periods
        while cursor < len(development_periods):
            validation_end = min(cursor + self._config.validation_periods, len(development_periods))
            train = _flatten(development_periods[:cursor])
            validation = _flatten(development_periods[cursor:validation_end])
            if max(item.cutoff_at for item in train) >= min(item.cutoff_at for item in validation):
                raise ValueError("chaque fold exige train strictement antérieur à validation")
            folds.append(
                TemporalFold(
                    fold_index=len(folds),
                    train=train,
                    validation=validation,
                    train_cutoff_max=max(item.cutoff_at for item in train),
                    validation_cutoff_min=min(item.cutoff_at for item in validation),
                    validation_cutoff_max=max(item.cutoff_at for item in validation),
                )
            )
            cursor = validation_end
        initial_train = _flatten(initial_periods)
        oof_validation = tuple(item for fold in folds for item in fold.validation)
        final_test = _flatten(final_periods)
        if set(item.example_id for item in final_test) & {
            item.example_id for fold in folds for item in (*fold.train, *fold.validation)
        }:
            raise ValueError("la période finale ne peut apparaître dans les folds")
        fold_tuple = tuple(folds)
        segments = _segment_report(initial_train, oof_validation, final_test)
        return WalkForwardPlan(
            config=self._config,
            folds=fold_tuple,
            initial_train=initial_train,
            oof_validation=oof_validation,
            final_test=final_test,
            segments=segments,
            fingerprint=_plan_fingerprint(
                self._config,
                fold_tuple,
                final_test,
            ),
        )


def prepare_walk_forward(
    plan: WalkForwardPlan,
    *,
    rows: Sequence[TrainingFeatureRow],
    preprocessor: TrainOnlyPreprocessor,
) -> PreparedWalkForward:
    """Ajuster chaque transformation sur le train du fold, jamais sur son futur."""

    rows_by_id = {row.row_id: row for row in rows}
    if len(rows_by_id) != len(rows):
        raise ValueError("les lignes de transformation doivent être uniques")
    required_ids = {
        example.example_id for fold in plan.folds for example in (*fold.train, *fold.validation)
    }
    missing = required_ids - rows_by_id.keys()
    if missing:
        raise ValueError(f"lignes de transformation absentes: {sorted(map(str, missing))}")
    prepared: list[PreparedFold] = []
    for fold in plan.folds:
        train_rows = tuple(rows_by_id[example.example_id] for example in fold.train)
        validation_rows = tuple(rows_by_id[example.example_id] for example in fold.validation)
        artifact = preprocessor.fit(
            train_rows,
            cutoff=FeatureCutoff(fold.validation_cutoff_min),
        )
        if set(artifact.fitted_row_ids) != {row.row_id for row in train_rows}:
            raise ValueError("le préprocesseur n'a pas été ajusté sur le train exact")
        prepared.append(
            PreparedFold(
                split=fold,
                preprocessor=artifact,
                transformed_train=tuple(
                    preprocessor.transform(artifact, row) for row in train_rows
                ),
                transformed_validation=tuple(
                    preprocessor.transform(artifact, row) for row in validation_rows
                ),
            )
        )
    return PreparedWalkForward(
        folds=tuple(prepared),
        untouched_final_test_ids=tuple(example.example_id for example in plan.final_test),
    )


def collect_oof_predictions(
    plan: WalkForwardPlan,
    folds: Sequence[FoldProbabilities],
) -> OutOfFoldPredictions:
    """Accepter uniquement une probabilité future pour chaque validation de fold."""

    supplied = {fold.fold_index: fold for fold in folds}
    expected_indexes = {fold.fold_index for fold in plan.folds}
    if set(supplied) != expected_indexes or len(supplied) != len(folds):
        raise ValueError("une prédiction est requise pour chaque fold exact")
    predictions: list[OutOfFoldPrediction] = []
    for split in plan.folds:
        values = supplied[split.fold_index].probabilities
        expected_ids = {example.example_id for example in split.validation}
        if set(values) != expected_ids:
            raise ValueError("les probabilités doivent couvrir exactement la validation du fold")
        for example in split.validation:
            probability = values[example.example_id]
            if not probability.is_finite() or probability < 0 or probability > 1:
                raise ValueError("une probabilité OOF doit être finie et comprise entre 0 et 1")
            predictions.append(
                OutOfFoldPrediction(
                    example_id=example.example_id,
                    fold_index=split.fold_index,
                    cutoff_at=example.cutoff_at,
                    label=example.label,
                    probability=probability,
                )
            )
    final_ids = tuple(example.example_id for example in plan.final_test)
    if set(final_ids) & {prediction.example_id for prediction in predictions}:
        raise ValueError("le test final ne peut pas apparaître dans les prédictions OOF")
    return OutOfFoldPredictions(tuple(predictions), final_ids)


def _flatten(periods: Sequence[Sequence[WalkForwardExample]]) -> tuple[WalkForwardExample, ...]:
    return tuple(example for period in periods for example in period)


def _segment_report(
    initial_train: Sequence[WalkForwardExample],
    oof_validation: Sequence[WalkForwardExample],
    final_test: Sequence[WalkForwardExample],
) -> WalkForwardSegmentReport:
    return WalkForwardSegmentReport(
        patches=_segment_counts(
            initial_train,
            oof_validation,
            final_test,
            key=lambda example: example.patch or "unknown",
        ),
        international=_segment_counts(
            initial_train,
            oof_validation,
            final_test,
            key=lambda example: (
                "international"
                if example.international is True
                else "domestic"
                if example.international is False
                else "unknown"
            ),
        ),
    )


def _segment_counts(
    initial_train: Sequence[WalkForwardExample],
    oof_validation: Sequence[WalkForwardExample],
    final_test: Sequence[WalkForwardExample],
    *,
    key: Callable[[WalkForwardExample], str],
) -> Mapping[str, SegmentCounts]:
    counts: defaultdict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for bucket, examples in enumerate((initial_train, oof_validation, final_test)):
        for example in examples:
            counts[key(example)][bucket] += 1
    return MappingProxyType(
        {
            label: SegmentCounts(values[0], values[1], values[2])
            for label, values in sorted(counts.items())
        }
    )


def _plan_fingerprint(
    config: WalkForwardConfig,
    folds: Sequence[TemporalFold],
    final_test: Sequence[WalkForwardExample],
) -> str:
    document = {
        "config": {
            "final_test_periods": config.final_test_periods,
            "minimum_train_periods": config.minimum_train_periods,
            "primary_split": config.primary_split,
            "threshold_tuning_scope": config.threshold_tuning_scope,
            "validation_periods": config.validation_periods,
            "version": config.version,
        },
        "final_test": [str(example.example_id) for example in final_test],
        "folds": [
            {
                "fold_index": fold.fold_index,
                "train": [str(example.example_id) for example in fold.train],
                "validation": [str(example.example_id) for example in fold.validation],
            }
            for fold in folds
        ],
    }
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
