"""Commandes paper réelles et lecture des rapports matérialisés."""

import json
from datetime import timedelta
from importlib.metadata import version
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from sqlalchemy import Engine

from metiquo.api.dto import (
    CreatePaperBetRequest,
    ItemResponse,
    PageInfo,
    PageResponse,
    PaperMetricsDto,
    SettlePaperBetRequest,
)
from metiquo.api.mutation_routes import IdempotencyKey
from metiquo.config import Settings
from metiquo.contracts import ContractMetadata, PaperBet
from metiquo.contracts.enums import DataMode, FreshnessStatus, PaperBetStatus
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock
from metiquo.paper.creation import PaperBankrollPolicy, PostgresPaperService
from metiquo.paper.metrics import FINANCIAL_METHOD_VERSION
from metiquo.paper.reporting import PostgresFinancialReportingService
from metiquo.paper.settlement_job import PostgresPaperSettlementService
from metiquo.repositories.postgres_paper import PostgresPaperRepository


def _meta(clock: Clock, mode: DataMode) -> ContractMetadata:
    now = clock.now().value
    return ContractMetadata(
        data_mode=mode,
        freshness=FreshnessStatus.FRESH,
        as_of=now,
        computed_at=now,
        app_version=version("metiquo"),
    )


def build_paper_metrics_router(
    service: PostgresFinancialReportingService | None, clock: Clock
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["paper-reports"])
    mode = DataMode.REAL if service is not None else DataMode.MOCK

    @router.get("/paper-bets/metrics", response_model=ItemResponse[PaperMetricsDto])
    def metrics(
        currency: Annotated[str, Query(pattern=r"^[A-Z]{3}$")] = "EUR",
    ) -> ItemResponse[PaperMetricsDto]:
        report = service.latest(currency=currency) if service else None
        if report is None:
            dto = PaperMetricsDto(currency=currency, method_version=FINANCIAL_METHOD_VERSION)
        else:
            document = report.document
            payload = {
                key: document[key]
                for key in ("signals", "bets", "settled", "open", "pendingReview", "estimates")
            }
            payload.update(
                reportId=str(report.report_id),
                currency=currency,
                computedAt=report.computed_at.isoformat(),
                methodVersion=FINANCIAL_METHOD_VERSION,
                reportFingerprint=report.report_fingerprint,
            )
            dto = PaperMetricsDto.model_validate_json(json.dumps(payload))
        meta = _meta(clock, mode)
        if report is None:
            meta = meta.model_copy(update={"freshness": FreshnessStatus.STALE})
        else:
            meta = meta.model_copy(
                update={
                    "computed_at": report.computed_at,
                    "as_of": report.computed_at,
                    "freshness": FreshnessStatus.STALE
                    if (clock.now().value - report.computed_at).total_seconds() > 300
                    else FreshnessStatus.FRESH,
                }
            )
        return ItemResponse(data=dto, meta=meta)

    @router.get("/paper-reports/{report_id}", response_class=Response)
    def download_report(report_id: UUID) -> Response:
        report = service.get(report_id) if service else None
        if report is None:
            raise BusinessError(ErrorCode.NOT_FOUND, "Rapport introuvable")
        return Response(
            json.dumps(
                {
                    "reportId": str(report.report_id),
                    "computedAt": report.computed_at.isoformat(),
                    "reportFingerprint": report.report_fingerprint,
                    "inputEvidence": report.input_evidence,
                    "document": report.document,
                }
            ),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="paper-report-{report_id}.json"'
            },
        )

    return router


def build_real_paper_router(engine: Engine, settings: Settings, clock: Clock) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["real-paper"])
    repository = PostgresPaperRepository(
        engine, clock, closing_max_age_seconds=settings.paper_closing_max_age_seconds
    )
    creation = PostgresPaperService(
        engine,
        bankroll=PaperBankrollPolicy(
            settings.paper_bankroll_policy_version,
            settings.paper_bankroll_currency,
            settings.paper_bankroll_initial,
            settings.paper_max_open_exposure,
        ),
        source_sla=timedelta(seconds=settings.oe_freshness_sla_seconds),
        clock=clock,
    )
    settlement = PostgresPaperSettlementService(
        engine,
        source_sla=timedelta(seconds=settings.oe_freshness_sla_seconds),
        settlement_delay=timedelta(seconds=settings.paper_settlement_delay_seconds),
        clock=clock,
    )

    @router.get("/paper-bets", response_model=PageResponse[PaperBet])
    def list_bets(
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        status: PaperBetStatus | None = None,
    ) -> PageResponse[PaperBet]:
        rows, total = repository.page(offset=offset, limit=limit, status=status)
        return PageResponse(
            data=rows,
            page=PageInfo(offset=offset, limit=limit, total=total),
            meta=_meta(clock, DataMode.REAL),
        )

    @router.get("/paper-bets/{paper_bet_id}", response_model=ItemResponse[PaperBet])
    def get_bet(paper_bet_id: UUID) -> ItemResponse[PaperBet]:
        bet = repository.get(paper_bet_id)
        if bet is None:
            raise BusinessError(ErrorCode.NOT_FOUND, "Paper bet introuvable")
        return ItemResponse(data=bet, meta=_meta(clock, DataMode.REAL))

    @router.post("/paper-bets", response_model=ItemResponse[PaperBet])
    def create_bet(
        request: CreatePaperBetRequest, idempotency_key: IdempotencyKey
    ) -> ItemResponse[PaperBet]:
        bet = creation.create(
            idempotency_key,
            request.signal_id,
            request.stake_amount,
            request.currency,
            actor=request.actor,
        )
        return ItemResponse(data=bet, meta=_meta(clock, DataMode.REAL))

    @router.post("/admin/paper-bets/settle", response_model=ItemResponse[PaperBet])
    def settle_bet(
        request: SettlePaperBetRequest, idempotency_key: IdempotencyKey
    ) -> ItemResponse[PaperBet]:
        if request.status is not None or request.profit_loss is not None:
            raise BusinessError(
                ErrorCode.INVALID_INPUT, "Le résultat réel est dérivé des preuves OE"
            )
        bet = settlement.settle(
            request.paper_bet_id,
            key=idempotency_key,
            actor=request.actor,
            correction_reason=request.correction_reason,
            request_reason=request.reason,
        )
        return ItemResponse(data=bet, meta=_meta(clock, DataMode.REAL))

    return router
