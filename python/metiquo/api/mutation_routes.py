"""Routes d'actions mock idempotentes et auditées."""

from importlib.metadata import version
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query

from metiquo.api.dto import (
    CreateAliasRequest,
    CreatePaperBetRequest,
    ItemResponse,
    MappingDecisionRequest,
    ModelDecisionRequest,
    PageInfo,
    PageResponse,
    SettlePaperBetRequest,
    TrainModelRequest,
)
from metiquo.contracts import (
    AliasRecord,
    AuditEntry,
    ContractMetadata,
    IngestionRunSummary,
    MappingReview,
    ModelSummary,
    PaperBet,
)
from metiquo.contracts.enums import DataMode, FreshnessStatus, MappingReviewStatus
from metiquo.foundation.time import Clock
from metiquo.services import MockMutationService

IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]


def _meta(clock: Clock) -> ContractMetadata:
    now = clock.now().value
    return ContractMetadata(
        data_mode=DataMode.MOCK,
        freshness=FreshnessStatus.FRESH,
        as_of=now,
        computed_at=now,
        app_version=version("metiquo"),
    )


def build_mutation_router(service: MockMutationService, clock: Clock) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["mock-actions"])

    @router.post(
        "/admin/oracles-elixir/sync",
        response_model=ItemResponse[IngestionRunSummary],
    )
    def sync(idempotency_key: IdempotencyKey) -> ItemResponse[IngestionRunSummary]:
        return ItemResponse(data=service.sync(idempotency_key), meta=_meta(clock))

    @router.post("/admin/models/train", response_model=ItemResponse[ModelSummary])
    def train(
        request: TrainModelRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[ModelSummary]:
        return ItemResponse(
            data=service.train(idempotency_key, request.game_title, request.market_type),
            meta=_meta(clock),
        )

    @router.post(
        "/admin/models/{model_version_id}/promote",
        response_model=ItemResponse[ModelSummary],
    )
    def promote(
        model_version_id: UUID,
        request: ModelDecisionRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[ModelSummary]:
        return ItemResponse(
            data=service.promote(idempotency_key, model_version_id, request.reason),
            meta=_meta(clock),
        )

    @router.post(
        "/admin/models/{model_version_id}/retire",
        response_model=ItemResponse[ModelSummary],
    )
    def retire(
        model_version_id: UUID,
        request: ModelDecisionRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[ModelSummary]:
        return ItemResponse(
            data=service.retire(idempotency_key, model_version_id, request.reason),
            meta=_meta(clock),
        )

    @router.post("/paper-bets", response_model=ItemResponse[PaperBet])
    def create_paper_bet(
        request: CreatePaperBetRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[PaperBet]:
        return ItemResponse(
            data=service.create_paper_bet(
                idempotency_key,
                request.signal_id,
                request.stake_amount,
                request.currency,
            ),
            meta=_meta(clock),
        )

    @router.post("/admin/paper-bets/settle", response_model=ItemResponse[PaperBet])
    def settle_paper_bet(
        request: SettlePaperBetRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[PaperBet]:
        return ItemResponse(
            data=service.settle_paper_bet(
                idempotency_key,
                request.paper_bet_id,
                request.status,
                request.profit_loss,
                request.reason,
            ),
            meta=_meta(clock),
        )

    def mapping_decision(
        mapping_review_id: UUID,
        request: MappingDecisionRequest,
        idempotency_key: str,
        status: MappingReviewStatus,
    ) -> ItemResponse[MappingReview]:
        return ItemResponse(
            data=service.decide_mapping(
                idempotency_key,
                mapping_review_id,
                status,
                request.reviewer,
                request.reason,
            ),
            meta=_meta(clock),
        )

    @router.post(
        "/admin/mappings/{mapping_review_id}/approve",
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
        "/admin/mappings/{mapping_review_id}/reject",
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

    @router.post("/admin/aliases", response_model=ItemResponse[AliasRecord])
    def create_alias(
        request: CreateAliasRequest,
        idempotency_key: IdempotencyKey,
    ) -> ItemResponse[AliasRecord]:
        return ItemResponse(
            data=service.create_alias(
                idempotency_key,
                request.provider,
                request.alias,
                request.canonical_id,
            ),
            meta=_meta(clock),
        )

    @router.get("/admin/audit-log", response_model=PageResponse[AuditEntry])
    def audit_log(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> PageResponse[AuditEntry]:
        values = service.audit_log()
        return PageResponse(
            data=values[offset : offset + limit],
            page=PageInfo(offset=offset, limit=limit, total=len(values)),
            meta=_meta(clock),
        )

    return router
