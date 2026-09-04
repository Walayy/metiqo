"""Ports de lecture partagés par les implémentations mock et réelles."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from metiquo.contracts import (
    BacktestSummary,
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
)
from metiquo.contracts.enums import GameTitle
from metiquo.contracts.odds_provider import (
    OddsCaptureResult,
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
)


class OpportunityRepository(Protocol):
    def list(self) -> tuple[Opportunity, ...]: ...

    def get(self, signal_id: UUID) -> Opportunity | None: ...


class EventRepository(Protocol):
    def list(self) -> tuple[Event, ...]: ...

    def get(self, event_id: UUID) -> Event | None: ...

    def list_markets(self, event_id: UUID) -> tuple[Market, ...]: ...

    def odds_history(self, event_id: UUID) -> tuple[OddsSnapshot, ...]: ...


class ModelRepository(Protocol):
    def list(self) -> tuple[ModelSummary, ...]: ...

    def get(self, model_version_id: UUID) -> ModelSummary | None: ...

    def list_backtests(self) -> tuple[BacktestSummary, ...]: ...

    def get_backtest(self, backtest_id: UUID) -> BacktestSummary | None: ...


class PaperRepository(Protocol):
    def list(self) -> tuple[PaperBet, ...]: ...

    def get(self, paper_bet_id: UUID) -> PaperBet | None: ...


class DataHealthRepository(Protocol):
    def list(self) -> tuple[ProviderHealth, ...]: ...

    def get(self, provider_code: str) -> ProviderHealth | None: ...


class MappingRepository(Protocol):
    def list_pending(self) -> tuple[MappingReview, ...]: ...

    def get(self, mapping_review_id: UUID) -> MappingReview | None: ...


class OperationsRepository(Protocol):
    def list_ingestion_runs(self) -> tuple[IngestionRunSummary, ...]: ...

    def list_quality_issues(self) -> tuple[DataQualityIssue, ...]: ...

    def list_jobs(self) -> tuple[JobSummary, ...]: ...


class OddsProvider(Protocol):
    provider_code: str

    def list_events(
        self,
        starts_from: datetime,
        starts_to: datetime,
        game_title: GameTitle,
    ) -> tuple[ProviderEvent, ...]: ...

    def get_event_markets(self, provider_event_id: str) -> tuple[ProviderMarket, ...]: ...

    def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult: ...

    def health(self) -> ProviderHealth: ...
