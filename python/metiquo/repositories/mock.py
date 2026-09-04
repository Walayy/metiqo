"""Repositories mock immuables alimentés par le catalogue normatif."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
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
from metiquo.contracts.enums import DataMode, GameTitle, MappingReviewStatus, ProviderStatus
from metiquo.contracts.odds_provider import (
    OddsCaptureResult,
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
    ProviderSelection,
)
from metiquo.mock.scenarios import MockScenario, MockScenarioCatalog
from metiquo.repositories.boundary import DataModeViolation


def _validate_catalog(catalog: MockScenarioCatalog) -> None:
    if any(
        scenario.opportunity.meta.data_mode is not DataMode.MOCK for scenario in catalog.scenarios
    ):
        raise DataModeViolation("Les repositories mock refusent un catalogue non mock")


def _unique_by_id[T](values: Iterable[T], identifier: Callable[[T], UUID]) -> tuple[T, ...]:
    indexed: dict[UUID, T] = {}
    for value in values:
        indexed[identifier(value)] = value
    return tuple(indexed.values())


@dataclass(frozen=True, slots=True)
class MockOpportunityRepository:
    catalog: MockScenarioCatalog

    def __post_init__(self) -> None:
        _validate_catalog(self.catalog)

    def list(self) -> tuple[Opportunity, ...]:
        return tuple(scenario.opportunity for scenario in self.catalog.scenarios)

    def get(self, signal_id: UUID) -> Opportunity | None:
        return next((item for item in self.list() if item.signal_id == signal_id), None)


@dataclass(frozen=True, slots=True)
class MockEventRepository:
    catalog: MockScenarioCatalog

    def __post_init__(self) -> None:
        _validate_catalog(self.catalog)

    def list(self) -> tuple[Event, ...]:
        return _unique_by_id(
            (scenario.current_event for scenario in self.catalog.scenarios),
            lambda event: event.event_id,
        )

    def get(self, event_id: UUID) -> Event | None:
        return next((event for event in self.list() if event.event_id == event_id), None)

    def list_markets(self, event_id: UUID) -> tuple[Market, ...]:
        return _unique_by_id(
            (
                scenario.current_market
                for scenario in self.catalog.scenarios
                if scenario.current_event.event_id == event_id
            ),
            lambda market: market.market_id,
        )

    def odds_history(self, event_id: UUID) -> tuple[OddsSnapshot, ...]:
        snapshots = (
            snapshot
            for scenario in self.catalog.scenarios
            if scenario.current_event.event_id == event_id
            for snapshot in scenario.odds_history
        )
        return tuple(sorted(snapshots, key=lambda snapshot: snapshot.captured_at))


@dataclass(frozen=True, slots=True)
class MockModelRepository:
    catalog: MockScenarioCatalog

    def __post_init__(self) -> None:
        _validate_catalog(self.catalog)

    def list(self) -> tuple[ModelSummary, ...]:
        return _unique_by_id(
            (scenario.model_summary for scenario in self.catalog.scenarios),
            lambda model: model.model_version_id,
        )

    def get(self, model_version_id: UUID) -> ModelSummary | None:
        return next(
            (model for model in self.list() if model.model_version_id == model_version_id),
            None,
        )


@dataclass(frozen=True, slots=True)
class MockPaperRepository:
    catalog: MockScenarioCatalog

    def __post_init__(self) -> None:
        _validate_catalog(self.catalog)

    def list(self) -> tuple[PaperBet, ...]:
        return tuple(
            scenario.paper_bet
            for scenario in self.catalog.scenarios
            if scenario.paper_bet is not None
        )

    def get(self, paper_bet_id: UUID) -> PaperBet | None:
        return next((item for item in self.list() if item.paper_bet_id == paper_bet_id), None)


@dataclass(frozen=True, slots=True)
class MockDataHealthRepository:
    catalog: MockScenarioCatalog

    def __post_init__(self) -> None:
        _validate_catalog(self.catalog)

    def list(self) -> tuple[ProviderHealth, ...]:
        failed = any(scenario.source_sync_failed for scenario in self.catalog.scenarios)
        last_success_at = max(
            snapshot.captured_at
            for scenario in self.catalog.scenarios
            for snapshot in scenario.odds_history
        )
        return (
            ProviderHealth(
                provider_code=MockOddsProvider.provider_code,
                status=ProviderStatus.DEGRADED if failed else ProviderStatus.OPERATIONAL,
                checked_at=self.catalog.reference_time,
                last_success_at=last_success_at,
                detail=(
                    "Une synchronisation mock a échoué ; le dernier snapshot valide est conservé"
                    if failed
                    else None
                ),
            ),
        )

    def get(self, provider_code: str) -> ProviderHealth | None:
        return next((item for item in self.list() if item.provider_code == provider_code), None)


@dataclass(frozen=True, slots=True)
class MockMappingRepository:
    catalog: MockScenarioCatalog

    def __post_init__(self) -> None:
        _validate_catalog(self.catalog)

    def list_pending(self) -> tuple[MappingReview, ...]:
        return tuple(
            review
            for scenario in self.catalog.scenarios
            if (review := scenario.mapping_review) is not None
            and review.status is MappingReviewStatus.PENDING
        )

    def get(self, mapping_review_id: UUID) -> MappingReview | None:
        return next(
            (item for item in self.list_pending() if item.mapping_review_id == mapping_review_id),
            None,
        )


@dataclass(frozen=True, slots=True)
class MockOddsProvider:
    """Provider sans réseau partageant le contrat des futurs providers réels."""

    catalog: MockScenarioCatalog
    provider_code = "mock-provider"

    def __post_init__(self) -> None:
        _validate_catalog(self.catalog)

    def _scenario(self, provider_event_id: str) -> MockScenario | None:
        return next(
            (
                scenario
                for scenario in self.catalog.scenarios
                if self._provider_event_id(scenario) == provider_event_id
            ),
            None,
        )

    @staticmethod
    def _provider_event_id(scenario: MockScenario) -> str:
        return f"mock-event-{scenario.scenario_key.value}"

    def list_events(
        self,
        starts_from: datetime,
        starts_to: datetime,
        game_title: GameTitle,
    ) -> tuple[ProviderEvent, ...]:
        if starts_to < starts_from:
            raise ValueError("startsTo doit être postérieur ou égal à startsFrom")
        return tuple(
            ProviderEvent(
                provider_event_id=self._provider_event_id(scenario),
                game_title=event.game_title,
                competition=event.competition,
                participants=(event.team_a, event.team_b),
                starts_at=event.starts_at,
                best_of=event.best_of,
                status=event.status,
                collected_at=event.observed_at,
                source_reference=f"mock-v1:{scenario.scenario_key.value}:event",
            )
            for scenario in self.catalog.scenarios
            if (event := scenario.current_event).game_title is game_title
            and starts_from <= event.starts_at <= starts_to
        )

    def get_event_markets(self, provider_event_id: str) -> tuple[ProviderMarket, ...]:
        scenario = self._scenario(provider_event_id)
        if scenario is None:
            return ()
        market = scenario.current_market
        latest = scenario.odds_history[-1]
        return (
            ProviderMarket(
                provider_event_id=provider_event_id,
                provider_market_id=str(market.market_id),
                raw_label=f"{market.selection_label} vainqueur",
                market_type=market.type,
                period=market.period,
                line=market.line,
                selections=(
                    ProviderSelection(
                        selection=latest.selection,
                        label=market.selection_label,
                        decimal_odds=latest.decimal_odds,
                    ),
                ),
                status=market.status,
                captured_at=latest.captured_at,
                settlement_rules_version=market.settlement_rules_version or "unknown",
            ),
        )

    def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult:
        scenario = self._scenario(provider_event_id)
        if scenario is None:
            raise LookupError(f"Événement fournisseur inconnu : {provider_event_id}")
        return OddsCaptureResult(
            provider_event_id=provider_event_id,
            captured_at=self.catalog.reference_time,
            snapshots=scenario.odds_history,
        )

    def health(self) -> ProviderHealth:
        return MockDataHealthRepository(self.catalog).list()[0]


@dataclass(frozen=True, slots=True)
class MockRepositoryBundle:
    opportunities: MockOpportunityRepository
    events: MockEventRepository
    models: MockModelRepository
    paper: MockPaperRepository
    data_health: MockDataHealthRepository
    mappings: MockMappingRepository
    odds_provider: MockOddsProvider


def build_mock_repository_bundle(catalog: MockScenarioCatalog) -> MockRepositoryBundle:
    """Construire tous les adaptateurs mock depuis un unique catalogue immuable."""

    _validate_catalog(catalog)
    return MockRepositoryBundle(
        opportunities=MockOpportunityRepository(catalog),
        events=MockEventRepository(catalog),
        models=MockModelRepository(catalog),
        paper=MockPaperRepository(catalog),
        data_health=MockDataHealthRepository(catalog),
        mappings=MockMappingRepository(catalog),
        odds_provider=MockOddsProvider(catalog),
    )
