"""Routes réelles des événements historiques issues exclusivement de core."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from importlib.metadata import version
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from metiquo.api.dto import ItemResponse, OpportunityExplanation, PageInfo, PageResponse
from metiquo.contracts import ContractMetadata, Event, Market, OddsSnapshot, Opportunity
from metiquo.contracts.enums import (
    DataMode,
    EventStatus,
    FreshnessStatus,
    MarketType,
    ProviderStatus,
    ValueGrade,
)
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock
from metiquo.repositories.postgres_admin import PostgresAdminRepository
from metiquo.repositories.postgres_canonical import PostgresCanonicalRepository
from metiquo.repositories.postgres_opportunities import PostgresOpportunityRepository

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


def build_real_historical_router(
    repository: PostgresCanonicalRepository,
    opportunity_repository: PostgresOpportunityRepository,
    admin_repository: PostgresAdminRepository,
    clock: Clock,
) -> APIRouter:
    """Exposer les mêmes DTO événement que le mock avec des métadonnées réelles."""

    router = APIRouter(prefix="/api/v1", tags=["real-historical-events"])

    @router.get("/events", response_model=PageResponse[Event])
    def list_events(
        offset: Offset = 0,
        limit: Limit = 20,
        competition: str | None = None,
        team: str | None = None,
        status: EventStatus | None = None,
        starts_from: Annotated[datetime | None, Query(alias="startsFrom")] = None,
        starts_to: Annotated[datetime | None, Query(alias="startsTo")] = None,
    ) -> PageResponse[Event]:
        _validate_period(starts_from, starts_to)
        page = repository.page(
            offset=offset,
            limit=limit,
            competition=competition,
            team=team,
            status=status,
            starts_from=starts_from,
            starts_to=starts_to,
        )
        return PageResponse(
            data=page.items,
            page=PageInfo(offset=offset, limit=limit, total=page.total),
            meta=_meta(admin_repository, clock),
        )

    @router.get("/events/{event_id}", response_model=ItemResponse[Event])
    def get_event(event_id: UUID) -> ItemResponse[Event]:
        event = repository.get(event_id)
        if event is None:
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                "Événement introuvable",
                context={"id": str(event_id)},
            )
        return ItemResponse(data=event, meta=_meta(admin_repository, clock))

    @router.get("/events/{event_id}/markets", response_model=PageResponse[Market])
    def list_event_markets(
        event_id: UUID,
        offset: Offset = 0,
        limit: Limit = 20,
    ) -> PageResponse[Market]:
        _require_event(repository, event_id)
        return _page(repository.list_markets(event_id), offset, limit, admin_repository, clock)

    @router.get(
        "/events/{event_id}/odds-history",
        response_model=PageResponse[OddsSnapshot],
    )
    def get_odds_history(
        event_id: UUID,
        offset: Offset = 0,
        limit: Limit = 20,
    ) -> PageResponse[OddsSnapshot]:
        _require_event(repository, event_id)
        page = repository.odds_history_page(event_id, offset=offset, limit=limit)
        return PageResponse(
            data=page.items,
            page=PageInfo(offset=offset, limit=limit, total=page.total),
            meta=_odds_meta(page.items, admin_repository, clock),
        )

    @router.get("/opportunities", response_model=PageResponse[Opportunity])
    def list_opportunities(
        offset: Offset = 0,
        limit: Limit = 20,
        competition: str | None = None,
        team: str | None = None,
        market: MarketType | None = None,
        grade: ValueGrade | None = None,
        min_edge: Annotated[Decimal | None, Query(alias="minEdge", ge=-1, le=1)] = None,
        min_ev: Annotated[Decimal | None, Query(alias="minEv", ge=-1)] = None,
        min_confidence: Annotated[
            Decimal | None,
            Query(alias="minConfidence", ge=0, le=1),
        ] = None,
        freshness: FreshnessStatus | None = None,
        starts_from: Annotated[datetime | None, Query(alias="startsFrom")] = None,
        starts_to: Annotated[datetime | None, Query(alias="startsTo")] = None,
    ) -> PageResponse[Opportunity]:
        _validate_period(starts_from, starts_to)
        page = opportunity_repository.page(
            offset=offset,
            limit=limit,
            competition=competition,
            team=team,
            market=market,
            grade=grade,
            min_edge=min_edge,
            min_ev=min_ev,
            min_confidence=min_confidence,
            freshness=freshness,
            starts_from=starts_from,
            starts_to=starts_to,
        )
        return PageResponse(
            data=page.items,
            page=PageInfo(offset=offset, limit=limit, total=page.total),
            meta=_opportunity_meta(page.items, admin_repository, clock),
        )

    @router.get("/opportunities/{signal_id}", response_model=ItemResponse[Opportunity])
    def get_opportunity(signal_id: UUID) -> ItemResponse[Opportunity]:
        opportunity = _require_opportunity(opportunity_repository, signal_id)
        return ItemResponse(data=opportunity, meta=opportunity.meta)

    @router.get(
        "/opportunities/{signal_id}/explanation",
        response_model=ItemResponse[OpportunityExplanation],
    )
    def get_opportunity_explanation(
        signal_id: UUID,
    ) -> ItemResponse[OpportunityExplanation]:
        opportunity = _require_opportunity(opportunity_repository, signal_id)
        reasons = tuple(reason.value for reason in opportunity.quality.abstention_reasons)
        if not reasons:
            reasons = (
                f"Signal reproductible selon {opportunity.value.policy_version}",
                f"Prédiction {opportunity.model.prediction_id}",
                f"Snapshot de cote {opportunity.book.odds_snapshot_id}",
            )
        explanation = OpportunityExplanation(
            signal_id=opportunity.signal_id,
            reference=opportunity.explanation_reference or "signal-proof-v1:unavailable",
            publishable=opportunity.quality.publishable,
            reasons=reasons,
        )
        return ItemResponse(data=explanation, meta=opportunity.meta)

    return router


def _require_opportunity(
    repository: PostgresOpportunityRepository,
    signal_id: UUID,
) -> Opportunity:
    opportunity = repository.get(signal_id)
    if opportunity is None:
        raise BusinessError(
            ErrorCode.NOT_FOUND,
            "Opportunité introuvable",
            context={"id": str(signal_id)},
        )
    return opportunity


def _require_event(repository: PostgresCanonicalRepository, event_id: UUID) -> Event:
    event = repository.get(event_id)
    if event is None:
        raise BusinessError(
            ErrorCode.NOT_FOUND,
            "Événement introuvable",
            context={"id": str(event_id)},
        )
    return event


def _validate_period(starts_from: datetime | None, starts_to: datetime | None) -> None:
    for name, value in (("startsFrom", starts_from), ("startsTo", starts_to)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise BusinessError(ErrorCode.INVALID_INPUT, f"{name} doit inclure un fuseau horaire")
    if starts_from is not None and starts_to is not None and starts_to < starts_from:
        raise BusinessError(
            ErrorCode.INVALID_INPUT,
            "startsTo doit être postérieur ou égal à startsFrom",
        )


def _meta(repository: PostgresAdminRepository, clock: Clock) -> ContractMetadata:
    now = clock.now().value
    health = repository.list_data_sources()[0]
    as_of = health.last_success_at or now
    return ContractMetadata(
        data_mode=DataMode.REAL,
        freshness=health.freshness or FreshnessStatus.FAILED,
        as_of=as_of,
        computed_at=max(now, as_of),
        app_version=version("metiquo"),
    )


def _odds_meta(
    values: Sequence[OddsSnapshot],
    repository: PostgresAdminRepository,
    clock: Clock,
) -> ContractMetadata:
    if not values:
        return _meta(repository, clock)
    now = clock.now().value
    as_of = max(snapshot.captured_at for snapshot in values)
    health_by_provider = {health.provider_code: health for health in repository.list_data_sources()}
    freshness_values = tuple(
        health.freshness
        for snapshot in values
        if (health := health_by_provider.get(snapshot.provider)) is not None
        if health.freshness is not None
    )
    if FreshnessStatus.DEGRADED in freshness_values or FreshnessStatus.FAILED in freshness_values:
        freshness = FreshnessStatus.DEGRADED
    elif FreshnessStatus.STALE in freshness_values:
        freshness = FreshnessStatus.STALE
    elif any(snapshot.provider_status is not ProviderStatus.OPERATIONAL for snapshot in values):
        freshness = FreshnessStatus.DEGRADED
    else:
        freshness = FreshnessStatus.FRESH
    return ContractMetadata(
        data_mode=DataMode.REAL,
        freshness=freshness,
        as_of=as_of,
        computed_at=max(now, as_of),
        app_version=version("metiquo"),
    )


def _opportunity_meta(
    values: Sequence[Opportunity],
    repository: PostgresAdminRepository,
    clock: Clock,
) -> ContractMetadata:
    if not values:
        return _meta(repository, clock)
    priorities = {
        FreshnessStatus.FRESH: 0,
        FreshnessStatus.STALE: 1,
        FreshnessStatus.DEGRADED: 2,
        FreshnessStatus.QUARANTINED: 3,
        FreshnessStatus.FAILED: 4,
    }
    return ContractMetadata(
        data_mode=DataMode.REAL,
        freshness=max(
            (item.meta.freshness for item in values),
            key=priorities.__getitem__,
        ),
        as_of=max(item.meta.as_of for item in values),
        computed_at=max(item.meta.computed_at for item in values),
        app_version=version("metiquo"),
    )


def _page[T](
    values: Sequence[T],
    offset: int,
    limit: int,
    repository: PostgresAdminRepository,
    clock: Clock,
) -> PageResponse[T]:
    return PageResponse(
        data=tuple(values[offset : offset + limit]),
        page=PageInfo(offset=offset, limit=limit, total=len(values)),
        meta=_meta(repository, clock),
    )
