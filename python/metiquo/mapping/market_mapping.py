"""Mapping structurel et fermé des marchés fournisseur."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.contracts.enums import MarketPeriod, MarketType, SelectionType
from metiquo.db.odds_models import (
    MarketMappingAttempt,
    MarketRulesRecord,
    OddsProviderRecord,
    ProviderOddsEvent,
)
from metiquo.foundation.time import Clock, SystemClock

type SettlementPolicy = Literal["settle", "void", "review"]


class MarketMappingStatus(StrEnum):
    """Résultat fermé d'une tentative de mapping marché."""

    MAPPED = "mapped"
    UNKNOWN = "unknown"


class MarketMappingReason(StrEnum):
    """Motif stable et auditable d'une décision de marché."""

    STRUCTURE_MATCHED = "STRUCTURE_MATCHED"
    RULES_REFERENCE_MISSING = "RULES_REFERENCE_MISSING"
    RULES_REFERENCE_UNKNOWN = "RULES_REFERENCE_UNKNOWN"
    RULES_REFERENCE_INACTIVE = "RULES_REFERENCE_INACTIVE"
    MARKET_TYPE_MISMATCH = "MARKET_TYPE_MISMATCH"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    LINE_STRUCTURE_MISMATCH = "LINE_STRUCTURE_MISMATCH"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    OUTCOME_STRUCTURE_MISMATCH = "OUTCOME_STRUCTURE_MISMATCH"
    SETTLEMENT_POLICY_MISMATCH = "SETTLEMENT_POLICY_MISMATCH"


class UnresolvedMarketMappingError(RuntimeError):
    """Un marché inconnu tente d'atteindre une prédiction ou un prix."""


@dataclass(frozen=True, slots=True)
class MarketRulesReference:
    """Signature canonique versionnée requise pour activer un marché."""

    reference: str
    market_type: MarketType
    period: MarketPeriod
    line_required: bool
    unit: str
    selection_types: tuple[SelectionType, ...]
    remake_policy: SettlementPolicy
    forfeit_policy: SettlementPolicy
    cancelled_policy: SettlementPolicy
    active: bool = True

    def __post_init__(self) -> None:
        reference = self.reference.strip()
        unit = self.unit.strip().casefold()
        if not reference or len(reference) > 128:
            raise ValueError("la référence de règlement doit contenir entre 1 et 128 caractères")
        if not unit or len(unit) > 32:
            raise ValueError("l'unité de marché doit contenir entre 1 et 32 caractères")
        if len(self.selection_types) < 2 or len(set(self.selection_types)) != len(
            self.selection_types
        ):
            raise ValueError("les issues de la règle doivent être distinctes et au moins deux")
        if self.market_type is MarketType.MATCH_WINNER and self.line_required:
            raise ValueError("MATCH_WINNER ne porte jamais de ligne")
        if any(
            selection not in {SelectionType.TEAM_A, SelectionType.TEAM_B, SelectionType.DRAW}
            for selection in self.selection_types
        ):
            raise ValueError("MATCH_WINNER accepte uniquement TEAM_A, TEAM_B et DRAW")
        if {SelectionType.TEAM_A, SelectionType.TEAM_B} - set(self.selection_types):
            raise ValueError("MATCH_WINNER exige les deux équipes")
        object.__setattr__(self, "reference", reference)
        object.__setattr__(self, "unit", unit)


@dataclass(frozen=True, slots=True)
class RawProviderMarket:
    """Descripteur provider conservé même lorsque sa structure est inconnue."""

    provider_market_id: str
    raw_label: str
    declared_type: str
    period: str
    line: Decimal | None
    unit: str
    selection_types: tuple[str, ...]
    settlement_rules_reference: str | None
    remake_policy: str
    forfeit_policy: str
    cancelled_policy: str

    def __post_init__(self) -> None:
        provider_market_id = self.provider_market_id.strip()
        raw_label = self.raw_label.strip()
        if not provider_market_id or len(provider_market_id) > 255:
            raise ValueError("l'identifiant provider du marché est obligatoire")
        if not raw_label or len(raw_label) > 255:
            raise ValueError("le libellé brut du marché est obligatoire")
        if self.line is not None and not self.line.is_finite():
            raise ValueError("une ligne provider doit être finie")
        object.__setattr__(self, "provider_market_id", provider_market_id)
        object.__setattr__(self, "raw_label", raw_label)

    def audit_payload(self) -> dict[str, object]:
        return {
            "declaredType": self.declared_type,
            "period": self.period,
            "line": str(self.line) if self.line is not None else None,
            "unit": self.unit,
            "selectionTypes": list(self.selection_types),
            "outcomeCount": len(self.selection_types),
            "settlementRulesReference": self.settlement_rules_reference,
            "remakePolicy": self.remake_policy,
            "forfeitPolicy": self.forfeit_policy,
            "cancelledPolicy": self.cancelled_policy,
        }


@dataclass(frozen=True, slots=True)
class CanonicalMarketMapping:
    """Structure utilisable par les plugins après résolution complète."""

    market_type: MarketType
    period: MarketPeriod
    line: Decimal | None
    unit: str
    selection_types: tuple[SelectionType, ...]
    rules_reference: str


@dataclass(frozen=True, slots=True)
class MarketMappingDecision:
    """Décision dont les champs canoniques n'existent qu'après mapping."""

    status: MarketMappingStatus
    reason: MarketMappingReason
    provider_market_id: str
    mapping: CanonicalMarketMapping | None = None
    attempt_id: UUID | None = None

    @property
    def resolved(self) -> bool:
        return self.status is MarketMappingStatus.MAPPED and self.mapping is not None

    def require_mapped(self) -> CanonicalMarketMapping:
        if not self.resolved or self.mapping is None:
            raise UnresolvedMarketMappingError(
                "un marché inconnu ne peut alimenter aucune prédiction"
            )
        return self.mapping


@dataclass(frozen=True, slots=True)
class MarketMappingEngine:
    """Comparer une signature complète sans jamais interpréter son seul libellé."""

    rules: tuple[MarketRulesReference, ...]

    def __post_init__(self) -> None:
        references = tuple(rule.reference for rule in self.rules)
        if len(set(references)) != len(references):
            raise ValueError("une référence de règlement ne peut être déclarée deux fois")

    def evaluate(self, raw: RawProviderMarket) -> MarketMappingDecision:
        reference = (raw.settlement_rules_reference or "").strip()
        if not reference:
            return self._unknown(raw, MarketMappingReason.RULES_REFERENCE_MISSING)
        rule = next((item for item in self.rules if item.reference == reference), None)
        if rule is None:
            return self._unknown(raw, MarketMappingReason.RULES_REFERENCE_UNKNOWN)
        if not rule.active:
            return self._unknown(raw, MarketMappingReason.RULES_REFERENCE_INACTIVE)
        if raw.declared_type.strip() != rule.market_type.value:
            return self._unknown(raw, MarketMappingReason.MARKET_TYPE_MISMATCH)
        if raw.period.strip() != rule.period.value:
            return self._unknown(raw, MarketMappingReason.PERIOD_MISMATCH)
        if (raw.line is not None) != rule.line_required:
            return self._unknown(raw, MarketMappingReason.LINE_STRUCTURE_MISMATCH)
        if raw.unit.strip().casefold() != rule.unit:
            return self._unknown(raw, MarketMappingReason.UNIT_MISMATCH)
        raw_selections = tuple(item.strip() for item in raw.selection_types)
        expected = tuple(item.value for item in rule.selection_types)
        if len(raw_selections) != len(set(raw_selections)) or set(raw_selections) != set(expected):
            return self._unknown(raw, MarketMappingReason.OUTCOME_STRUCTURE_MISMATCH)
        if (
            raw.remake_policy.strip() != rule.remake_policy
            or raw.forfeit_policy.strip() != rule.forfeit_policy
            or raw.cancelled_policy.strip() != rule.cancelled_policy
        ):
            return self._unknown(raw, MarketMappingReason.SETTLEMENT_POLICY_MISMATCH)
        return MarketMappingDecision(
            status=MarketMappingStatus.MAPPED,
            reason=MarketMappingReason.STRUCTURE_MATCHED,
            provider_market_id=raw.provider_market_id,
            mapping=CanonicalMarketMapping(
                market_type=rule.market_type,
                period=rule.period,
                line=raw.line,
                unit=rule.unit,
                selection_types=rule.selection_types,
                rules_reference=rule.reference,
            ),
        )

    @staticmethod
    def _unknown(
        raw: RawProviderMarket,
        reason: MarketMappingReason,
    ) -> MarketMappingDecision:
        return MarketMappingDecision(
            status=MarketMappingStatus.UNKNOWN,
            reason=reason,
            provider_market_id=raw.provider_market_id,
        )


class PostgresMarketMappingService:
    """Enregistrer les règles et chaque tentative de résolution de marché."""

    def __init__(self, engine: Engine, clock: Clock | None = None) -> None:
        self.engine = engine
        self.clock = clock or SystemClock()

    def register_rules(self, rule: MarketRulesReference) -> UUID:
        rules = cast(Table, MarketRulesRecord.__table__)
        fingerprint = _rules_fingerprint(rule)
        rule_id = uuid4()
        with self.engine.begin() as connection:
            inserted = connection.execute(
                insert(rules)
                .values(
                    id=rule_id,
                    reference=rule.reference,
                    market_type=rule.market_type.value,
                    period=rule.period.value,
                    line_required=rule.line_required,
                    unit=rule.unit,
                    selection_types=[item.value for item in rule.selection_types],
                    remake_policy=rule.remake_policy,
                    forfeit_policy=rule.forfeit_policy,
                    cancelled_policy=rule.cancelled_policy,
                    active=rule.active,
                    fingerprint=fingerprint,
                    created_at=self.clock.now().value,
                )
                .on_conflict_do_nothing(index_elements=[rules.c.reference])
                .returning(rules.c.id)
            ).scalar_one_or_none()
            if inserted is not None:
                return cast(UUID, inserted)
            existing = connection.execute(
                select(rules.c.id, rules.c.fingerprint).where(rules.c.reference == rule.reference)
            ).one()
            if existing.fingerprint != fingerprint:
                raise ValueError("la référence de règlement existe avec une autre signature")
            return cast(UUID, existing.id)

    def map_market(
        self,
        provider_code: str,
        provider_event_id: str,
        raw: RawProviderMarket,
    ) -> MarketMappingDecision:
        event_id = self._provider_event_id(provider_code, provider_event_id)
        decision = MarketMappingEngine(self._rules()).evaluate(raw)
        attempt_id = uuid4()
        mapping = decision.mapping
        attempts = cast(Table, MarketMappingAttempt.__table__)
        with self.engine.begin() as connection:
            connection.execute(
                attempts.insert().values(
                    id=attempt_id,
                    provider_event_id=event_id,
                    provider_market_id=raw.provider_market_id,
                    raw_label=raw.raw_label,
                    raw_descriptor=raw.audit_payload(),
                    result_status=decision.status.value,
                    canonical_market_type=(mapping.market_type.value if mapping else None),
                    canonical_period=(mapping.period.value if mapping else None),
                    canonical_line=(mapping.line if mapping else None),
                    rules_reference=(mapping.rules_reference if mapping else None),
                    reason_code=decision.reason.value,
                    evaluated_at=self.clock.now().value,
                )
            )
        return replace(decision, attempt_id=attempt_id)

    def _rules(self) -> tuple[MarketRulesReference, ...]:
        rules = cast(Table, MarketRulesRecord.__table__)
        with self.engine.connect() as connection:
            rows = connection.execute(select(rules).order_by(rules.c.reference)).mappings()
            return tuple(_rule_from_row(row) for row in rows)

    def _provider_event_id(self, provider_code: str, provider_event_id: str) -> UUID:
        providers = cast(Table, OddsProviderRecord.__table__)
        events = cast(Table, ProviderOddsEvent.__table__)
        with self.engine.connect() as connection:
            value = connection.execute(
                select(events.c.id)
                .join(providers, providers.c.id == events.c.provider_id)
                .where(
                    providers.c.code == provider_code,
                    events.c.provider_event_id == provider_event_id,
                )
            ).scalar_one_or_none()
        if value is None:
            raise ValueError("l'événement provider du marché est introuvable")
        return cast(UUID, value)


def _rule_from_row(row: RowMapping) -> MarketRulesReference:
    return MarketRulesReference(
        reference=cast(str, row["reference"]),
        market_type=MarketType(cast(str, row["market_type"])),
        period=MarketPeriod(cast(str, row["period"])),
        line_required=bool(row["line_required"]),
        unit=cast(str, row["unit"]),
        selection_types=tuple(
            SelectionType(item) for item in cast(list[str], row["selection_types"])
        ),
        remake_policy=cast(SettlementPolicy, row["remake_policy"]),
        forfeit_policy=cast(SettlementPolicy, row["forfeit_policy"]),
        cancelled_policy=cast(SettlementPolicy, row["cancelled_policy"]),
        active=bool(row["active"]),
    )


def _rules_fingerprint(rule: MarketRulesReference) -> str:
    payload = {
        "reference": rule.reference,
        "marketType": rule.market_type.value,
        "period": rule.period.value,
        "lineRequired": rule.line_required,
        "unit": rule.unit,
        "selectionTypes": sorted(item.value for item in rule.selection_types),
        "remakePolicy": rule.remake_policy,
        "forfeitPolicy": rule.forfeit_policy,
        "cancelledPolicy": rule.cancelled_policy,
        "active": rule.active,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
