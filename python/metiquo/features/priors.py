"""Priors hiérarchiques, missingness et transformations fit train-only."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from uuid import UUID

from metiquo.features.registry import FeatureAvailability, FeatureDefinitionSpec, FeatureValue
from metiquo.features.temporal import AsOfInputAudit, CutoffViolationError, FeatureCutoff
from metiquo.foundation.time import normalize_utc_datetime

_QUANTUM = Decimal("0.000001")
_CODE_VERSION = "hierarchical-priors-v1"


@dataclass(frozen=True, slots=True)
class PriorParameters:
    recency_half_life_days: Decimal = Decimal("90")
    league_prior_strength: Decimal = Decimal("20")
    patch_prior_strength: Decimal = Decimal("10")
    observation_prior_strength: Decimal = Decimal("5")
    ood_confidence_multiplier: Decimal = Decimal("0.5")
    version: str = "hierarchical-priors-v1"

    def __post_init__(self) -> None:
        for name, value in (
            ("recency_half_life_days", self.recency_half_life_days),
            ("league_prior_strength", self.league_prior_strength),
            ("patch_prior_strength", self.patch_prior_strength),
            ("observation_prior_strength", self.observation_prior_strength),
        ):
            if not value.is_finite() or value <= 0:
                raise ValueError(f"{name} doit être fini et positif")
        if (
            not self.ood_confidence_multiplier.is_finite()
            or not Decimal() <= self.ood_confidence_multiplier <= Decimal(1)
        ):
            raise ValueError("ood_confidence_multiplier doit être compris entre zéro et un")
        if not self.version.strip():
            raise ValueError("version de priors requise")

    def document(self) -> dict[str, object]:
        return {
            "league_prior_strength": str(self.league_prior_strength),
            "observation_prior_strength": str(self.observation_prior_strength),
            "ood_confidence_multiplier": str(self.ood_confidence_multiplier),
            "patch_prior_strength": str(self.patch_prior_strength),
            "recency_half_life_days": str(self.recency_half_life_days),
        }


@dataclass(frozen=True, slots=True)
class PriorObservation:
    observation_id: UUID
    event_time: datetime
    known_at: datetime
    league: str | None
    patch: str | None
    value: Decimal | None
    sample_size: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time", normalize_utc_datetime(self.event_time))
        object.__setattr__(self, "known_at", normalize_utc_datetime(self.known_at))
        if self.sample_size < 0:
            raise ValueError("sample_size ne peut pas être négatif")
        if self.value is not None and not self.value.is_finite():
            raise ValueError("la valeur observée doit être finie")


@dataclass(frozen=True, slots=True)
class HierarchicalPriorModel:
    parameters_version: str
    fitted_at_cutoff: datetime
    audit: AsOfInputAudit
    global_prior: Decimal | None
    league_priors: Mapping[str, Decimal]
    patch_priors: Mapping[tuple[str, str], Decimal]
    observation_ids: tuple[UUID, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ShrunkFeatureValue:
    raw_value: Decimal | None
    value: Decimal | None
    prior: Decimal | None
    prior_level: str
    raw_sample_size: int
    effective_sample_size: Decimal
    raw_available: bool
    cold_start: bool
    ood: bool
    confidence: Decimal


class HierarchicalPriorEstimator:
    """Fit strictement antérieur puis shrinkage patch → ligue → global."""

    def __init__(self, parameters: PriorParameters | None = None) -> None:
        self._parameters = parameters or PriorParameters()

    def fit(
        self,
        observations: Sequence[PriorObservation],
        *,
        cutoff: FeatureCutoff,
    ) -> HierarchicalPriorModel:
        if not isinstance(cutoff, FeatureCutoff):
            raise TypeError("un FeatureCutoff explicite est obligatoire")
        selected = tuple(
            sorted(
                (
                    observation
                    for observation in observations
                    if observation.event_time < cutoff.at and observation.known_at <= cutoff.at
                ),
                key=lambda item: (item.event_time, item.observation_id),
            )
        )
        audit = cutoff.audit(
            (item.event_time for item in selected),
            source_knowledge_times=(item.known_at for item in selected),
        )
        usable = tuple(item for item in selected if item.value is not None and item.sample_size > 0)
        weighted = tuple((item, self._weight(item, cutoff)) for item in usable)
        global_prior = _weighted_mean(weighted)
        league_priors: dict[str, Decimal] = {}
        if global_prior is not None:
            for league in sorted({item.league for item in usable if item.league is not None}):
                group = tuple(pair for pair in weighted if pair[0].league == league)
                league_priors[league] = _regularized_group(
                    group,
                    parent=global_prior,
                    strength=self._parameters.league_prior_strength,
                )
        patch_priors: dict[tuple[str, str], Decimal] = {}
        for key in sorted(
            {
                (item.league, item.patch)
                for item in usable
                if item.league is not None and item.patch is not None
            }
        ):
            league, patch = key
            parent = league_priors.get(league, global_prior)
            if parent is None:
                continue
            group = tuple(
                pair for pair in weighted if pair[0].league == league and pair[0].patch == patch
            )
            patch_priors[(league, patch)] = _regularized_group(
                group,
                parent=parent,
                strength=self._parameters.patch_prior_strength,
            )
        ids = tuple(item.observation_id for item in selected)
        fingerprint = _prior_fingerprint(
            parameters=self._parameters,
            cutoff=cutoff,
            observations=selected,
            global_prior=global_prior,
            league_priors=league_priors,
            patch_priors=patch_priors,
        )
        return HierarchicalPriorModel(
            parameters_version=self._parameters.version,
            fitted_at_cutoff=cutoff.at,
            audit=audit,
            global_prior=global_prior,
            league_priors=MappingProxyType(league_priors),
            patch_priors=MappingProxyType(patch_priors),
            observation_ids=ids,
            fingerprint=fingerprint,
        )

    def shrink(
        self,
        model: HierarchicalPriorModel,
        *,
        value: Decimal | None,
        sample_size: int,
        league: str | None,
        patch: str | None,
        last_observed_at: datetime | None,
        prediction_cutoff: FeatureCutoff,
    ) -> ShrunkFeatureValue:
        if model.parameters_version != self._parameters.version:
            raise ValueError("la version du modèle de prior ne correspond pas au calculateur")
        if model.fitted_at_cutoff > prediction_cutoff.at:
            raise CutoffViolationError("un prior ajusté après le cutoff de prédiction est interdit")
        if sample_size < 0:
            raise ValueError("sample_size ne peut pas être négatif")
        if value is not None and not value.is_finite():
            raise ValueError("la valeur brute doit être finie")
        if last_observed_at is not None:
            normalized = normalize_utc_datetime(last_observed_at)
            prediction_cutoff.audit([normalized])
        else:
            normalized = None
        prior, level, ood = _resolve_prior(model, league, patch)
        effective = (
            _quantize(
                Decimal(sample_size)
                * _recency_weight(
                    normalized,
                    prediction_cutoff.at,
                    self._parameters.recency_half_life_days,
                )
            )
            if normalized is not None and sample_size > 0
            else Decimal().quantize(_QUANTUM)
        )
        available = value is not None and sample_size > 0
        cold_start = not available
        adjusted: Decimal | None
        if value is not None and sample_size > 0 and prior is not None:
            adjusted = _quantize(
                (value * effective + prior * self._parameters.observation_prior_strength)
                / (effective + self._parameters.observation_prior_strength)
            )
        elif value is not None and sample_size > 0:
            adjusted = value
        else:
            adjusted = prior
        confidence: Decimal = (
            effective / (effective + self._parameters.observation_prior_strength)
            if available
            else Decimal()
        )
        if ood:
            confidence *= self._parameters.ood_confidence_multiplier
        return ShrunkFeatureValue(
            raw_value=value,
            value=_quantize(adjusted) if adjusted is not None else None,
            prior=prior,
            prior_level=level,
            raw_sample_size=sample_size,
            effective_sample_size=effective,
            raw_available=available,
            cold_start=cold_start,
            ood=ood,
            confidence=_quantize(confidence),
        )

    def _weight(self, observation: PriorObservation, cutoff: FeatureCutoff) -> Decimal:
        return _quantize(
            Decimal(observation.sample_size)
            * _recency_weight(
                observation.event_time,
                cutoff.at,
                self._parameters.recency_half_life_days,
            )
        )


def prior_feature_definitions(
    metric_names: Sequence[str],
    parameters: PriorParameters | None = None,
) -> tuple[FeatureDefinitionSpec, ...]:
    resolved = parameters or PriorParameters()
    definitions: list[FeatureDefinitionSpec] = []
    for metric in metric_names:
        names: tuple[tuple[str, FeatureAvailability], ...] = (
            (f"prior.{metric}.value", "optional"),
            (f"prior.{metric}.available", "required"),
            (f"prior.{metric}.effective_sample", "required"),
            (f"prior.{metric}.confidence", "required"),
            (f"prior.{metric}.cold_start", "required"),
            (f"prior.{metric}.ood", "required"),
            (f"prior.{metric}.level", "required"),
        )
        for name, availability in names:
            definitions.append(
                FeatureDefinitionSpec(
                    name=name,
                    domain="priors_missingness",
                    definition_version=resolved.version,
                    parameters=resolved.document(),
                    availability=availability,
                    code_version=_CODE_VERSION,
                )
            )
    return tuple(definitions)


@dataclass(frozen=True, slots=True)
class TrainingFeatureRow:
    row_id: UUID
    event_time: datetime
    numeric: Mapping[str, Decimal | None]
    categorical: Mapping[str, str | None]

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time", normalize_utc_datetime(self.event_time))
        if any(value is not None and not value.is_finite() for value in self.numeric.values()):
            raise ValueError("les valeurs numériques d'entraînement doivent être finies")


@dataclass(frozen=True, slots=True)
class NumericTransform:
    mean: Decimal | None
    standard_deviation: Decimal | None
    observed_rows: int


@dataclass(frozen=True, slots=True)
class TrainOnlyPreprocessorArtifact:
    version: str
    fitted_at_cutoff: datetime
    fitted_row_ids: tuple[UUID, ...]
    numeric: Mapping[str, NumericTransform]
    categorical: Mapping[str, Mapping[str, int]]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class TransformedFeatureRow:
    values: Mapping[str, FeatureValue]


@dataclass(frozen=True, slots=True)
class PreprocessorParameters:
    numeric_fields: tuple[str, ...]
    categorical_fields: tuple[str, ...]
    version: str = "train-only-preprocessor-v1"

    def __post_init__(self) -> None:
        if len(set(self.numeric_fields)) != len(self.numeric_fields):
            raise ValueError("champs numériques dupliqués")
        if len(set(self.categorical_fields)) != len(self.categorical_fields):
            raise ValueError("champs catégoriels dupliqués")
        if set(self.numeric_fields) & set(self.categorical_fields):
            raise ValueError("un champ ne peut pas être numérique et catégoriel")
        if not self.version.strip():
            raise ValueError("version préprocesseur requise")


class TrainOnlyPreprocessor:
    """Ajuster scaler et encodeur uniquement sur les lignes avant le cutoff train."""

    def __init__(self, parameters: PreprocessorParameters) -> None:
        self._parameters = parameters

    def fit(
        self,
        rows: Sequence[TrainingFeatureRow],
        *,
        cutoff: FeatureCutoff,
    ) -> TrainOnlyPreprocessorArtifact:
        selected = tuple(
            sorted(
                (row for row in rows if row.event_time < cutoff.at),
                key=lambda row: (row.event_time, row.row_id),
            )
        )
        cutoff.audit(row.event_time for row in selected)
        numeric = {
            field_name: _numeric_transform(tuple(row.numeric.get(field_name) for row in selected))
            for field_name in self._parameters.numeric_fields
        }
        categorical = {
            field_name: MappingProxyType(
                {
                    value: index
                    for index, value in enumerate(
                        _category_values(selected, field_name),
                        start=1,
                    )
                }
            )
            for field_name in self._parameters.categorical_fields
        }
        row_ids = tuple(row.row_id for row in selected)
        fingerprint = _preprocessor_fingerprint(
            self._parameters,
            cutoff,
            row_ids,
            numeric,
            categorical,
        )
        return TrainOnlyPreprocessorArtifact(
            version=self._parameters.version,
            fitted_at_cutoff=cutoff.at,
            fitted_row_ids=row_ids,
            numeric=MappingProxyType(numeric),
            categorical=MappingProxyType(categorical),
            fingerprint=fingerprint,
        )

    def transform(
        self,
        artifact: TrainOnlyPreprocessorArtifact,
        row: TrainingFeatureRow,
    ) -> TransformedFeatureRow:
        values: dict[str, FeatureValue] = {}
        for field_name in self._parameters.numeric_fields:
            raw = row.numeric.get(field_name)
            transform = artifact.numeric[field_name]
            available = raw is not None
            scaled = (
                _quantize((raw - transform.mean) / transform.standard_deviation)
                if raw is not None
                and transform.mean is not None
                and transform.standard_deviation is not None
                else None
            )
            values[f"numeric.{field_name}.scaled"] = scaled
            values[f"numeric.{field_name}.available"] = available
            values[f"numeric.{field_name}.transform_available"] = scaled is not None
        for field_name in self._parameters.categorical_fields:
            raw_category = row.categorical.get(field_name)
            code = artifact.categorical[field_name].get(raw_category) if raw_category else None
            values[f"categorical.{field_name}.code"] = code
            values[f"categorical.{field_name}.available"] = raw_category is not None
            values[f"categorical.{field_name}.ood"] = raw_category is not None and code is None
        return TransformedFeatureRow(MappingProxyType(values))


def _category_values(rows: Sequence[TrainingFeatureRow], field_name: str) -> tuple[str, ...]:
    values = {value for row in rows if (value := row.categorical.get(field_name)) is not None}
    return tuple(sorted(values))


def _weighted_mean(
    observations: Sequence[tuple[PriorObservation, Decimal]],
) -> Decimal | None:
    weight = sum((item[1] for item in observations), Decimal())
    if weight <= 0:
        return None
    numerator = sum(
        (item.value * item_weight for item, item_weight in observations if item.value is not None),
        Decimal(),
    )
    return _quantize(numerator / weight)


def _regularized_group(
    observations: Sequence[tuple[PriorObservation, Decimal]],
    *,
    parent: Decimal,
    strength: Decimal,
) -> Decimal:
    weight = sum((item[1] for item in observations), Decimal())
    numerator = sum(
        (item.value * item_weight for item, item_weight in observations if item.value is not None),
        parent * strength,
    )
    return _quantize(numerator / (weight + strength))


def _resolve_prior(
    model: HierarchicalPriorModel,
    league: str | None,
    patch: str | None,
) -> tuple[Decimal | None, str, bool]:
    if league is not None and patch is not None and (league, patch) in model.patch_priors:
        return model.patch_priors[(league, patch)], "patch", False
    if league is not None and league in model.league_priors:
        return model.league_priors[league], "league", patch is not None
    if model.global_prior is not None:
        return model.global_prior, "global", league is not None or patch is not None
    return None, "none", True


def _recency_weight(
    observed_at: datetime | None,
    cutoff_at: datetime,
    half_life_days: Decimal,
) -> Decimal:
    if observed_at is None:
        return Decimal()
    age_days = Decimal(str((cutoff_at - observed_at).total_seconds())) / Decimal(86400)
    return _quantize(Decimal(str(math.pow(0.5, float(age_days / half_life_days)))))


def _numeric_transform(values: Sequence[Decimal | None]) -> NumericTransform:
    observed = tuple(value for value in values if value is not None)
    if not observed:
        return NumericTransform(None, None, 0)
    mean = sum(observed, Decimal()) / Decimal(len(observed))
    variance = sum(((value - mean) ** 2 for value in observed), Decimal()) / Decimal(len(observed))
    standard_deviation = variance.sqrt() if variance > 0 else None
    return NumericTransform(
        mean=_quantize(mean),
        standard_deviation=(
            _quantize(standard_deviation) if standard_deviation is not None else None
        ),
        observed_rows=len(observed),
    )


def _prior_fingerprint(
    *,
    parameters: PriorParameters,
    cutoff: FeatureCutoff,
    observations: Sequence[PriorObservation],
    global_prior: Decimal | None,
    league_priors: Mapping[str, Decimal],
    patch_priors: Mapping[tuple[str, str], Decimal],
) -> str:
    document = {
        "cutoff": cutoff.at.isoformat(),
        "global": str(global_prior) if global_prior is not None else None,
        "league": {key: str(value) for key, value in sorted(league_priors.items())},
        "observations": [str(item.observation_id) for item in observations],
        "parameters": parameters.document(),
        "patch": {
            f"{league}:{patch}": str(value)
            for (league, patch), value in sorted(patch_priors.items())
        },
    }
    return _hash_document(document)


def _preprocessor_fingerprint(
    parameters: PreprocessorParameters,
    cutoff: FeatureCutoff,
    row_ids: tuple[UUID, ...],
    numeric: Mapping[str, NumericTransform],
    categorical: Mapping[str, Mapping[str, int]],
) -> str:
    document = {
        "categorical": {key: dict(value) for key, value in sorted(categorical.items())},
        "cutoff": cutoff.at.isoformat(),
        "numeric": {
            key: {
                "mean": str(value.mean) if value.mean is not None else None,
                "observed_rows": value.observed_rows,
                "standard_deviation": (
                    str(value.standard_deviation) if value.standard_deviation is not None else None
                ),
            }
            for key, value in sorted(numeric.items())
        },
        "row_ids": [str(row_id) for row_id in row_ids],
        "version": parameters.version,
    }
    return _hash_document(document)


def _hash_document(document: Mapping[str, object]) -> str:
    serialized = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
