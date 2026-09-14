"""Lecture des marchés collectés sur les pages publiques ; aucun pari exécutable."""

from datetime import datetime
from importlib.metadata import version
from typing import Annotated

from fastapi import APIRouter, Query

from metiquo.api.dto import ItemResponse, PageInfo, PageResponse
from metiquo.api.real_historical_routes import _validate_period
from metiquo.contracts import ContractMetadata
from metiquo.contracts.enums import DataMode, FreshnessStatus
from metiquo.contracts.stake_scraping import StakeCollectionStatus, StakePublicEvent
from metiquo.foundation.time import Clock
from metiquo.repositories.postgres_stake_scraping import PostgresStakeScrapingRepository


def build_stake_scraping_router(
    repository: PostgresStakeScrapingRepository | None,
    clock: Clock,
    data_mode: DataMode,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/odds/stake", tags=["stake-scraping"])

    def metadata(freshness: FreshnessStatus, as_of: datetime | None) -> ContractMetadata:
        return ContractMetadata(
            data_mode=data_mode,
            freshness=freshness,
            as_of=as_of or clock.now().value,
            computed_at=clock.now().value,
            app_version=version("metiquo"),
        )

    @router.get("/status", response_model=ItemResponse[StakeCollectionStatus])
    def status() -> ItemResponse[StakeCollectionStatus]:
        value = (
            repository.status()
            if repository
            else StakeCollectionStatus(
                enabled=False,
                state="disabled",
                checked_at=None,
                last_success_at=None,
                next_attempt_at=None,
                detail="Mode mock : collecte réelle désactivée",
                event_count=0,
            )
        )
        freshness = (
            FreshnessStatus.FRESH if value.state == "operational" else FreshnessStatus.DEGRADED
        )
        return ItemResponse(data=value, meta=metadata(freshness, value.checked_at))

    @router.get("/events", response_model=PageResponse[StakePublicEvent])
    def events(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=20)] = 10,
        starts_from: Annotated[datetime | None, Query(alias="startsFrom")] = None,
        starts_to: Annotated[datetime | None, Query(alias="startsTo")] = None,
    ) -> PageResponse[StakePublicEvent]:
        _validate_period(starts_from, starts_to)
        page = (
            repository.page(
                offset=offset, limit=limit, starts_from=starts_from, starts_to=starts_to
            )
            if repository
            else None
        )
        values = page.items if page else ()
        freshness = (
            FreshnessStatus.FAILED
            if not values
            else FreshnessStatus.STALE
            if any(v.freshness is FreshnessStatus.STALE for v in values)
            else FreshnessStatus.DEGRADED
            if any(v.freshness is FreshnessStatus.DEGRADED for v in values)
            else FreshnessStatus.FRESH
        )
        return PageResponse(
            data=values,
            page=PageInfo(offset=offset, limit=limit, total=page.total if page else 0),
            meta=metadata(freshness, max((v.capture.observed_at for v in values), default=None)),
        )

    return router
