"""Politiques versionnées de seuils pour les décisions de value."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import cast
from uuid import UUID

from metiquo.config import Settings
from metiquo.contracts.enums import MarketType
from metiquo.foundation.time import normalize_utc_datetime


class ValuePolicyError(ValueError):
    """Une politique de signal est incohérente ou ambiguë."""


@dataclass(frozen=True, slots=True)
class ValueThresholds:
    """Seuils complets appliqués à une décision de value."""

    min_edge: Decimal
    min_ev: Decimal
    min_conservative_ev: Decimal
    max_odds_age_seconds: int
    min_mapping_confidence: Decimal

    def __post_init__(self) -> None:
        for label, value in (
            ("min_edge", self.min_edge),
            ("min_ev", self.min_ev),
            ("min_conservative_ev", self.min_conservative_ev),
            ("min_mapping_confidence", self.min_mapping_confidence),
        ):
            if not value.is_finite() or not Decimal() <= value <= Decimal(1):
                raise ValuePolicyError(f"{label} doit être fini et appartenir à [0,1]")
        if self.max_odds_age_seconds <= 0:
            raise ValuePolicyError("max_odds_age_seconds doit être strictement positif")

    @classmethod
    def from_settings(cls, settings: Settings) -> ValueThresholds:
        return cls(
            min_edge=settings.signal_min_edge,
            min_ev=settings.signal_min_ev,
            min_conservative_ev=settings.signal_min_conservative_ev,
            max_odds_age_seconds=settings.odds_max_age_seconds,
            min_mapping_confidence=settings.signal_min_mapping_confidence,
        )

    def document(self) -> dict[str, object]:
        return {
            "minEdge": _canonical_decimal(self.min_edge),
            "minEv": _canonical_decimal(self.min_ev),
            "minConservativeEv": _canonical_decimal(self.min_conservative_ev),
            "maxOddsAgeSeconds": self.max_odds_age_seconds,
            "minMappingConfidence": _canonical_decimal(self.min_mapping_confidence),
        }


@dataclass(frozen=True, slots=True)
class ValueThresholdOverride:
    """Sous-ensemble de seuils remplacés par un périmètre explicite."""

    min_edge: Decimal | None = None
    min_ev: Decimal | None = None
    min_conservative_ev: Decimal | None = None
    max_odds_age_seconds: int | None = None
    min_mapping_confidence: Decimal | None = None

    def __post_init__(self) -> None:
        if all(
            value is None
            for value in (
                self.min_edge,
                self.min_ev,
                self.min_conservative_ev,
                self.max_odds_age_seconds,
                self.min_mapping_confidence,
            )
        ):
            raise ValuePolicyError("une surcharge doit modifier au moins un seuil")
        for label, value in (
            ("min_edge", self.min_edge),
            ("min_ev", self.min_ev),
            ("min_conservative_ev", self.min_conservative_ev),
            ("min_mapping_confidence", self.min_mapping_confidence),
        ):
            if value is not None and (
                not value.is_finite() or not Decimal() <= value <= Decimal(1)
            ):
                raise ValuePolicyError(f"{label} doit être fini et appartenir à [0,1]")
        if self.max_odds_age_seconds is not None and self.max_odds_age_seconds <= 0:
            raise ValuePolicyError("max_odds_age_seconds doit être strictement positif")

    def apply(self, base: ValueThresholds) -> ValueThresholds:
        return ValueThresholds(
            min_edge=self.min_edge if self.min_edge is not None else base.min_edge,
            min_ev=self.min_ev if self.min_ev is not None else base.min_ev,
            min_conservative_ev=(
                self.min_conservative_ev
                if self.min_conservative_ev is not None
                else base.min_conservative_ev
            ),
            max_odds_age_seconds=(
                self.max_odds_age_seconds
                if self.max_odds_age_seconds is not None
                else base.max_odds_age_seconds
            ),
            min_mapping_confidence=(
                self.min_mapping_confidence
                if self.min_mapping_confidence is not None
                else base.min_mapping_confidence
            ),
        )

    def document(self) -> dict[str, object]:
        values: dict[str, object] = {}
        if self.min_edge is not None:
            values["minEdge"] = _canonical_decimal(self.min_edge)
        if self.min_ev is not None:
            values["minEv"] = _canonical_decimal(self.min_ev)
        if self.min_conservative_ev is not None:
            values["minConservativeEv"] = _canonical_decimal(self.min_conservative_ev)
        if self.max_odds_age_seconds is not None:
            values["maxOddsAgeSeconds"] = self.max_odds_age_seconds
        if self.min_mapping_confidence is not None:
            values["minMappingConfidence"] = _canonical_decimal(self.min_mapping_confidence)
        return values


@dataclass(frozen=True, slots=True)
class ResolvedValuePolicy:
    """Seuils effectifs et trace des surcharges utilisées."""

    policy_version: str
    thresholds: ValueThresholds
    applied_scopes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValuePolicy:
    """Version immuable dont le tuning précède strictement le test final."""

    version: str
    thresholds: ValueThresholds
    tuned_through: datetime
    final_test_starts_at: datetime
    market_overrides: Mapping[MarketType, ValueThresholdOverride] = MappingProxyType({})
    competition_overrides: Mapping[UUID, ValueThresholdOverride] = MappingProxyType({})
    bucket_overrides: Mapping[str, ValueThresholdOverride] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not isinstance(self.thresholds, ValueThresholds):
            raise TypeError("thresholds doit être un ValueThresholds")
        version = self.version.strip()
        if not version or len(version) > 128:
            raise ValuePolicyError("version doit contenir entre 1 et 128 caractères")
        tuned_through = normalize_utc_datetime(self.tuned_through)
        final_test_starts_at = normalize_utc_datetime(self.final_test_starts_at)
        if tuned_through >= final_test_starts_at:
            raise ValuePolicyError("le tuning doit précéder strictement la période de test finale")
        market_overrides = dict(self.market_overrides)
        competition_overrides = dict(self.competition_overrides)
        raw_buckets = dict(self.bucket_overrides)
        bucket_overrides = {key.strip(): value for key, value in raw_buckets.items()}
        if len(bucket_overrides) != len(raw_buckets) or any(not key for key in bucket_overrides):
            raise ValuePolicyError("les buckets refusent les clés vides ou dupliquées après trim")
        if any(not isinstance(key, MarketType) for key in market_overrides):
            raise TypeError("les surcharges marché exigent des MarketType")
        if any(not isinstance(key, UUID) for key in competition_overrides):
            raise TypeError("les surcharges compétition exigent des UUID")
        if any(
            not isinstance(value, ValueThresholdOverride)
            for value in (
                *market_overrides.values(),
                *competition_overrides.values(),
                *bucket_overrides.values(),
            )
        ):
            raise TypeError("chaque surcharge doit être un ValueThresholdOverride")
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "tuned_through", tuned_through)
        object.__setattr__(self, "final_test_starts_at", final_test_starts_at)
        object.__setattr__(self, "market_overrides", MappingProxyType(market_overrides))
        object.__setattr__(self, "competition_overrides", MappingProxyType(competition_overrides))
        object.__setattr__(self, "bucket_overrides", MappingProxyType(bucket_overrides))

    def resolve(
        self,
        market_type: MarketType,
        *,
        competition_id: UUID | None = None,
        bucket: str | None = None,
    ) -> ResolvedValuePolicy:
        """Appliquer global, marché, compétition puis bucket dans cet ordre."""

        thresholds = self.thresholds
        scopes: list[str] = []
        market_override = self.market_overrides.get(market_type)
        if market_override is not None:
            thresholds = market_override.apply(thresholds)
            scopes.append(f"market:{market_type.value}")
        if competition_id is not None:
            competition_override = self.competition_overrides.get(competition_id)
            if competition_override is not None:
                thresholds = competition_override.apply(thresholds)
                scopes.append(f"competition:{competition_id}")
        normalized_bucket = bucket.strip() if bucket is not None else None
        if bucket is not None and not normalized_bucket:
            raise ValuePolicyError("bucket ne peut pas être vide")
        if normalized_bucket is not None:
            bucket_override = self.bucket_overrides.get(normalized_bucket)
            if bucket_override is not None:
                thresholds = bucket_override.apply(thresholds)
                scopes.append(f"bucket:{normalized_bucket}")
        return ResolvedValuePolicy(self.version, thresholds, tuple(scopes))

    def document(self) -> dict[str, object]:
        return {
            "version": self.version,
            "thresholds": self.thresholds.document(),
            "tunedThrough": self.tuned_through.isoformat(),
            "finalTestStartsAt": self.final_test_starts_at.isoformat(),
            "overrides": _overrides_document(self),
        }

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.document(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def value_policy_from_storage(
    *,
    version: str,
    thresholds: ValueThresholds,
    tuned_through: datetime,
    final_test_starts_at: datetime,
    overrides: Mapping[str, object],
) -> ValuePolicy:
    market_document = cast(Mapping[str, object], overrides.get("market", {}))
    competition_document = cast(Mapping[str, object], overrides.get("competition", {}))
    bucket_document = cast(Mapping[str, object], overrides.get("bucket", {}))
    return ValuePolicy(
        version=version,
        thresholds=thresholds,
        tuned_through=tuned_through,
        final_test_starts_at=final_test_starts_at,
        market_overrides={
            MarketType(key): _override_from_document(cast(Mapping[str, object], value))
            for key, value in market_document.items()
        },
        competition_overrides={
            UUID(key): _override_from_document(cast(Mapping[str, object], value))
            for key, value in competition_document.items()
        },
        bucket_overrides={
            key: _override_from_document(cast(Mapping[str, object], value))
            for key, value in bucket_document.items()
        },
    )


def _overrides_document(policy: ValuePolicy) -> dict[str, object]:
    return {
        "market": {
            key.value: value.document()
            for key, value in sorted(
                policy.market_overrides.items(), key=lambda item: item[0].value
            )
        },
        "competition": {
            str(key): value.document()
            for key, value in sorted(
                policy.competition_overrides.items(), key=lambda item: str(item[0])
            )
        },
        "bucket": {key: value.document() for key, value in sorted(policy.bucket_overrides.items())},
    }


def _override_from_document(document: Mapping[str, object]) -> ValueThresholdOverride:
    return ValueThresholdOverride(
        min_edge=_optional_decimal(document.get("minEdge")),
        min_ev=_optional_decimal(document.get("minEv")),
        min_conservative_ev=_optional_decimal(document.get("minConservativeEv")),
        max_odds_age_seconds=_optional_int(document.get("maxOddsAgeSeconds")),
        min_mapping_confidence=_optional_decimal(document.get("minMappingConfidence")),
    )


def _optional_decimal(value: object | None) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValuePolicyError("un seuil décimal stocké doit être une chaîne")
    return Decimal(value)


def _optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValuePolicyError("maxOddsAgeSeconds stocké doit être un entier")
    return value


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")
