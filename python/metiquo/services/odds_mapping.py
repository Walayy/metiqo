"""Gate intégré capture, événement, marché et historique coté."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, Table, select

from metiquo.contracts import Event
from metiquo.contracts.odds_provider import ProviderEvent
from metiquo.db.odds_models import OddsSnapshotRecord
from metiquo.mapping import (
    EventMappingDecision,
    MarketMappingDecision,
    PostgresEventMatchingService,
    PostgresMarketMappingService,
    raw_market_from_provider,
)
from metiquo.providers import OddsProvider
from metiquo.services.odds_capture import OddsCaptureReport, OddsCaptureService, OddsCaptureSource


class ResolvedOddsGateReason(StrEnum):
    """Causes fermées empêchant un historique coté d'atteindre le pricing."""

    EVENT_MAPPING_UNRESOLVED = "EVENT_MAPPING_UNRESOLVED"
    MARKET_MAPPING_UNRESOLVED = "MARKET_MAPPING_UNRESOLVED"
    ODDS_MISSING = "ODDS_MISSING"
    ODDS_TIMESTAMP_UNRELIABLE = "ODDS_TIMESTAMP_UNRELIABLE"


class OddsPricingGateError(RuntimeError):
    """Le parcours coté ne possède pas toutes les preuves P5."""


@dataclass(frozen=True, slots=True)
class ResolvedOddsContext:
    """Références minimales autorisées à franchir la frontière du pricing."""

    canonical_event_id: UUID
    provider_event_id: UUID
    market_mappings: tuple[MarketMappingDecision, ...]
    usable_snapshot_count: int
    odds_as_of: datetime


@dataclass(frozen=True, slots=True)
class ResolvedOddsGateResult:
    """Résultat auditable du gate, sans produire lui-même de prix."""

    capture: OddsCaptureReport
    event_mapping: EventMappingDecision
    market_mappings: tuple[MarketMappingDecision, ...]
    usable_snapshot_count: int
    odds_as_of: datetime | None
    reason_codes: tuple[ResolvedOddsGateReason, ...]

    @property
    def ready(self) -> bool:
        return not self.reason_codes

    def require_pricing_ready(self) -> ResolvedOddsContext:
        canonical_event_id = self.event_mapping.selected_event_id
        if not self.ready or canonical_event_id is None or self.odds_as_of is None:
            reasons = ",".join(reason.value for reason in self.reason_codes)
            raise OddsPricingGateError(f"historique coté non résolu : {reasons}")
        return ResolvedOddsContext(
            canonical_event_id=canonical_event_id,
            provider_event_id=self.capture.event_id,
            market_mappings=self.market_mappings,
            usable_snapshot_count=self.usable_snapshot_count,
            odds_as_of=self.odds_as_of,
        )


class PostgresResolvedOddsGate:
    """Vérifier les preuves persistées sans modifier les observations."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def evaluate(
        self,
        capture: OddsCaptureReport,
        event_mapping: EventMappingDecision,
        market_mappings: tuple[MarketMappingDecision, ...],
    ) -> ResolvedOddsGateResult:
        reasons: list[ResolvedOddsGateReason] = []
        if not event_mapping.resolved:
            reasons.append(ResolvedOddsGateReason.EVENT_MAPPING_UNRESOLVED)
        if not market_mappings or any(not decision.resolved for decision in market_mappings):
            reasons.append(ResolvedOddsGateReason.MARKET_MAPPING_UNRESOLVED)
        snapshots = cast(Table, OddsSnapshotRecord.__table__)
        with self.engine.connect() as connection:
            rows = tuple(
                connection.execute(
                    select(
                        snapshots.c.captured_at,
                        snapshots.c.timestamp_reliable,
                        snapshots.c.informational_only,
                    ).where(snapshots.c.event_id == capture.event_id)
                )
            )
        if not rows:
            reasons.append(ResolvedOddsGateReason.ODDS_MISSING)
        usable_times = tuple(
            cast(datetime, row.captured_at)
            for row in rows
            if row.captured_at is not None
            and bool(row.timestamp_reliable)
            and not bool(row.informational_only)
        )
        if rows and not usable_times:
            reasons.append(ResolvedOddsGateReason.ODDS_TIMESTAMP_UNRELIABLE)
        return ResolvedOddsGateResult(
            capture=capture,
            event_mapping=event_mapping,
            market_mappings=market_mappings,
            usable_snapshot_count=len(usable_times),
            odds_as_of=max(usable_times, default=None),
            reason_codes=tuple(dict.fromkeys(reasons)),
        )


class ResolvedOddsPipeline:
    """Orchestrer P5 en réutilisant exactement les services spécialisés."""

    def __init__(
        self,
        capture_service: OddsCaptureService,
        event_mapping_service: PostgresEventMatchingService,
        market_mapping_service: PostgresMarketMappingService,
        gate: PostgresResolvedOddsGate,
    ) -> None:
        self.capture_service = capture_service
        self.event_mapping_service = event_mapping_service
        self.market_mapping_service = market_mapping_service
        self.gate = gate

    def process(
        self,
        provider: OddsProvider,
        event: ProviderEvent,
        source: OddsCaptureSource,
        canonical_candidates: tuple[Event, ...],
    ) -> ResolvedOddsGateResult:
        capture = self.capture_service.capture_event(provider, event, source)
        event_mapping = self.event_mapping_service.match_event(
            provider.provider_code,
            event,
            canonical_candidates,
        )
        market_mappings = tuple(
            self.market_mapping_service.map_market(
                provider.provider_code,
                event.provider_event_id,
                raw_market_from_provider(market),
            )
            for market in capture.markets
        )
        return self.gate.evaluate(capture, event_mapping, market_mappings)
