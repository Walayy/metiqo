"""Fraîcheur et admissibilité bloquantes des marchés de cotes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType

from metiquo.config import Settings
from metiquo.contracts import OddsSnapshot
from metiquo.contracts.enums import (
    AbstentionReason,
    MarketStatus,
    MarketType,
    OddsPhase,
    SelectionType,
)
from metiquo.foundation.time import normalize_utc_datetime


@dataclass(frozen=True, slots=True)
class OddsFreshnessPolicy:
    """SLA global avec surcharges provider, marché puis phase."""

    default_max_age_seconds: int
    provider_overrides: Mapping[str, int] = MappingProxyType({})
    market_overrides: Mapping[MarketType, int] = MappingProxyType({})
    phase_overrides: Mapping[OddsPhase, int] = MappingProxyType({})

    def __post_init__(self) -> None:
        if self.default_max_age_seconds <= 0:
            raise ValueError("default_max_age_seconds doit être strictement positif")
        provider_overrides = {
            provider.strip(): seconds for provider, seconds in self.provider_overrides.items()
        }
        if any(not provider for provider in provider_overrides):
            raise ValueError("un code provider de fraîcheur ne peut pas être vide")
        for seconds in (
            *provider_overrides.values(),
            *self.market_overrides.values(),
            *self.phase_overrides.values(),
        ):
            if seconds <= 0:
                raise ValueError("chaque max_age_seconds doit être strictement positif")
        object.__setattr__(self, "provider_overrides", MappingProxyType(provider_overrides))
        object.__setattr__(
            self,
            "market_overrides",
            MappingProxyType(dict(self.market_overrides)),
        )
        object.__setattr__(
            self,
            "phase_overrides",
            MappingProxyType(dict(self.phase_overrides)),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> OddsFreshnessPolicy:
        """Construire la politique depuis la configuration serveur validée."""

        return cls(
            default_max_age_seconds=settings.odds_max_age_seconds,
            provider_overrides=settings.odds_provider_max_age_seconds,
            market_overrides=settings.odds_market_max_age_seconds,
            phase_overrides=settings.odds_phase_max_age_seconds,
        )

    def max_age_seconds(
        self,
        provider_code: str,
        market_type: MarketType,
        phase: OddsPhase,
    ) -> int:
        """Résoudre le SLA le plus spécifique selon une priorité documentée."""

        normalized_provider = provider_code.strip()
        if not normalized_provider:
            raise ValueError("provider_code est obligatoire")
        if normalized_provider in self.provider_overrides:
            return self.provider_overrides[normalized_provider]
        if market_type in self.market_overrides:
            return self.market_overrides[market_type]
        if phase in self.phase_overrides:
            return self.phase_overrides[phase]
        return self.default_max_age_seconds


@dataclass(frozen=True, slots=True)
class MarketAdmissibilityInput:
    """Vue complète d'un marché au moment d'une décision de signal."""

    provider_code: str
    event_starts_at: datetime
    market_type: MarketType
    phase: OddsPhase
    evaluated_at: datetime
    required_selection: SelectionType
    expected_selections: frozenset[SelectionType]
    snapshots: tuple[OddsSnapshot, ...]
    requires_complete_market: bool = True

    def __post_init__(self) -> None:
        provider_code = self.provider_code.strip()
        if not provider_code:
            raise ValueError("provider_code est obligatoire")
        if not self.expected_selections:
            raise ValueError("expected_selections ne peut pas être vide")
        object.__setattr__(self, "provider_code", provider_code)
        object.__setattr__(
            self,
            "event_starts_at",
            normalize_utc_datetime(self.event_starts_at),
        )
        object.__setattr__(
            self,
            "evaluated_at",
            normalize_utc_datetime(self.evaluated_at),
        )


@dataclass(frozen=True, slots=True)
class MarketAdmissibilityDecision:
    """Décision explicite, y compris lorsqu'aucun signal ne peut être publié."""

    admissible: bool
    reasons: tuple[AbstentionReason, ...]
    max_age_seconds: int
    age_seconds: int | None

    def __post_init__(self) -> None:
        if self.admissible == bool(self.reasons):
            raise ValueError("une décision admissible ne doit porter aucune abstention")


class MarketAdmissibilityGate:
    """Appliquer les blocages temporels et de complétude avant tout pricing."""

    def __init__(self, policy: OddsFreshnessPolicy) -> None:
        self.policy = policy

    def evaluate(self, request: MarketAdmissibilityInput) -> MarketAdmissibilityDecision:
        """Évaluer le marché sans transformer une abstention en exception."""

        max_age_seconds = self.policy.max_age_seconds(
            request.provider_code,
            request.market_type,
            request.phase,
        )
        reasons: list[AbstentionReason] = []
        if request.phase is OddsPhase.LIVE:
            reasons.append(AbstentionReason.LIVE_BETTING_OUT_OF_SCOPE)

        snapshots = request.snapshots
        selection_counts: dict[SelectionType, int] = {}
        for snapshot in snapshots:
            selection_counts[snapshot.selection] = selection_counts.get(snapshot.selection, 0) + 1
        observed_selections = frozenset(selection_counts)
        if request.required_selection not in observed_selections:
            reasons.append(AbstentionReason.SELECTION_MISSING)
        if request.requires_complete_market and observed_selections != request.expected_selections:
            reasons.append(AbstentionReason.MARKET_OUTCOMES_INCOMPLETE)
        if any(count != 1 for count in selection_counts.values()):
            reasons.append(AbstentionReason.ODDS_TEMPORAL_ORDER_INVALID)

        if snapshots:
            first = snapshots[0]
            if any(
                snapshot.provider != request.provider_code
                or snapshot.event_id != first.event_id
                or snapshot.market_id != first.market_id
                for snapshot in snapshots
            ):
                reasons.append(AbstentionReason.ODDS_TEMPORAL_ORDER_INVALID)
            if any(snapshot.market_status is not MarketStatus.OPEN for snapshot in snapshots):
                reasons.append(AbstentionReason.MARKET_SUSPENDED)
            if any(snapshot.informational_only for snapshot in snapshots):
                reasons.append(AbstentionReason.ODDS_INFORMATIONAL_ONLY)
            if any(snapshot.captured_at > request.evaluated_at for snapshot in snapshots):
                reasons.append(AbstentionReason.ODDS_TEMPORAL_ORDER_INVALID)
            if request.phase is OddsPhase.PREMATCH and any(
                snapshot.captured_at >= request.event_starts_at for snapshot in snapshots
            ):
                reasons.append(AbstentionReason.EVENT_ALREADY_STARTED)
            oldest_capture = min(snapshot.captured_at for snapshot in snapshots)
            age = request.evaluated_at - oldest_capture
            if age > timedelta(seconds=max_age_seconds):
                reasons.append(AbstentionReason.ODDS_STALE)
            age_seconds = int(age.total_seconds())
        else:
            age_seconds = None

        if request.phase is OddsPhase.PREMATCH and request.evaluated_at >= request.event_starts_at:
            reasons.append(AbstentionReason.EVENT_ALREADY_STARTED)

        unique_reasons = tuple(dict.fromkeys(reasons))
        return MarketAdmissibilityDecision(
            admissible=not unique_reasons,
            reasons=unique_reasons,
            max_age_seconds=max_age_seconds,
            age_seconds=age_seconds,
        )
