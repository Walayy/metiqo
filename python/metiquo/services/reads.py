"""Orchestration des lectures métier, identique en mode mock et réel."""

from dataclasses import dataclass
from uuid import UUID

from metiquo.contracts import (
    Event,
    MappingReview,
    Market,
    ModelSummary,
    OddsSnapshot,
    Opportunity,
    PaperBet,
)
from metiquo.contracts.odds_provider import ProviderHealth
from metiquo.repositories.contracts import (
    DataHealthRepository,
    EventRepository,
    MappingRepository,
    ModelRepository,
    OpportunityRepository,
    PaperRepository,
)


@dataclass(frozen=True, slots=True)
class ReadService:
    """Façade consommée par l'API sans connaître fixtures, SQL ou provider."""

    opportunities: OpportunityRepository
    events: EventRepository
    models: ModelRepository
    paper: PaperRepository
    data_health: DataHealthRepository
    mappings: MappingRepository

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

    def list_paper_bets(self) -> tuple[PaperBet, ...]:
        return self.paper.list()

    def get_paper_bet(self, paper_bet_id: UUID) -> PaperBet | None:
        return self.paper.get(paper_bet_id)

    def list_data_sources(self) -> tuple[ProviderHealth, ...]:
        return self.data_health.list()

    def list_pending_mappings(self) -> tuple[MappingReview, ...]:
        return self.mappings.list_pending()
