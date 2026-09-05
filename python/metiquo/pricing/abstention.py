"""Abstention métier structurée, distincte d'une erreur système."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from types import MappingProxyType

from metiquo.contracts.enums import AbstentionReason, order_abstention_reasons
from metiquo.pricing.admission import ValueAdmissionDecision
from metiquo.pricing.value import ValuePrice

_MODEL_REASON_MAP = MappingProxyType(
    {
        "ABSTENTION_REQUIRED": AbstentionReason.OUT_OF_DISTRIBUTION,
        "CALIBRATION_FAILED": AbstentionReason.CALIBRATION_FAILED,
        "INSUFFICIENT_HISTORY": AbstentionReason.INSUFFICIENT_HISTORY,
        "LOW_DATA_COVERAGE": AbstentionReason.INSUFFICIENT_HISTORY,
        "OUT_OF_DISTRIBUTION": AbstentionReason.OUT_OF_DISTRIBUTION,
        "PATCH_CONTEXT_UNKNOWN": AbstentionReason.PATCH_CONTEXT_UNKNOWN,
        "ROSTER_UNCERTAIN": AbstentionReason.ROSTER_UNCERTAIN,
    }
)


@dataclass(frozen=True, slots=True)
class AbstentionDecision:
    """Résultat bloqué explicite et sérialisable par ses valeurs primitives."""

    policy_version: str
    reasons: tuple[AbstentionReason, ...]

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("policy_version est requise")
        if not self.reasons:
            raise ValueError("une abstention exige au moins une raison")
        if self.reasons != order_abstention_reasons(self.reasons):
            raise ValueError("les raisons doivent être uniques et dans l'ordre public")

    @property
    def primary_reason(self) -> AbstentionReason:
        return self.reasons[0]


@dataclass(frozen=True, slots=True)
class ValueDecision:
    """Résultat du pricing : opportunité ou abstention, sans exception métier."""

    policy_version: str
    evaluated_value: ValuePrice | None
    abstention: AbstentionDecision | None

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("policy_version est requise")
        if self.abstention is not None and self.abstention.policy_version != self.policy_version:
            raise ValueError("la décision et l'abstention doivent partager la même politique")
        if self.abstention is None and self.evaluated_value is None:
            raise ValueError("une opportunité exige une value calculée")

    @property
    def is_opportunity(self) -> bool:
        return self.abstention is None

    @property
    def reasons(self) -> tuple[AbstentionReason, ...]:
        return () if self.abstention is None else self.abstention.reasons


class ValueDecisionEngine:
    """Réunir les preuves ML et les garde-fous dans un résultat fermé."""

    def from_admission(
        self,
        admission: ValueAdmissionDecision,
        evaluated_value: ValuePrice,
        *,
        upstream_reasons: Sequence[AbstentionReason] = (),
        model_reason_codes: Sequence[str] = (),
    ) -> ValueDecision:
        if not isinstance(admission, ValueAdmissionDecision):
            raise TypeError("admission doit être une ValueAdmissionDecision")
        if not isinstance(evaluated_value, ValuePrice):
            raise TypeError("evaluated_value doit être une ValuePrice")
        reasons = _merge_reasons(upstream_reasons, model_reason_codes, admission.reasons)
        return ValueDecision(
            policy_version=admission.policy_version,
            evaluated_value=evaluated_value,
            abstention=(AbstentionDecision(admission.policy_version, reasons) if reasons else None),
        )

    def abstain_without_value(
        self,
        policy_version: str,
        *,
        reasons: Sequence[AbstentionReason] = (),
        model_reason_codes: Sequence[str] = (),
    ) -> ValueDecision:
        """Retourner une abstention normale quand le pricing n'a pas pu commencer."""

        merged = _merge_reasons(reasons, model_reason_codes, ())
        return ValueDecision(
            policy_version=policy_version,
            evaluated_value=None,
            abstention=AbstentionDecision(policy_version, merged),
        )


def _merge_reasons(
    upstream_reasons: Sequence[AbstentionReason],
    model_reason_codes: Sequence[str],
    admission_reasons: Sequence[AbstentionReason],
) -> tuple[AbstentionReason, ...]:
    typed_upstream = tuple(upstream_reasons)
    typed_admission = tuple(admission_reasons)
    for reason in (*typed_upstream, *typed_admission):
        if not isinstance(reason, AbstentionReason):
            raise TypeError("chaque raison amont doit être une AbstentionReason")
    model_reasons: list[AbstentionReason] = []
    for code in model_reason_codes:
        mapped = _MODEL_REASON_MAP.get(code)
        if mapped is None:
            raise ValueError(f"raison modèle non structurée : {code}")
        model_reasons.append(mapped)
    return order_abstention_reasons((*typed_upstream, *model_reasons, *typed_admission))
