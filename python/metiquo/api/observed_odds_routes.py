"""Consulter les observations réelles sans fabriquer d'événement canonique."""

from datetime import datetime
from importlib.metadata import version
from typing import Annotated

from fastapi import APIRouter, Query

from metiquo.api.dto import PageInfo, PageResponse
from metiquo.api.real_historical_routes import _validate_period
from metiquo.contracts import ContractMetadata
from metiquo.contracts.enums import DataMode, FreshnessStatus
from metiquo.contracts.observed_odds import ObservedOddsQuote
from metiquo.foundation.time import Clock
from metiquo.repositories.postgres_observed_odds import PostgresObservedOddsRepository


def build_observed_odds_router(
    repository: PostgresObservedOddsRepository | None, clock: Clock, data_mode: DataMode
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/odds", tags=["observed-odds"])

    @router.get("/quotes", response_model=PageResponse[ObservedOddsQuote])
    def list_observed_odds(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        provider: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
        starts_from: Annotated[datetime | None, Query(alias="startsFrom")] = None,
        starts_to: Annotated[datetime | None, Query(alias="startsTo")] = None,
    ) -> PageResponse[ObservedOddsQuote]:
        _validate_period(starts_from, starts_to)
        now = clock.now().value
        page = (
            repository.page(
                offset=offset,
                limit=limit,
                provider=provider,
                starts_from=starts_from,
                starts_to=starts_to,
            )
            if repository is not None
            else None
        )
        values = page.items if page else ()
        freshness = FreshnessStatus.FAILED
        if values:
            freshness = (
                FreshnessStatus.DEGRADED
                if any(q.freshness is FreshnessStatus.DEGRADED for q in values)
                else FreshnessStatus.STALE
                if any(q.freshness is FreshnessStatus.STALE for q in values)
                else FreshnessStatus.FRESH
            )
        return PageResponse(
            data=values,
            page=PageInfo(offset=offset, limit=limit, total=page.total if page else 0),
            meta=ContractMetadata(
                data_mode=data_mode,
                freshness=freshness,
                as_of=max((q.captured_at for q in values), default=now),
                computed_at=now,
                app_version=version("metiquo"),
            ),
        )

    return router
