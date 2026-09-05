"""Routes réelles des événements historiques issues exclusivement de core."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from importlib.metadata import version
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from metiquo.api.dto import ItemResponse, PageInfo, PageResponse
from metiquo.contracts import ContractMetadata, Event, Market, OddsSnapshot, Opportunity
from metiquo.contracts.enums import (
    DataMode,
    EventStatus,
    FreshnessStatus,
    ProviderStatus,
)
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock
from metiquo.repositories.postgres_admin import PostgresAdminRepository
from metiquo.repositories.postgres_canonical import PostgresCanonicalRepository

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


def build_real_historical_router(
    repository: PostgresCanonicalRepository,
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
        values = tuple(
            event
            for event in repository.list()
            if _matches(event.competition, competition)
            and (team is None or _matches(event.team_a, team) or _matches(event.team_b, team))
            and (status is None or event.status is status)
            and (starts_from is None or event.starts_at >= starts_from)
            and (starts_to is None or event.starts_at <= starts_to)
        )
        return _page(values, offset, limit, admin_repository, clock)

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
        return _page(repository.odds_history(event_id), offset, limit, admin_repository, clock)

    @router.get("/opportunities", response_model=PageResponse[Opportunity])
    def list_opportunities(
        offset: Offset = 0,
        limit: Limit = 20,
    ) -> PageResponse[Opportunity]:
        return _page((), offset, limit, admin_repository, clock)

    return router


def _require_event(repository: PostgresCanonicalRepository, event_id: UUID) -> Event:
    event = repository.get(event_id)
    if event is None:
        raise BusinessError(
            ErrorCode.NOT_FOUND,
            "Événement introuvable",
            context={"id": str(event_id)},
        )
    return event


def _matches(value: str, query: str | None) -> bool:
    return query is None or query.casefold() in value.casefold()


def _validate_period(starts_from: datetime | None, starts_to: datetime | None) -> None:
    for name, value in (("startsFrom", starts_from), ("startsTo", starts_to)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise BusinessError(ErrorCode.INVALID_INPUT, f"{name} doit inclure un fuseau horaire")
    if starts_from is not None and starts_to is not None and starts_to < starts_from:
        raise BusinessError(
            ErrorCode.INVALID_INPUT,
            "startsTo doit être postérieur ou égal à startsFrom",
        )


def _freshness(repository: PostgresAdminRepository) -> FreshnessStatus:
    return {
        ProviderStatus.OPERATIONAL: FreshnessStatus.FRESH,
        ProviderStatus.DEGRADED: FreshnessStatus.DEGRADED,
        ProviderStatus.UNAVAILABLE: FreshnessStatus.FAILED,
        ProviderStatus.DISABLED: FreshnessStatus.FAILED,
    }[repository.list_data_sources()[0].status]


def _meta(repository: PostgresAdminRepository, clock: Clock) -> ContractMetadata:
    now = clock.now().value
    health = repository.list_data_sources()[0]
    as_of = health.last_success_at or now
    return ContractMetadata(
        data_mode=DataMode.REAL,
        freshness=_freshness(repository),
        as_of=as_of,
        computed_at=max(now, as_of),
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
