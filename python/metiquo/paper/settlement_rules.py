"""Preuves et décisions communes aux moteurs de règlement paper."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from metiquo.contracts.enums import PaperBetStatus, SelectionType
from metiquo.foundation.time import normalize_utc_datetime
from metiquo.paper.creation import fingerprint


@dataclass(frozen=True, slots=True)
class ResultProvenance:
    snapshot_id: UUID | None
    status: str
    validated_at: datetime | None
    processed_at: datetime | None
    result_fingerprint: str

    def known_validated_at(self, now: datetime) -> bool:
        now = normalize_utc_datetime(now)
        return (
            self.snapshot_id is not None
            and self.status == "validated"
            and self.validated_at is not None
            and self.processed_at is not None
            and normalize_utc_datetime(self.validated_at)
            <= normalize_utc_datetime(self.processed_at)
            <= now
        )

    def document(self) -> dict[str, object]:
        return {
            "snapshotId": str(self.snapshot_id) if self.snapshot_id else None,
            "sourceStatus": self.status,
            "validatedAt": self.validated_at.isoformat() if self.validated_at else None,
            "processedAt": self.processed_at.isoformat() if self.processed_at else None,
            "resultFingerprint": self.result_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class SettlementRules:
    reference: str
    fingerprint: str
    period: str
    selections: frozenset[SelectionType]
    remake_policy: str = "review"
    forfeit_policy: str = "review"
    cancelled_policy: str = "review"
    active: bool = True

    def __post_init__(self) -> None:
        if not self.reference.strip() or not self.fingerprint.strip():
            raise ValueError("Les règles exigent une référence et une empreinte")
        if any(
            policy not in {"settle", "void", "review"}
            for policy in (self.remake_policy, self.forfeit_policy, self.cancelled_policy)
        ):
            raise ValueError("La politique d'exception doit être explicite")


@dataclass(frozen=True, slots=True)
class SettlementOutcome:
    status: PaperBetStatus
    reason: str
    evidence: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    @property
    def fingerprint(self) -> str:
        return fingerprint(
            {"status": self.status.value, "reason": self.reason, "evidence": dict(self.evidence)}
        )


def exception_outcome(
    flags: tuple[str, ...], rules: SettlementRules, evidence: dict[str, object]
) -> SettlementOutcome | None:
    if len(flags) > 1:
        return SettlementOutcome(PaperBetStatus.PENDING_REVIEW, "RESULT_FLAGS_CONFLICT", evidence)
    if not flags:
        return None
    policies = {
        "remake": rules.remake_policy,
        "forfeit": rules.forfeit_policy,
        "cancelled": rules.cancelled_policy,
    }
    policy = policies[flags[0]]
    if policy == "settle":
        return None
    return SettlementOutcome(
        PaperBetStatus.VOID if policy == "void" else PaperBetStatus.PENDING_REVIEW,
        f"{flags[0].upper()}_{policy.upper()}",
        evidence,
    )
