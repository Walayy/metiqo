"""Routes de santé et synchronisation branchées sur la persistance réelle."""

from __future__ import annotations

from collections.abc import Sequence
from importlib.metadata import version
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from metiquo.api.dto import (
    CapabilityEvaluationDto,
    CreateAliasRequest,
    ItemResponse,
    MappingDecisionRequest,
    ModelDecisionRequest,
    PageInfo,
    PageResponse,
    TrainModelRequest,
)
from metiquo.canonical.capabilities import CapabilityRegistry, CapabilityState
from metiquo.contracts import (
    AliasRecord,
    AuditEntry,
    ContractMetadata,
    DataQualityIssue,
    IngestionRunSummary,
    JobSummary,
    MappingReview,
    ModelSummary,
    ProviderHealth,
)
from metiquo.contracts.enums import (
    DataMode,
    FreshnessStatus,
    MappingReviewStatus,
    ProviderStatus,
)
from metiquo.foundation.audit import mutation_actor
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock
from metiquo.repositories.postgres_admin import PostgresAdminRepository
from metiquo.repositories.postgres_mapping import PostgresMappingRepository
from metiquo.repositories.postgres_models import PostgresModelRepository
from metiquo.repositories.postgres_operations import PostgresOperationsRepository
from metiquo.services.real_admin import RealAdminMutationService
from metiquo.services.real_mapping import RealMappingMutationService

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]


def _freshness(repository: PostgresAdminRepository) -> FreshnessStatus:
    values = tuple(
        source.freshness
        or {
            ProviderStatus.OPERATIONAL: FreshnessStatus.FRESH,
            ProviderStatus.DEGRADED: FreshnessStatus.DEGRADED,
            ProviderStatus.UNAVAILABLE: FreshnessStatus.FAILED,
            ProviderStatus.DISABLED: FreshnessStatus.FAILED,
        }[source.status]
        for source in repository.list_data_sources()
    )
    for state in (
        FreshnessStatus.FAILED,
        FreshnessStatus.QUARANTINED,
        FreshnessStatus.DEGRADED,
        FreshnessStatus.STALE,
        FreshnessStatus.FRESH,
    ):
        if state in values:
            return state
    return FreshnessStatus.FAILED


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
    mapping_repository: PostgresMappingRepository,
    mapping_mutation_service: RealMappingMutationService,
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
        page = repository.ingestion_runs_page(offset=offset, limit=limit, status=status)
        return PageResponse(
            data=page.items,
            page=PageInfo(offset=offset, limit=limit, total=page.total),
            meta=_meta(repository, clock),
        )

    @router.get("/quality-issues", response_model=PageResponse[DataQualityIssue])
    def list_quality_issues(
        offset: Offset = 0,
        limit: Limit = 20,
        severity: Literal["warning", "blocking"] | None = None,
        status: Literal["open", "quarantined"] | None = None,
    ) -> PageResponse[DataQualityIssue]:
        page = repository.quality_issues_page(
            offset=offset, limit=limit, severity=severity, status=status
        )
        return PageResponse(
            data=page.items,
            page=PageInfo(offset=offset, limit=limit, total=page.total),
            meta=_meta(repository, clock),
        )

    @router.get("/jobs", response_model=PageResponse[JobSummary])
    def list_jobs(
        offset: Offset = 0,
        limit: Limit = 20,
        status: Literal["idle", "queued", "succeeded", "failed", "running", "cancelled", "dead"]
        | None = None,
    ) -> PageResponse[JobSummary]:
        page = PostgresOperationsRepository(repository.engine).jobs(
            offset=offset, limit=limit, status=status
        )
        return PageResponse[JobSummary](
            data=page.items,
            page=PageInfo(offset=offset, limit=limit, total=page.total),
            meta=_meta(repository, clock),
        )

    @router.get("/jobs/{job_id}", response_model=ItemResponse[JobSummary])
    def get_job(job_id: UUID) -> ItemResponse[JobSummary]:
        job = PostgresOperationsRepository(repository.engine).job(job_id)
        if job is None:
            raise BusinessError(ErrorCode.NOT_FOUND, "Job introuvable")
        return ItemResponse(data=job, meta=_meta(repository, clock))

    @router.get("/audit-log", response_model=PageResponse[AuditEntry])
    def list_audit(offset: Offset = 0, limit: Limit = 20) -> PageResponse[AuditEntry]:
        page = PostgresOperationsRepository(repository.engine).audits(offset=offset, limit=limit)
        return PageResponse[AuditEntry](
            data=page.items,
            page=PageInfo(offset=offset, limit=limit, total=page.total),
            meta=_meta(repository, clock),
        )

    @router.get("/mappings/pending", response_model=PageResponse[MappingReview])
    def list_pending_mappings(
        offset: Offset = 0,
        limit: Limit = 20,
    ) -> PageResponse[MappingReview]:
        page = mapping_repository.pending_page(offset=offset, limit=limit)
        return PageResponse(
            data=page.items,
            page=PageInfo(offset=offset, limit=limit, total=page.total),
            meta=_meta(repository, clock),
        )

    def mapping_decision(
        mapping_review_id: UUID,
        request: MappingDecisionRequest,
        idempotency_key: str,
        status: MappingReviewStatus,
    ) -> ItemResponse[MappingReview]:
        return ItemResponse(
            data=mapping_mutation_service.decide_mapping(
                idempotency_key,
                mapping_review_id,
                status,
                mutation_actor(request.reviewer),
                request.reason,
                request.candidate_event_id,
            ),
            meta=_meta(repository, clock),
        )

    @router.post(
        "/mappings/{mapping_review_id}/approve",
        response_model=ItemResponse[MappingReview],
    )
    def approve_mapping(
        mapping_review_id: UUID,
        request: MappingDecisionRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[MappingReview]:
        return mapping_decision(
            mapping_review_id,
            request,
            idempotency_key,
            MappingReviewStatus.APPROVED,
        )

    @router.post(
        "/mappings/{mapping_review_id}/reject",
        response_model=ItemResponse[MappingReview],
    )
    def reject_mapping(
        mapping_review_id: UUID,
        request: MappingDecisionRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[MappingReview]:
        return mapping_decision(
            mapping_review_id,
            request,
            idempotency_key,
            MappingReviewStatus.REJECTED,
        )

    @router.post("/aliases", response_model=ItemResponse[AliasRecord])
    def create_alias(
        request: CreateAliasRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[AliasRecord]:
        return ItemResponse(
            data=mapping_mutation_service.create_alias(
                idempotency_key,
                request.provider,
                request.alias,
                request.canonical_id,
                request.entity_type,
                mutation_actor(request.reviewer),
                request.reason,
            ),
            meta=_meta(repository, clock),
        )

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
        responses={
            202: {"model": ItemResponse[JobSummary], "description": "Synchronisation en file"}
        },
    )
    def sync(
        idempotency_key: IdempotencyKey,
        year: Annotated[int | None, Query(ge=2014, le=2200)] = None,
    ) -> ItemResponse[IngestionRunSummary] | JSONResponse:
        result = mutation_service.sync(idempotency_key, year)
        if isinstance(result, JobSummary):
            return JSONResponse(
                status_code=202,
                content=ItemResponse(data=result, meta=_meta(repository, clock)).model_dump(
                    mode="json",
                    by_alias=True,
                ),
            )
        return ItemResponse(
            data=result,
            meta=_meta(repository, clock),
        )

    @router.post(
        "/models/train",
        response_model=ItemResponse[ModelSummary],
        responses={202: {"model": ItemResponse[JobSummary], "description": "Entraînement en file"}},
    )
    def train(
        request: TrainModelRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[ModelSummary] | JSONResponse:
        result = mutation_service.train(idempotency_key, request.game_title, request.market_type)
        if isinstance(result, JobSummary):
            return JSONResponse(
                status_code=202,
                content=ItemResponse(data=result, meta=_meta(repository, clock)).model_dump(
                    mode="json",
                    by_alias=True,
                ),
            )
        return ItemResponse(data=result, meta=_meta(repository, clock))

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
