"""Routes de lecture métier alimentées exclusivement par les services."""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from importlib.metadata import version
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Query

from metiquo.api.dto import (
    CapabilityEvaluationDto,
    ItemResponse,
    OpportunityExplanation,
    PageInfo,
    PageResponse,
)
from metiquo.contracts import (
    BacktestSummary,
    ContractMetadata,
    DataQualityIssue,
    Event,
    IngestionRunSummary,
    JobSummary,
    MappingReview,
    Market,
    ModelSummary,
    OddsSnapshot,
    Opportunity,
    PaperBet,
    ProviderHealth,
)
from metiquo.contracts.enums import (
    BacktestKind,
    DataMode,
    EventStatus,
    FreshnessStatus,
    MarketType,
    ModelStatus,
    PaperBetStatus,
    ValueGrade,
)
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock
from metiquo.services import ReadService

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


def _meta(clock: Clock, freshness: FreshnessStatus = FreshnessStatus.FRESH) -> ContractMetadata:
    now = clock.now().value
    return ContractMetadata(
        data_mode=DataMode.MOCK,
        freshness=freshness,
        as_of=now,
        computed_at=now,
        app_version=version("metiquo"),
    )


def _page[T](
    values: Sequence[T],
    offset: int,
    limit: int,
    clock: Clock,
    freshness: FreshnessStatus = FreshnessStatus.FRESH,
) -> PageResponse[T]:
    return PageResponse[T](
        data=tuple(values[offset : offset + limit]),
        page=PageInfo(offset=offset, limit=limit, total=len(values)),
        meta=_meta(clock, freshness),
    )


def _item[T](value: T, clock: Clock) -> ItemResponse[T]:
    return ItemResponse[T](data=value, meta=_meta(clock))


def _required[T](value: T | None, resource: str, identifier: UUID) -> T:
    if value is None:
        raise BusinessError(
            ErrorCode.NOT_FOUND,
            f"{resource} introuvable",
            context={"id": str(identifier)},
        )
    return value


def _matches_text(value: str, query: str | None) -> bool:
    return query is None or query.casefold() in value.casefold()


def _validate_period(starts_from: datetime | None, starts_to: datetime | None) -> None:
    for name, value in (("startsFrom", starts_from), ("startsTo", starts_to)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise BusinessError(
                ErrorCode.INVALID_INPUT,
                f"{name} doit inclure un fuseau horaire",
            )
    if starts_from is not None and starts_to is not None and starts_to < starts_from:
        raise BusinessError(
            ErrorCode.INVALID_INPUT,
            "startsTo doit être postérieur ou égal à startsFrom",
        )


def build_read_router(service: ReadService, clock: Clock) -> APIRouter:
    """Construire les endpoints sans dépendre de l'implémentation des repositories."""

    router = APIRouter(prefix="/api/v1", tags=["reads"])

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
        min_confidence: Annotated[Decimal | None, Query(alias="minConfidence", ge=0, le=1)] = None,
        freshness: FreshnessStatus | None = None,
        starts_from: Annotated[datetime | None, Query(alias="startsFrom")] = None,
        starts_to: Annotated[datetime | None, Query(alias="startsTo")] = None,
    ) -> PageResponse[Opportunity]:
        _validate_period(starts_from, starts_to)
        items = tuple(
            item
            for item in service.list_opportunities()
            if _matches_text(item.event.competition, competition)
            and (
                team is None
                or _matches_text(item.event.team_a, team)
                or _matches_text(item.event.team_b, team)
            )
            and (market is None or item.market.type is market)
            and (grade is None or item.value.grade is grade)
            and (min_edge is None or item.value.edge >= min_edge)
            and (min_ev is None or item.value.expected_value >= min_ev)
            and (min_confidence is None or item.model.confidence >= min_confidence)
            and (freshness is None or item.meta.freshness is freshness)
            and (starts_from is None or item.event.starts_at >= starts_from)
            and (starts_to is None or item.event.starts_at <= starts_to)
        )
        return _page(items, offset, limit, clock)

    @router.get("/opportunities/{signal_id}", response_model=ItemResponse[Opportunity])
    def get_opportunity(signal_id: UUID) -> ItemResponse[Opportunity]:
        return _item(_required(service.get_opportunity(signal_id), "Opportunité", signal_id), clock)

    @router.get(
        "/opportunities/{signal_id}/explanation",
        response_model=ItemResponse[OpportunityExplanation],
    )
    def get_opportunity_explanation(
        signal_id: UUID,
    ) -> ItemResponse[OpportunityExplanation]:
        opportunity = _required(service.get_opportunity(signal_id), "Opportunité", signal_id)
        reasons = tuple(reason.value for reason in opportunity.quality.abstention_reasons)
        if not reasons:
            reasons = ("Décision publiable selon les seuils mock actifs",)
        explanation = OpportunityExplanation(
            signal_id=opportunity.signal_id,
            reference=opportunity.explanation_reference or "mock-v1:unavailable",
            publishable=opportunity.quality.publishable,
            reasons=reasons,
        )
        return _item(explanation, clock)

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
        items = tuple(
            item
            for item in service.list_events()
            if _matches_text(item.competition, competition)
            and (
                team is None or _matches_text(item.team_a, team) or _matches_text(item.team_b, team)
            )
            and (status is None or item.status is status)
            and (starts_from is None or item.starts_at >= starts_from)
            and (starts_to is None or item.starts_at <= starts_to)
        )
        return _page(items, offset, limit, clock)

    @router.get("/events/{event_id}", response_model=ItemResponse[Event])
    def get_event(event_id: UUID) -> ItemResponse[Event]:
        return _item(_required(service.get_event(event_id), "Événement", event_id), clock)

    @router.get("/events/{event_id}/markets", response_model=PageResponse[Market])
    def list_event_markets(
        event_id: UUID, offset: Offset = 0, limit: Limit = 20
    ) -> PageResponse[Market]:
        _required(service.get_event(event_id), "Événement", event_id)
        return _page(service.list_event_markets(event_id), offset, limit, clock)

    @router.get("/events/{event_id}/odds-history", response_model=PageResponse[OddsSnapshot])
    def get_odds_history(
        event_id: UUID, offset: Offset = 0, limit: Limit = 20
    ) -> PageResponse[OddsSnapshot]:
        _required(service.get_event(event_id), "Événement", event_id)
        return _page(service.get_odds_history(event_id), offset, limit, clock)

    @router.get("/models", response_model=PageResponse[ModelSummary])
    def list_models(
        offset: Offset = 0,
        limit: Limit = 20,
        status: ModelStatus | None = None,
    ) -> PageResponse[ModelSummary]:
        items = tuple(
            model for model in service.list_models() if status is None or model.status is status
        )
        return _page(items, offset, limit, clock)

    @router.get("/backtests", response_model=PageResponse[BacktestSummary])
    def list_backtests(
        offset: Offset = 0,
        limit: Limit = 20,
        kind: BacktestKind | None = None,
    ) -> PageResponse[BacktestSummary]:
        items = tuple(
            backtest
            for backtest in service.list_backtests()
            if kind is None or backtest.kind is kind
        )
        return _page(items, offset, limit, clock)

    @router.get("/paper-bets", response_model=PageResponse[PaperBet])
    def list_paper_bets(
        offset: Offset = 0,
        limit: Limit = 20,
        status: PaperBetStatus | None = None,
    ) -> PageResponse[PaperBet]:
        items = tuple(
            paper_bet
            for paper_bet in service.list_paper_bets()
            if status is None or paper_bet.status is status
        )
        return _page(items, offset, limit, clock)

    @router.get("/admin/data-sources", response_model=PageResponse[ProviderHealth])
    def list_data_sources(offset: Offset = 0, limit: Limit = 20) -> PageResponse[ProviderHealth]:
        return _page(
            service.list_data_sources(),
            offset,
            limit,
            clock,
            freshness=FreshnessStatus.DEGRADED,
        )

    @router.get("/admin/ingestion-runs", response_model=PageResponse[IngestionRunSummary])
    def list_ingestion_runs(
        offset: Offset = 0,
        limit: Limit = 20,
        status: Literal["succeeded", "failed"] | None = None,
    ) -> PageResponse[IngestionRunSummary]:
        items = tuple(
            run for run in service.list_ingestion_runs() if status is None or run.status == status
        )
        return _page(items, offset, limit, clock)

    @router.get("/admin/quality-issues", response_model=PageResponse[DataQualityIssue])
    def list_quality_issues(
        offset: Offset = 0,
        limit: Limit = 20,
        severity: Literal["warning", "blocking"] | None = None,
        status: Literal["open", "quarantined"] | None = None,
    ) -> PageResponse[DataQualityIssue]:
        items = tuple(
            issue
            for issue in service.list_quality_issues()
            if (severity is None or issue.severity == severity)
            and (status is None or issue.status == status)
        )
        return _page(items, offset, limit, clock)

    @router.get("/admin/jobs", response_model=PageResponse[JobSummary])
    def list_jobs(
        offset: Offset = 0,
        limit: Limit = 20,
        status: Literal["idle", "succeeded", "failed", "running"] | None = None,
    ) -> PageResponse[JobSummary]:
        items = tuple(job for job in service.list_jobs() if status is None or job.status == status)
        return _page(items, offset, limit, clock)

    @router.get(
        "/admin/capabilities",
        response_model=PageResponse[CapabilityEvaluationDto],
    )
    def list_capabilities(
        offset: Offset = 0,
        limit: Limit = 20,
    ) -> PageResponse[CapabilityEvaluationDto]:
        now = clock.now().value
        snapshot_id = uuid5(NAMESPACE_URL, "metiquo:mock:capability-snapshot")
        values = (
            CapabilityEvaluationDto(
                snapshot_id=snapshot_id,
                capability="label.match_winner",
                kind="label",
                status="enabled",
                reason_codes=(),
                threshold_version="lol-capability-thresholds-v1",
                evaluation_revision=1,
                required_columns=("datacompleteness", "result"),
                observed_columns=("datacompleteness", "result"),
                minimum_completeness=Decimal("0.9500"),
                observed_completeness=Decimal("1.0000"),
                minimum_sample_size=1,
                observed_sample_size=12,
                gates={"data": True, "sample": True},
                evaluated_at=now,
            ),
            CapabilityEvaluationDto(
                snapshot_id=snapshot_id,
                capability="market.match_winner",
                kind="market",
                status="pending",
                reason_codes=("GATE_MODEL_PENDING", "GATE_ODDS_PENDING"),
                threshold_version="lol-capability-thresholds-v1",
                evaluation_revision=1,
                required_columns=("datacompleteness", "result"),
                observed_columns=("datacompleteness", "result"),
                minimum_completeness=Decimal("0.9500"),
                observed_completeness=Decimal("1.0000"),
                minimum_sample_size=1,
                observed_sample_size=12,
                gates={
                    "label": True,
                    "data": True,
                    "rules": True,
                    "model": None,
                    "calibration": None,
                    "mapping": True,
                    "odds": None,
                    "sample": True,
                },
                evaluated_at=now,
            ),
        )
        return _page(values, offset, limit, clock)

    @router.get("/admin/mappings/pending", response_model=PageResponse[MappingReview])
    def list_pending_mappings(offset: Offset = 0, limit: Limit = 20) -> PageResponse[MappingReview]:
        return _page(service.list_pending_mappings(), offset, limit, clock)

    @router.get("/models/{model_version_id}", response_model=ItemResponse[ModelSummary])
    def get_model(model_version_id: UUID) -> ItemResponse[ModelSummary]:
        return _item(
            _required(service.get_model(model_version_id), "Modèle", model_version_id), clock
        )

    @router.get("/backtests/{backtest_id}", response_model=ItemResponse[BacktestSummary])
    def get_backtest(backtest_id: UUID) -> ItemResponse[BacktestSummary]:
        return _item(_required(service.get_backtest(backtest_id), "Backtest", backtest_id), clock)

    @router.get("/paper-bets/{paper_bet_id}", response_model=ItemResponse[PaperBet])
    def get_paper_bet(paper_bet_id: UUID) -> ItemResponse[PaperBet]:
        return _item(
            _required(service.get_paper_bet(paper_bet_id), "Paper bet", paper_bet_id), clock
        )

    return router
