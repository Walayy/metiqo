"""Orchestration des lectures métier, identique en mode mock et réel."""

from dataclasses import dataclass
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
from metiquo.contracts.odds_provider import ProviderHealth
from metiquo.mock.scenarios import MockScenarioCatalog
from metiquo.repositories.contracts import (
    DataHealthRepository,
    EventRepository,
    MappingRepository,
    ModelRepository,
    OperationsRepository,
    OpportunityRepository,
    PaperRepository,
)
from metiquo.repositories.mock import build_mock_repository_bundle


@dataclass(frozen=True, slots=True)
class ReadService:
    """Façade consommée par l'API sans connaître fixtures, SQL ou provider."""

    opportunities: OpportunityRepository
    events: EventRepository
    models: ModelRepository
    paper: PaperRepository
    data_health: DataHealthRepository
    mappings: MappingRepository
    operations: OperationsRepository

    def list_opportunities(self) -> tuple[Opportunity, ...]:
        return self.opportunities.list()

    def get_opportunity(self, signal_id: UUID) -> Opportunity | None:
        return self.opportunities.get(signal_id)

    def list_events(self) -> tuple[Event, ...]:
        return self.events.list()

    def get_event(self, event_id: UUID) -> Event | None:
        return self.events.get(event_id)

    def list_event_markets(self, event_id: UUID) -> tuple[Market, ...]:
        return self.events.list_markets(event_id)

    def get_odds_history(self, event_id: UUID) -> tuple[OddsSnapshot, ...]:
        return self.events.odds_history(event_id)

    def list_models(self) -> tuple[ModelSummary, ...]:
        return self.models.list()

    def get_model(self, model_version_id: UUID) -> ModelSummary | None:
        return self.models.get(model_version_id)

    def list_backtests(self) -> tuple[BacktestSummary, ...]:
        return self.models.list_backtests()

    def get_backtest(self, backtest_id: UUID) -> BacktestSummary | None:
        return self.models.get_backtest(backtest_id)

    def list_paper_bets(self) -> tuple[PaperBet, ...]:
        return self.paper.list()

    def get_paper_bet(self, paper_bet_id: UUID) -> PaperBet | None:
        return self.paper.get(paper_bet_id)

    def list_data_sources(self) -> tuple[ProviderHealth, ...]:
        return self.data_health.list()

    def list_pending_mappings(self) -> tuple[MappingReview, ...]:
        return self.mappings.list_pending()

    def list_ingestion_runs(self) -> tuple[IngestionRunSummary, ...]:
        return self.operations.list_ingestion_runs()

    def list_quality_issues(self) -> tuple[DataQualityIssue, ...]:
        return self.operations.list_quality_issues()

    def list_jobs(self) -> tuple[JobSummary, ...]:
        return self.operations.list_jobs()


def build_mock_read_service(catalog: MockScenarioCatalog) -> ReadService:
    """Assembler la façade commune avec les adaptateurs mock."""

    repositories = build_mock_repository_bundle(catalog)
    return ReadService(
        opportunities=repositories.opportunities,
        events=repositories.events,
        models=repositories.models,
        paper=repositories.paper,
        data_health=repositories.data_health,
        mappings=repositories.mappings,
        operations=repositories.operations,
    )
