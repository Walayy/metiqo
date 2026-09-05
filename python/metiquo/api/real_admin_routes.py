"""Routes de santé et synchronisation branchées sur la persistance réelle."""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import version
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query

from metiquo.api.dto import (
    CapabilityEvaluationDto,
    ItemResponse,
    ModelDecisionRequest,
    PageInfo,
    PageResponse,
    TrainModelRequest,
)
from metiquo.canonical.capabilities import CapabilityRegistry, CapabilityState
from metiquo.contracts import (
    AuditEntry,
    ContractMetadata,
    DataQualityIssue,
    IngestionRunSummary,
    JobSummary,
    ModelSummary,
    ProviderHealth,
)
from metiquo.contracts.enums import DataMode, FreshnessStatus, ProviderStatus
from metiquo.foundation.time import Clock
from metiquo.repositories.postgres_admin import PostgresAdminRepository
from metiquo.repositories.postgres_models import PostgresModelRepository
from metiquo.services.real_admin import RealAdminMutationService

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]


def _freshness(repository: PostgresAdminRepository) -> FreshnessStatus:
    status = repository.list_data_sources()[0].status
    return {
        ProviderStatus.OPERATIONAL: FreshnessStatus.FRESH,
        ProviderStatus.DEGRADED: FreshnessStatus.DEGRADED,
        ProviderStatus.UNAVAILABLE: FreshnessStatus.FAILED,
        ProviderStatus.DISABLED: FreshnessStatus.FAILED,
    }[status]


def _meta(repository: PostgresAdminRepository, clock: Clock) -> ContractMetadata:
    now = clock.now().value
    return ContractMetadata(
        data_mode=DataMode.REAL,
        freshness=_freshness(repository),
        as_of=now,
        computed_at=now,
        app_version=version("metiquo"),
    )


def _page[T](
    values: Sequence[T],
    offset: int,
    limit: int,
    repository: PostgresAdminRepository,
    clock: Clock,
) -> PageResponse[T]:
    return PageResponse[T](
        data=tuple(values[offset : offset + limit]),
        page=PageInfo(offset=offset, limit=limit, total=len(values)),
        meta=_meta(repository, clock),
    )


def build_real_admin_router(
    repository: PostgresAdminRepository,
    mutation_service: RealAdminMutationService,
    clock: Clock,
    capability_registry: CapabilityRegistry,
    model_repository: PostgresModelRepository,
) -> APIRouter:
    """Exposer exactement les DTO d'administration partagés avec le mode mock."""

    router = APIRouter(prefix="/api/v1/admin", tags=["real-data-admin"])

    @router.get("/data-sources", response_model=PageResponse[ProviderHealth])
    def list_data_sources(offset: Offset = 0, limit: Limit = 20) -> PageResponse[ProviderHealth]:
        return _page(repository.list_data_sources(), offset, limit, repository, clock)

    @router.get("/ingestion-runs", response_model=PageResponse[IngestionRunSummary])
    def list_ingestion_runs(
        offset: Offset = 0,
        limit: Limit = 20,
        status: Literal["succeeded", "failed"] | None = None,
    ) -> PageResponse[IngestionRunSummary]:
        values = tuple(
            item
            for item in repository.list_ingestion_runs()
            if status is None or item.status == status
        )
        return _page(values, offset, limit, repository, clock)

    @router.get("/quality-issues", response_model=PageResponse[DataQualityIssue])
    def list_quality_issues(
        offset: Offset = 0,
        limit: Limit = 20,
        severity: Literal["warning", "blocking"] | None = None,
        status: Literal["open", "quarantined"] | None = None,
    ) -> PageResponse[DataQualityIssue]:
        values = tuple(
            item
            for item in repository.list_quality_issues()
            if (severity is None or item.severity == severity)
            and (status is None or item.status == status)
        )
        return _page(values, offset, limit, repository, clock)

    @router.get("/jobs", response_model=PageResponse[JobSummary])
    def list_jobs(
        offset: Offset = 0,
        limit: Limit = 20,
        status: Literal["idle", "succeeded", "failed", "running"] | None = None,
    ) -> PageResponse[JobSummary]:
        values = tuple(
            item
            for item in (*model_repository.list_jobs(), *repository.list_jobs())
            if status is None or item.status == status
        )
        return _page(values, offset, limit, repository, clock)

    @router.get("/audit-log", response_model=PageResponse[AuditEntry])
    def list_audit(offset: Offset = 0, limit: Limit = 20) -> PageResponse[AuditEntry]:
        return _page(model_repository.list_audit(), offset, limit, repository, clock)

    @router.get(
        "/capabilities",
        response_model=PageResponse[CapabilityEvaluationDto],
    )
    def list_capabilities(
        offset: Offset = 0,
        limit: Limit = 20,
        snapshot_id: Annotated[UUID | None, Query(alias="snapshotId")] = None,
    ) -> PageResponse[CapabilityEvaluationDto]:
        values = tuple(
            _capability_dto(item)
            for item in capability_registry.list_latest(snapshot_id=snapshot_id)
        )
        return _page(values, offset, limit, repository, clock)

    @router.post(
        "/oracles-elixir/sync",
        response_model=ItemResponse[IngestionRunSummary],
    )
    def sync(
        idempotency_key: IdempotencyKey,
        year: Annotated[int | None, Query(ge=2014, le=2200)] = None,
    ) -> ItemResponse[IngestionRunSummary]:
        return ItemResponse(
            data=mutation_service.sync(idempotency_key, year),
            meta=_meta(repository, clock),
        )

    @router.post("/models/train", response_model=ItemResponse[ModelSummary])
    def train(
        request: TrainModelRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[ModelSummary]:
        return ItemResponse(
            data=mutation_service.train(
                idempotency_key,
                request.game_title,
                request.market_type,
            ),
            meta=_meta(repository, clock),
        )

    @router.post(
        "/models/{model_version_id}/promote",
        response_model=ItemResponse[ModelSummary],
    )
    def promote(
        model_version_id: UUID,
        request: ModelDecisionRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[ModelSummary]:
        return ItemResponse(
            data=mutation_service.promote(
                idempotency_key,
                model_version_id,
                request.reason,
            ),
            meta=_meta(repository, clock),
        )

    @router.post(
        "/models/{model_version_id}/retire",
        response_model=ItemResponse[ModelSummary],
    )
    def retire(
        model_version_id: UUID,
        request: ModelDecisionRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[ModelSummary]:
        return ItemResponse(
            data=mutation_service.retire(
                idempotency_key,
                model_version_id,
                request.reason,
            ),
            meta=_meta(repository, clock),
        )

    return router


def _capability_dto(state: CapabilityState) -> CapabilityEvaluationDto:
    return CapabilityEvaluationDto(
        snapshot_id=state.snapshot_id,
        capability=state.capability,
        kind=state.capability_kind,
        status=state.status,
        reason_codes=state.reason_codes,
        threshold_version=state.threshold_version,
        evaluation_revision=state.evaluation_revision,
        required_columns=state.required_columns,
        observed_columns=state.observed_columns,
        minimum_completeness=state.minimum_completeness,
        observed_completeness=state.observed_completeness,
        minimum_sample_size=state.minimum_sample_size,
        observed_sample_size=state.observed_sample_size,
        gates=dict(state.gates),
        evaluated_at=state.evaluated_at,
    )
