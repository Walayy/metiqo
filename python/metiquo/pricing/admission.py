"""Garde-fous ordonnés avant création d'une opportunité."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from metiquo.contracts.enums import (
    AbstentionReason,
    FreshnessStatus,
    MarketStatus,
    ModelStatus,
)
from metiquo.foundation.finance import Probability
from metiquo.foundation.time import normalize_utc_datetime
from metiquo.pricing.policy import ResolvedValuePolicy
from metiquo.pricing.value import ValuePrice


class AdmissionCheckCode(StrEnum):
    """Ordre public et stable des contrôles d'admission."""

    CAPABILITY_ENABLED = "CAPABILITY_ENABLED"
    SOURCE_QUALITY = "SOURCE_QUALITY"
    CHAMPION_MODEL = "CHAMPION_MODEL"
    EVENT_MAPPING = "EVENT_MAPPING"
    MARKET_RULES = "MARKET_RULES"
    MARKET_OPEN = "MARKET_OPEN"
    EVENT_NOT_STARTED = "EVENT_NOT_STARTED"
    PREDICTION_CUTOFF = "PREDICTION_CUTOFF"
    ODDS_AGE = "ODDS_AGE"
    MAPPING_CONFIDENCE = "MAPPING_CONFIDENCE"
    MIN_EDGE = "MIN_EDGE"
    MIN_EV = "MIN_EV"
    MIN_CONSERVATIVE_EV = "MIN_CONSERVATIVE_EV"


@dataclass(frozen=True, slots=True)
class ValueAdmissionInput:
    """Toutes les preuves déjà calculées, sans accès implicite à un repository."""

    value_price: ValuePrice
    policy: ResolvedValuePolicy
    mapping_confidence: Probability
    odds_age_seconds: int
    model_status: ModelStatus
    source_freshness: FreshnessStatus
    market_status: MarketStatus
    prediction_cutoff: datetime
    event_starts_at: datetime
    evaluated_at: datetime
    capability_enabled: bool
    event_mapping_resolved: bool
    market_rules_known: bool

    def __post_init__(self) -> None:
        if not isinstance(self.value_price, ValuePrice):
            raise TypeError("value_price doit être un ValuePrice")
        if not isinstance(self.policy, ResolvedValuePolicy):
            raise TypeError("policy doit être une ResolvedValuePolicy")
        if not isinstance(self.mapping_confidence, Probability):
            raise TypeError("mapping_confidence doit être une Probability")
        if self.odds_age_seconds < 0:
            raise ValueError("odds_age_seconds ne peut pas être négatif")
        if not isinstance(self.model_status, ModelStatus):
            raise TypeError("model_status doit être un ModelStatus")
        if not isinstance(self.source_freshness, FreshnessStatus):
            raise TypeError("source_freshness doit être un FreshnessStatus")
        if not isinstance(self.market_status, MarketStatus):
            raise TypeError("market_status doit être un MarketStatus")
        for label in (
            "capability_enabled",
            "event_mapping_resolved",
            "market_rules_known",
        ):
            if not isinstance(getattr(self, label), bool):
                raise TypeError(f"{label} doit être un booléen")
        prediction_cutoff = normalize_utc_datetime(self.prediction_cutoff)
        event_starts_at = normalize_utc_datetime(self.event_starts_at)
        evaluated_at = normalize_utc_datetime(self.evaluated_at)
        if evaluated_at < prediction_cutoff:
            raise ValueError("l'évaluation ne peut pas précéder le cutoff de prédiction")
        object.__setattr__(self, "prediction_cutoff", prediction_cutoff)
        object.__setattr__(self, "event_starts_at", event_starts_at)
        object.__setattr__(self, "evaluated_at", evaluated_at)


@dataclass(frozen=True, slots=True)
class AdmissionCheck:
    """Résultat d'un contrôle individuel dans la matrice ordonnée."""

    code: AdmissionCheckCode
    passed: bool
    failure_reason: AbstentionReason | None

    def __post_init__(self) -> None:
        if self.passed == (self.failure_reason is not None):
            raise ValueError("un contrôle réussi ne porte pas de raison d'échec")


@dataclass(frozen=True, slots=True)
class ValueAdmissionDecision:
    """Décision fermée ; une seule raison suffit à interdire l'opportunité."""

    admitted: bool
    policy_version: str
    checks: tuple[AdmissionCheck, ...]
    reasons: tuple[AbstentionReason, ...]

    def __post_init__(self) -> None:
        if self.admitted == bool(self.reasons):
            raise ValueError("une admission ne peut pas contenir de raison d'abstention")
        if tuple(check.code for check in self.checks) != tuple(AdmissionCheckCode):
            raise ValueError("les contrôles d'admission doivent respecter l'ordre normatif")


class ValueAdmissionGate:
    """Évaluer tous les garde-fous dans le même ordre à chaque appel."""

    def evaluate(self, request: ValueAdmissionInput) -> ValueAdmissionDecision:
        thresholds = request.policy.thresholds
        checks = (
            _check(
                AdmissionCheckCode.CAPABILITY_ENABLED,
                request.capability_enabled,
                AbstentionReason.CAPABILITY_DISABLED,
            ),
            _check(
                AdmissionCheckCode.SOURCE_QUALITY,
                request.source_freshness is FreshnessStatus.FRESH,
                AbstentionReason.SOURCE_STALE,
            ),
            _check(
                AdmissionCheckCode.CHAMPION_MODEL,
                request.model_status is ModelStatus.CHAMPION,
                AbstentionReason.MODEL_STALE,
            ),
            _check(
                AdmissionCheckCode.EVENT_MAPPING,
                request.event_mapping_resolved,
                AbstentionReason.EVENT_MAPPING_AMBIGUOUS,
            ),
            _check(
                AdmissionCheckCode.MARKET_RULES,
                request.market_rules_known,
                AbstentionReason.MARKET_RULES_UNKNOWN,
            ),
            _check(
                AdmissionCheckCode.MARKET_OPEN,
                request.market_status is MarketStatus.OPEN,
                AbstentionReason.MARKET_SUSPENDED,
            ),
            _check(
                AdmissionCheckCode.EVENT_NOT_STARTED,
                request.evaluated_at < request.event_starts_at,
                AbstentionReason.EVENT_ALREADY_STARTED,
            ),
            _check(
                AdmissionCheckCode.PREDICTION_CUTOFF,
                request.prediction_cutoff < request.event_starts_at,
                AbstentionReason.EVENT_ALREADY_STARTED,
            ),
            _check(
                AdmissionCheckCode.ODDS_AGE,
                request.odds_age_seconds <= thresholds.max_odds_age_seconds,
                AbstentionReason.ODDS_STALE,
            ),
            _check(
                AdmissionCheckCode.MAPPING_CONFIDENCE,
                request.mapping_confidence.value >= thresholds.min_mapping_confidence,
                AbstentionReason.EVENT_MAPPING_AMBIGUOUS,
            ),
            _check(
                AdmissionCheckCode.MIN_EDGE,
                request.value_price.edge >= thresholds.min_edge,
                AbstentionReason.EDGE_TOO_SMALL,
            ),
            _check(
                AdmissionCheckCode.MIN_EV,
                request.value_price.expected_value >= thresholds.min_ev,
                AbstentionReason.EXPECTED_VALUE_TOO_SMALL,
            ),
            _check(
                AdmissionCheckCode.MIN_CONSERVATIVE_EV,
                (request.value_price.conservative_expected_value >= thresholds.min_conservative_ev),
                (
                    AbstentionReason.CONSERVATIVE_EV_NEGATIVE
                    if request.value_price.conservative_expected_value < 0
                    else AbstentionReason.CONSERVATIVE_EV_TOO_SMALL
                ),
            ),
        )
        reasons = tuple(
            dict.fromkeys(
                check.failure_reason for check in checks if check.failure_reason is not None
            )
        )
        return ValueAdmissionDecision(
            admitted=not reasons,
            policy_version=request.policy.policy_version,
            checks=checks,
            reasons=reasons,
        )


def _check(
    code: AdmissionCheckCode,
    passed: bool,
    failure_reason: AbstentionReason,
) -> AdmissionCheck:
    return AdmissionCheck(code, passed, None if passed else failure_reason)
