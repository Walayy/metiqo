"""Intervalles probabilistes et confiance sensibles à la couverture et à l'OOD."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from uuid import NAMESPACE_URL, UUID, uuid5

from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime
from metiquo.models.baselines import BaselinePrediction
from metiquo.models.calibration import CalibratorArtifact

UNCERTAINTY_VERSION = "temporal-conformal-uncertainty-v1"
ABSOLUTE_CONFORMAL = "absolute_conformal"
TEMPORAL_FOLD_CONFORMAL = "temporal_fold_conformal"
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class UncertaintySearchParameters:
    target_coverage: Decimal = Decimal("0.900000")
    minimum_data_coverage: Decimal = Decimal("0.800000")
    ood_warning_distance: Decimal = Decimal("3.000000")
    abstention_distance: Decimal = Decimal("5.000000")
    high_width_threshold: Decimal = Decimal("0.600000")
    version: str = UNCERTAINTY_VERSION

    def __post_init__(self) -> None:
        probabilities = (self.target_coverage, self.minimum_data_coverage)
        if any(not value.is_finite() or not 0 < value <= 1 for value in probabilities):
            raise ValueError("les couvertures doivent être finies dans ]0,1]")
        if (
            not self.ood_warning_distance.is_finite()
            or not self.abstention_distance.is_finite()
            or not Decimal() < self.ood_warning_distance < self.abstention_distance
        ):
            raise ValueError("les seuils OOD doivent être positifs et ordonnés")
        if not self.high_width_threshold.is_finite() or not 0 < self.high_width_threshold <= 1:
            raise ValueError("le seuil de largeur doit être dans ]0,1]")
        if not self.version.strip():
            raise ValueError("la version d'incertitude est requise")

    def document(self) -> dict[str, object]:
        return {
            "abstention_distance": str(self.abstention_distance),
            "high_width_threshold": str(self.high_width_threshold),
            "minimum_data_coverage": str(self.minimum_data_coverage),
            "ood_warning_distance": str(self.ood_warning_distance),
            "target_coverage": str(self.target_coverage),
        }


@dataclass(frozen=True, slots=True)
class UncertaintyCandidateEvaluation:
    method: str
    radius: Decimal
    empirical_coverage: Decimal
    mean_width: Decimal
    sample_count: int

    def document(self) -> dict[str, object]:
        return {
            "empirical_coverage": str(self.empirical_coverage),
            "mean_width": str(self.mean_width),
            "method": self.method,
            "radius": str(self.radius),
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True, slots=True)
class UncertaintyArtifact:
    artifact_id: UUID
    calibrator_artifact_id: UUID
    method: str
    base_radius: Decimal
    candidates: Mapping[str, UncertaintyCandidateEvaluation]
    search: UncertaintySearchParameters
    benchmark_fingerprint: str
    artifact_fingerprint: str
    code_commit: str
    created_at: datetime
    calibrator: CalibratorArtifact

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", normalize_utc_datetime(self.created_at))

    def estimate(
        self,
        raw_probability: Decimal,
        *,
        data_coverage: Decimal,
        training_domain_distance: Decimal,
    ) -> UncertaintyEstimate:
        """Calibrer le centre puis appliquer une prudence monotone et explicable."""

        return self.estimate_calibrated(
            self.calibrator.calibrate(raw_probability),
            data_coverage=data_coverage,
            training_domain_distance=training_domain_distance,
        )

    def estimate_calibrated(
        self,
        probability: Decimal,
        *,
        data_coverage: Decimal,
        training_domain_distance: Decimal,
    ) -> UncertaintyEstimate:
        """Évaluer une preuve déjà calibrée sans appliquer le calibrateur deux fois."""

        if not data_coverage.is_finite() or not 0 <= data_coverage <= 1:
            raise ValueError("data_coverage doit être dans [0,1]")
        if not training_domain_distance.is_finite() or training_domain_distance < 0:
            raise ValueError("training_domain_distance doit être positif")
        p50 = _probability(probability)
        reasons: list[str] = []
        if data_coverage < self.search.minimum_data_coverage:
            reasons.append("LOW_DATA_COVERAGE")
        if training_domain_distance >= self.search.ood_warning_distance:
            reasons.append("OUT_OF_DISTRIBUTION")
        if training_domain_distance >= self.search.abstention_distance:
            reasons.append("ABSTENTION_REQUIRED")
            return UncertaintyEstimate(
                p50=p50,
                p_low=Decimal(),
                p_high=Decimal(1),
                confidence=Decimal(),
                reasons=tuple(reasons),
                data_coverage=data_coverage,
                training_domain_distance=training_domain_distance,
                artifact_id=self.artifact_id,
            )
        coverage_inflation = (Decimal(1) - data_coverage) * Decimal("0.25")
        distance_inflation = max(Decimal(), training_domain_distance - Decimal(1)) * Decimal("0.05")
        radius = min(Decimal(1), self.base_radius + coverage_inflation + distance_inflation)
        p_low = _probability(max(Decimal(), p50 - radius))
        p_high = _probability(min(Decimal(1), p50 + radius))
        width = p_high - p_low
        if width >= self.search.high_width_threshold:
            reasons.append("HIGH_PREDICTIVE_UNCERTAINTY")
        confidence = _probability(
            max(
                Decimal(),
                Decimal(1)
                - width
                - (Decimal(1) - data_coverage) * Decimal("0.25")
                - min(Decimal("0.50"), training_domain_distance * Decimal("0.10")),
            )
        )
        return UncertaintyEstimate(
            p50=p50,
            p_low=p_low,
            p_high=p_high,
            confidence=confidence,
            reasons=tuple(reasons),
            data_coverage=data_coverage,
            training_domain_distance=training_domain_distance,
            artifact_id=self.artifact_id,
        )


@dataclass(frozen=True, slots=True)
class UncertaintyEstimate:
    p50: Decimal
    p_low: Decimal
    p_high: Decimal
    confidence: Decimal
    reasons: tuple[str, ...]
    data_coverage: Decimal
    training_domain_distance: Decimal
    artifact_id: UUID

    def __post_init__(self) -> None:
        if not Decimal() <= self.p_low <= self.p50 <= self.p_high <= Decimal(1):
            raise ValueError("l'intervalle doit respecter p_low <= p50 <= p_high")
        if not Decimal() <= self.confidence <= Decimal(1):
            raise ValueError("la confiance doit être dans [0,1]")


class UncertaintyArtifactBuilder:
    """Choisir une méthode conforme par couverture empirique puis largeur."""

    def __init__(
        self,
        *,
        code_commit: str,
        search: UncertaintySearchParameters | None = None,
        clock: Clock | None = None,
    ) -> None:
        if _COMMIT.fullmatch(code_commit) is None:
            raise ValueError("code_commit doit être un hash git hexadécimal")
        self._code_commit = code_commit
        self._search = search or UncertaintySearchParameters()
        self._clock = clock or SystemClock()

    def build(self, calibrator: CalibratorArtifact) -> UncertaintyArtifact:
        predictions = calibrator.oos_predictions
        if not predictions:
            raise ValueError("la preuve calibrée doit contenir des prédictions OOS")
        global_radius = _conformal_radius(
            predictions,
            target_coverage=self._search.target_coverage,
        )
        grouped: defaultdict[int, list[BaselinePrediction]] = defaultdict(list)
        for item in predictions:
            grouped[item.fold_index].append(item)
        temporal_radius = max(
            _conformal_radius(values, target_coverage=self._search.target_coverage)
            for values in grouped.values()
        )
        radii = {
            ABSOLUTE_CONFORMAL: global_radius,
            TEMPORAL_FOLD_CONFORMAL: temporal_radius,
        }
        candidates = {
            method: _candidate(method, radius, predictions) for method, radius in radii.items()
        }
        eligible = {
            method: value
            for method, value in candidates.items()
            if value.empirical_coverage >= self._search.target_coverage
        }
        pool = eligible or candidates
        selected_method = min(
            pool,
            key=lambda method: (
                pool[method].mean_width,
                -pool[method].empirical_coverage,
                method,
            ),
        )
        content = {
            "base_radius": str(candidates[selected_method].radius),
            "calibrator_artifact_id": str(calibrator.artifact_id),
            "candidates": {key: value.document() for key, value in sorted(candidates.items())},
            "code_commit": self._code_commit,
            "method": selected_method,
            "search": self._search.document(),
        }
        benchmark_fingerprint = _content_hash(content)
        artifact_fingerprint = _content_hash(
            {**content, "benchmark_fingerprint": benchmark_fingerprint}
        )
        return UncertaintyArtifact(
            artifact_id=uuid5(NAMESPACE_URL, f"metiquo:uncertainty:{artifact_fingerprint}"),
            calibrator_artifact_id=calibrator.artifact_id,
            method=selected_method,
            base_radius=candidates[selected_method].radius,
            candidates=MappingProxyType(candidates),
            search=self._search,
            benchmark_fingerprint=benchmark_fingerprint,
            artifact_fingerprint=artifact_fingerprint,
            code_commit=self._code_commit,
            created_at=self._clock.now().value,
            calibrator=calibrator,
        )


def _conformal_radius(
    predictions: Sequence[BaselinePrediction],
    *,
    target_coverage: Decimal,
) -> Decimal:
    scores = sorted(abs(Decimal(int(item.label)) - item.probability) for item in predictions)
    rank = int(
        (Decimal(len(scores) + 1) * target_coverage).to_integral_value(rounding=ROUND_CEILING)
    )
    return _probability(scores[min(max(rank - 1, 0), len(scores) - 1)])


def _candidate(
    method: str,
    radius: Decimal,
    predictions: Sequence[BaselinePrediction],
) -> UncertaintyCandidateEvaluation:
    covered = 0
    widths = Decimal()
    for item in predictions:
        low = max(Decimal(), item.probability - radius)
        high = min(Decimal(1), item.probability + radius)
        label = Decimal(int(item.label))
        covered += int(low <= label <= high)
        widths += high - low
    count = Decimal(len(predictions))
    return UncertaintyCandidateEvaluation(
        method=method,
        radius=_probability(radius),
        empirical_coverage=_probability(Decimal(covered) / count),
        mean_width=_probability(widths / count),
        sample_count=len(predictions),
    )


def _probability(value: Decimal) -> Decimal:
    if not value.is_finite() or not 0 <= value <= 1:
        raise ValueError("une probabilité doit être finie dans [0,1]")
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def _content_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
