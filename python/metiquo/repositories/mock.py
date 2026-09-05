"""Repositories mock immuables alimentés par le catalogue normatif."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid5

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
from metiquo.contracts.enums import (
    BacktestKind,
    DataMode,
    FreshnessStatus,
    GameTitle,
    MappingReviewStatus,
    ProviderStatus,
)
from metiquo.contracts.odds_provider import (
    OddsCaptureResult,
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
    ProviderSelection,
)
from metiquo.foundation.time import Clock
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

    def list_backtests(self) -> tuple[BacktestSummary, ...]:
        return tuple(
            BacktestSummary(
                backtest_id=uuid5(model.model_version_id, "statistical-backtest"),
                model_version_id=model.model_version_id,
                kind=BacktestKind.STATISTICAL,
                starts_at=model.created_at - timedelta(days=90),
                ends_at=model.created_at - timedelta(days=1),
                sample_count=240,
                metrics=model.metrics,
                baseline_metrics=model.baseline_metrics,
                observed_odds_count=0,
                uses_only_observed_odds=False,
                final_test_untouched=True,
                completed_at=model.created_at,
            )
            for model in self.list()
        )

    def get_backtest(self, backtest_id: UUID) -> BacktestSummary | None:
        return next(
            (backtest for backtest in self.list_backtests() if backtest.backtest_id == backtest_id),
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
        age_seconds = max(
            0,
            int((self.catalog.reference_time - last_success_at).total_seconds()),
        )
        return (
            ProviderHealth(
                provider_code=MockOddsProvider.provider_code,
                status=ProviderStatus.DEGRADED if failed else ProviderStatus.OPERATIONAL,
                checked_at=self.catalog.reference_time,
                last_success_at=last_success_at,
                last_capture_at=last_success_at,
                age_seconds=age_seconds,
                failure_count=sum(
                    1 for scenario in self.catalog.scenarios if scenario.source_sync_failed
                ),
                freshness=(FreshnessStatus.DEGRADED if failed else FreshnessStatus.FRESH),
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
class MockOperationsRepository:
    catalog: MockScenarioCatalog

    def __post_init__(self) -> None:
        _validate_catalog(self.catalog)

    def list_ingestion_runs(self) -> tuple[IngestionRunSummary, ...]:
        failed = next(
            scenario for scenario in self.catalog.scenarios if scenario.source_sync_failed
        )
        latest = max(
            snapshot.captured_at
            for scenario in self.catalog.scenarios
            for snapshot in scenario.odds_history
        )
        return (
            IngestionRunSummary(
                run_id=uuid5(failed.opportunity.signal_id, "failed-ingestion-run"),
                source=MockOddsProvider.provider_code,
                status="failed",
                started_at=self.catalog.reference_time - timedelta(minutes=2),
                completed_at=self.catalog.reference_time - timedelta(minutes=1),
                row_count=0,
                data_mode=DataMode.MOCK,
                last_valid_snapshot_id=failed.last_valid_snapshot_id,
            ),
            IngestionRunSummary(
                run_id=uuid5(failed.opportunity.signal_id, "successful-ingestion-run"),
                source=MockOddsProvider.provider_code,
                status="succeeded",
                started_at=latest - timedelta(seconds=2),
                completed_at=latest,
                row_count=len(self.catalog.scenarios),
                data_mode=DataMode.MOCK,
            ),
        )

    def list_quality_issues(self) -> tuple[DataQualityIssue, ...]:
        return tuple(
            DataQualityIssue(
                issue_id=uuid5(scenario.opportunity.signal_id, "quality-issue"),
                source=MockOddsProvider.provider_code,
                code=scenario.opportunity.quality.abstention_reasons[0].value,
                severity="blocking",
                status=("quarantined" if scenario.quarantine_reason is not None else "open"),
                detail=(
                    scenario.quarantine_reason
                    or "Le scénario normatif bloque explicitement la publication"
                ),
                observed_at=scenario.opportunity.meta.as_of,
                data_mode=DataMode.MOCK,
            )
            for scenario in self.catalog.scenarios
            if scenario.opportunity.quality.abstention_reasons
        )

    def list_jobs(self) -> tuple[JobSummary, ...]:
        names = ("odds-sync", "pricing-refresh", "paper-settlement")
        return tuple(
            JobSummary(
                job_id=uuid5(self.catalog.scenarios[0].opportunity.signal_id, name),
                name=name,
                status="idle",
                last_run_at=self.catalog.reference_time - timedelta(minutes=index + 1),
                data_mode=DataMode.MOCK,
            )
            for index, name in enumerate(names)
        )


@dataclass(frozen=True, slots=True)
class MockOddsProvider:
    """Provider sans réseau partageant le contrat des futurs providers réels."""

    catalog: MockScenarioCatalog
    clock: Clock | None = None
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

    def _now(self) -> datetime:
        return self.clock.now().value if self.clock is not None else self.catalog.reference_time

    @staticmethod
    def _snapshots_at(scenario: MockScenario, observed_at: datetime) -> tuple[OddsSnapshot, ...]:
        return tuple(
            snapshot.model_copy(
                update={"age_seconds": int((observed_at - snapshot.captured_at).total_seconds())}
            )
            for snapshot in scenario.odds_history
            if snapshot.captured_at <= observed_at
        )

    def list_events(
        self,
        starts_from: datetime,
        starts_to: datetime,
        game_title: GameTitle,
    ) -> tuple[ProviderEvent, ...]:
        if starts_to < starts_from:
            raise ValueError("startsTo doit être postérieur ou égal à startsFrom")
        observed_at = self._now()
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
            and event.observed_at <= observed_at
            and self._snapshots_at(scenario, observed_at)
        )

    def get_event_markets(self, provider_event_id: str) -> tuple[ProviderMarket, ...]:
        scenario = self._scenario(provider_event_id)
        if scenario is None:
            return ()
        snapshots = self._snapshots_at(scenario, self._now())
        if not snapshots:
            return ()
        market = scenario.current_market
        latest = snapshots[-1]
        return (
            ProviderMarket(
                provider_event_id=provider_event_id,
                provider_market_id=str(market.market_id),
                raw_label=f"{market.selection_label} vainqueur",
                market_type=market.type,
                period=market.period,
                line=market.line,
                unit="winner",
                selections=(
                    ProviderSelection(
                        provider_selection_id=(
                            f"{market.market_id}:{latest.selection.value.casefold()}"
                        ),
                        selection=latest.selection,
                        label=market.selection_label,
                        decimal_odds=latest.decimal_odds,
                    ),
                ),
                status=market.status,
                remake_policy="void",
                forfeit_policy="settle",
                cancelled_policy="void",
                captured_at=latest.captured_at,
                settlement_rules_version=market.settlement_rules_version or "unknown",
            ),
        )

    def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult:
        scenario = self._scenario(provider_event_id)
        if scenario is None:
            raise LookupError(f"Événement fournisseur inconnu : {provider_event_id}")
        observed_at = self._now()
        return OddsCaptureResult(
            provider_event_id=provider_event_id,
            captured_at=observed_at,
            snapshots=self._snapshots_at(scenario, observed_at),
        )

    def health(self) -> ProviderHealth:
        observed_at = self._now()
        snapshots = tuple(
            snapshot
            for scenario in self.catalog.scenarios
            for snapshot in self._snapshots_at(scenario, observed_at)
        )
        if not snapshots:
            return ProviderHealth(
                provider_code=self.provider_code,
                status=ProviderStatus.UNAVAILABLE,
                checked_at=observed_at,
                failure_count=sum(
                    1 for scenario in self.catalog.scenarios if scenario.source_sync_failed
                ),
                freshness=FreshnessStatus.FAILED,
                detail="Aucune observation mock disponible à cet instant",
            )
        failed = any(scenario.source_sync_failed for scenario in self.catalog.scenarios)
        last_capture_at = max(snapshot.captured_at for snapshot in snapshots)
        return ProviderHealth(
            provider_code=self.provider_code,
            status=ProviderStatus.DEGRADED if failed else ProviderStatus.OPERATIONAL,
            checked_at=observed_at,
            last_success_at=last_capture_at,
            last_capture_at=last_capture_at,
            age_seconds=max(0, int((observed_at - last_capture_at).total_seconds())),
            failure_count=sum(
                1 for scenario in self.catalog.scenarios if scenario.source_sync_failed
            ),
            freshness=FreshnessStatus.DEGRADED if failed else FreshnessStatus.FRESH,
            detail=(
                "Une synchronisation mock a échoué ; le dernier snapshot valide est conservé"
                if failed
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class MockRepositoryBundle:
    opportunities: MockOpportunityRepository
    events: MockEventRepository
    models: MockModelRepository
    paper: MockPaperRepository
    data_health: MockDataHealthRepository
    mappings: MockMappingRepository
    operations: MockOperationsRepository
    odds_provider: MockOddsProvider


def build_mock_repository_bundle(
    catalog: MockScenarioCatalog,
    *,
    clock: Clock | None = None,
) -> MockRepositoryBundle:
    """Construire tous les adaptateurs mock depuis un unique catalogue immuable."""

    _validate_catalog(catalog)
    return MockRepositoryBundle(
        opportunities=MockOpportunityRepository(catalog),
        events=MockEventRepository(catalog),
        models=MockModelRepository(catalog),
        paper=MockPaperRepository(catalog),
        data_health=MockDataHealthRepository(catalog),
        mappings=MockMappingRepository(catalog),
        operations=MockOperationsRepository(catalog),
        odds_provider=MockOddsProvider(catalog, clock),
    )
