"""Explications de modèle exclusivement issues de templates structurés."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from metiquo.features import StoredFeatureSnapshot
from metiquo.models.benchmark import TabularFeatureSpec
from metiquo.models.predictions import StoredPrematchPrediction

_FEATURE_LABELS = MappingProxyType(
    {
        "rating.difference": "écart de force pré-match",
        "form.team_a.ewm_win_rate": "forme récente de l'équipe A",
        "form.team_b.ewm_win_rate": "forme récente de l'équipe B",
        "side.team_a.adjusted_differential": "force ajustée à la side de l'équipe A",
        "side.team_b.adjusted_differential": "force ajustée à la side de l'équipe B",
        "economy.team_a.kills_per_minute": "rythme historique de l'équipe A",
        "economy.team_b.kills_per_minute": "rythme historique de l'équipe B",
        "roster.team_a.confidence": "continuité du roster de l'équipe A",
        "roster.team_b.confidence": "continuité du roster de l'équipe B",
        "context.best_of": "format de la série",
        "context.patch": "patch de la game",
        "context.phase": "phase de compétition",
        "context.region": "région de compétition",
        "side.target.team_a": "side prévue de l'équipe A",
    }
)


class ContributionMethod(StrEnum):
    SHAP = "shap"
    NATIVE = "native"
    COEFFICIENT = "coefficient"


class ExplanationKind(StrEnum):
    POSITIVE_FACTOR = "positive_factor"
    NEGATIVE_FACTOR = "negative_factor"
    UNCERTAINTY = "uncertainty"
    MISSING_DATA = "missing_data"
    DATA_AGE = "data_age"


@dataclass(frozen=True, slots=True)
class FeatureContribution:
    feature: str
    contribution: Decimal

    def __post_init__(self) -> None:
        if self.feature not in _FEATURE_LABELS:
            raise ValueError(f"feature explicative non autorisée: {self.feature}")
        if not self.contribution.is_finite():
            raise ValueError("une contribution doit être finie")


@dataclass(frozen=True, slots=True)
class ContributionEvidence:
    method: ContributionMethod
    baseline_output: Decimal
    model_output: Decimal
    contributions: tuple[FeatureContribution, ...]
    additive_tolerance: Decimal = Decimal("0.000001")

    def __post_init__(self) -> None:
        values = (self.baseline_output, self.model_output, self.additive_tolerance)
        if any(not value.is_finite() for value in values) or self.additive_tolerance < 0:
            raise ValueError("preuve de contribution numérique invalide")
        names = [item.feature for item in self.contributions]
        if len(names) != len(set(names)):
            raise ValueError("une feature ne peut apparaître qu'une fois")
        reconstructed = self.baseline_output + sum(
            (item.contribution for item in self.contributions), Decimal()
        )
        if abs(reconstructed - self.model_output) > self.additive_tolerance:
            raise ValueError("les contributions ne reconstruisent pas la sortie du modèle")


@dataclass(frozen=True, slots=True)
class StructuredField:
    name: str
    value: object
    missing: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("une référence de champ doit être nommée")
        if self.missing != (self.value is None):
            raise ValueError("le marqueur missing doit correspondre à la valeur")


@dataclass(frozen=True, slots=True)
class ExplanationItem:
    kind: ExplanationKind
    template_id: str
    text: str
    fields: tuple[StructuredField, ...]
    parameters: Mapping[str, str | bool]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        if not self.template_id.strip() or not self.text.strip() or not self.fields:
            raise ValueError("chaque phrase exige un template et des champs structurés")


@dataclass(frozen=True, slots=True)
class StructuredExplanation:
    reference: str
    prediction_id: UUID
    model_version_id: UUID
    feature_snapshot_id: UUID
    items: tuple[ExplanationItem, ...]
    contribution_method: ContributionMethod | None
    contribution_is_causal: bool

    def __post_init__(self) -> None:
        if not self.reference.startswith("model-explanation-v1:") or not self.items:
            raise ValueError("une explication versionnée non vide est requise")
        if self.contribution_is_causal:
            raise ValueError("une contribution modèle ne peut pas être étiquetée comme cause")
        if any(not item.fields for item in self.items):
            raise ValueError("toute phrase doit référencer au moins un champ")


class StructuredExplanationBuilder:
    """Rendre facteurs, incertitude et missingness sans texte libre."""

    def __init__(self, *, maximum_factors: int = 6) -> None:
        if maximum_factors < 1:
            raise ValueError("au moins un facteur explicatif est requis")
        self._maximum_factors = maximum_factors
        feature_spec = TabularFeatureSpec()
        self._model_features = (*feature_spec.numeric_fields, *feature_spec.categorical_fields)

    def build(
        self,
        prediction: StoredPrematchPrediction,
        snapshot: StoredFeatureSnapshot,
        *,
        contributions: ContributionEvidence | None = None,
    ) -> StructuredExplanation:
        if prediction.feature_snapshot_id != snapshot.snapshot_id:
            raise ValueError("la prédiction et l'explication doivent partager le snapshot")
        items: list[ExplanationItem] = []
        if contributions is not None:
            items.extend(self._contribution_items(contributions, snapshot))
        items.append(_uncertainty_item(prediction))
        items.extend(self._missing_items(snapshot))
        items.append(_data_age_item(prediction, snapshot))
        document = [_item_document(item) for item in items]
        fingerprint = _content_hash(
            {
                "contribution_method": contributions.method if contributions else None,
                "feature_snapshot_id": str(snapshot.snapshot_id),
                "items": document,
                "model_version_id": str(prediction.model_version_id),
                "prediction_id": str(prediction.prediction_id),
            }
        )
        return StructuredExplanation(
            reference=f"model-explanation-v1:{fingerprint}",
            prediction_id=prediction.prediction_id,
            model_version_id=prediction.model_version_id,
            feature_snapshot_id=snapshot.snapshot_id,
            items=tuple(items),
            contribution_method=contributions.method if contributions else None,
            contribution_is_causal=False,
        )

    def _contribution_items(
        self,
        evidence: ContributionEvidence,
        snapshot: StoredFeatureSnapshot,
    ) -> Sequence[ExplanationItem]:
        available: list[FeatureContribution] = []
        for contribution in evidence.contributions:
            if contribution.feature not in self._model_features:
                raise ValueError("la contribution ne fait pas partie du feature set du modèle")
            if snapshot.missingness.get(contribution.feature, True):
                raise ValueError("une feature manquante ne peut porter de contribution")
            if contribution.contribution != 0:
                available.append(contribution)
        selected = sorted(
            available,
            key=lambda item: (-abs(item.contribution), item.feature),
        )[: self._maximum_factors]
        return tuple(_contribution_item(item, evidence.method, snapshot) for item in selected)

    def _missing_items(self, snapshot: StoredFeatureSnapshot) -> Sequence[ExplanationItem]:
        return tuple(
            _missing_item(feature)
            for feature in self._model_features
            if snapshot.missingness.get(feature, True)
        )


def _contribution_item(
    contribution: FeatureContribution,
    method: ContributionMethod,
    snapshot: StoredFeatureSnapshot,
) -> ExplanationItem:
    positive = contribution.contribution > 0
    label = _FEATURE_LABELS[contribution.feature]
    direction = "à augmenter" if positive else "à diminuer"
    return ExplanationItem(
        kind=(ExplanationKind.POSITIVE_FACTOR if positive else ExplanationKind.NEGATIVE_FACTOR),
        template_id="model_contribution_v1",
        text=(
            f"« {label} » contribue {direction} la sortie du modèle ; "
            "cette contribution n'est pas une cause."
        ),
        fields=(
            StructuredField(
                name=contribution.feature,
                value=snapshot.values.get(contribution.feature),
                missing=False,
            ),
        ),
        parameters=MappingProxyType(
            {
                "causal": False,
                "contribution": str(contribution.contribution),
                "direction": "increase" if positive else "decrease",
                "feature_label": label,
                "method": method.value,
            }
        ),
    )


def _uncertainty_item(prediction: StoredPrematchPrediction) -> ExplanationItem:
    probability = _percent(prediction.team_a_probability)
    low = _percent(prediction.team_a_low)
    high = _percent(prediction.team_a_high)
    confidence = _percent(prediction.confidence)
    return ExplanationItem(
        kind=ExplanationKind.UNCERTAINTY,
        template_id="probability_interval_v1",
        text=(
            f"La probabilité équipe A est {probability}, dans une plage de {low} à {high}, "
            f"avec une confiance de {confidence}."
        ),
        fields=(
            StructuredField("prediction.team_a_probability", prediction.team_a_probability, False),
            StructuredField("prediction.team_a_low", prediction.team_a_low, False),
            StructuredField("prediction.team_a_high", prediction.team_a_high, False),
            StructuredField("prediction.confidence", prediction.confidence, False),
        ),
        parameters=MappingProxyType(
            {
                "confidence": confidence,
                "p50": probability,
                "p_high": high,
                "p_low": low,
            }
        ),
    )


def _missing_item(feature: str) -> ExplanationItem:
    label = _FEATURE_LABELS[feature]
    return ExplanationItem(
        kind=ExplanationKind.MISSING_DATA,
        template_id="missing_feature_v1",
        text=f"La donnée « {label} » est indisponible au cutoff.",
        fields=(StructuredField(feature, None, True),),
        parameters=MappingProxyType({"feature_label": label}),
    )


def _data_age_item(
    prediction: StoredPrematchPrediction,
    snapshot: StoredFeatureSnapshot,
) -> ExplanationItem:
    if snapshot.max_input_time is None:
        return ExplanationItem(
            kind=ExplanationKind.DATA_AGE,
            template_id="data_age_missing_v1",
            text="L'âge de la dernière donnée source est indisponible au cutoff.",
            fields=(StructuredField("snapshot.max_input_time", None, True),),
            parameters=MappingProxyType({"available": False}),
        )
    age_seconds = int((prediction.cutoff_at - snapshot.max_input_time).total_seconds())
    return ExplanationItem(
        kind=ExplanationKind.DATA_AGE,
        template_id="data_age_v1",
        text=f"La dernière donnée source précède le cutoff de {age_seconds} secondes.",
        fields=(
            StructuredField("snapshot.max_input_time", snapshot.max_input_time.isoformat(), False),
            StructuredField("prediction.cutoff_at", prediction.cutoff_at.isoformat(), False),
        ),
        parameters=MappingProxyType({"age_seconds": str(age_seconds), "available": True}),
    )


def _percent(value: Decimal) -> str:
    return f"{(value * Decimal(100)).quantize(Decimal('0.01'))}%"


def _item_document(item: ExplanationItem) -> dict[str, object]:
    return {
        "fields": [
            {"missing": field.missing, "name": field.name, "value": str(field.value)}
            for field in item.fields
        ],
        "kind": item.kind.value,
        "parameters": dict(item.parameters),
        "template_id": item.template_id,
        "text": item.text,
    }


def _content_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
