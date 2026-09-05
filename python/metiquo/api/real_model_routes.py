"""Routes de lecture du registre ML PostgreSQL."""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import version
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from metiquo.api.dto import ItemResponse, PageInfo, PageResponse
from metiquo.contracts import BacktestSummary, ContractMetadata, ModelSummary
from metiquo.contracts.enums import BacktestKind, DataMode, FreshnessStatus, ModelStatus
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock
from metiquo.repositories.postgres_models import PostgresModelRepository

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


def _meta(clock: Clock) -> ContractMetadata:
    now = clock.now().value
    return ContractMetadata(
        data_mode=DataMode.REAL,
        freshness=FreshnessStatus.FRESH,
        as_of=now,
        computed_at=now,
        app_version=version("metiquo"),
    )


def _page[T](values: Sequence[T], offset: int, limit: int, clock: Clock) -> PageResponse[T]:
    return PageResponse[T](
        data=tuple(values[offset : offset + limit]),
        page=PageInfo(offset=offset, limit=limit, total=len(values)),
        meta=_meta(clock),
    )


def build_real_model_router(repository: PostgresModelRepository, clock: Clock) -> APIRouter:
    """Exposer les mêmes DTO modèle/backtest que le catalogue mock."""

    router = APIRouter(prefix="/api/v1", tags=["real-models"])

    @router.get("/models", response_model=PageResponse[ModelSummary])
    def list_models(
        offset: Offset = 0,
        limit: Limit = 20,
        status: ModelStatus | None = None,
    ) -> PageResponse[ModelSummary]:
        values = tuple(
            item for item in repository.list_models() if status is None or item.status is status
        )
        return _page(values, offset, limit, clock)

    @router.get("/models/{model_version_id}", response_model=ItemResponse[ModelSummary])
    def get_model(model_version_id: UUID) -> ItemResponse[ModelSummary]:
        value = repository.get_model(model_version_id)
        if value is None:
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                "Modèle introuvable",
                context={"id": str(model_version_id)},
            )
        return ItemResponse(data=value, meta=_meta(clock))

    @router.get("/backtests", response_model=PageResponse[BacktestSummary])
    def list_backtests(
        offset: Offset = 0,
        limit: Limit = 20,
        kind: BacktestKind | None = None,
    ) -> PageResponse[BacktestSummary]:
        values = tuple(
            item for item in repository.list_backtests() if kind is None or item.kind is kind
        )
        return _page(values, offset, limit, clock)

    @router.get("/backtests/{backtest_id}", response_model=ItemResponse[BacktestSummary])
    def get_backtest(backtest_id: UUID) -> ItemResponse[BacktestSummary]:
        value = repository.get_backtest(backtest_id)
        if value is None:
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                "Backtest introuvable",
                context={"id": str(backtest_id)},
            )
        return ItemResponse(data=value, meta=_meta(clock))

    return router
