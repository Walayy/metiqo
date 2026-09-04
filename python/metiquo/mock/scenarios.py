"""Catalogue normatif des douze scénarios mock."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Self
from uuid import UUID, uuid5

from pydantic import Field, model_validator

from metiquo.contracts import (
    ContractMetadata,
    Event,
    MappingCandidate,
    MappingReview,
    Market,
    ModelSummary,
    OddsSnapshot,
    Opportunity,
    PaperBet,
    Prediction,
    Quality,
    Value,
)
from metiquo.contracts.base import ContractModel, NonEmptyText, UtcDateTime
from metiquo.contracts.enums import (
    AbstentionReason,
    DataMode,
    EventStatus,
    FreshnessStatus,
    GameTitle,
    MappingReviewStatus,
    MarketPeriod,
    MarketStatus,
    MarketType,
    ModelStatus,
    PaperBetStatus,
    ProviderStatus,
    SelectionType,
    ValueGrade,
)
from metiquo.foundation.time import Clock

_MOCK_NAMESPACE = UUID("c7edbce5-bfb1-42af-8f87-9e2239fabce4")
_APP_VERSION = "0.1.0"
_SETTLEMENT_RULES_VERSION = "lol-match-winner-v1"


class MockScenarioKey(StrEnum):
    """Clés stables des scénarios exigés par la SFG."""

    LOW_VALUE = "low_value"
    OUTSIDER_VALUE = "outsider_value"
    STALE_ODDS = "stale_odds"
    SUSPENDED_MARKET = "suspended_market"
    AMBIGUOUS_MAPPING = "ambiguous_mapping"
    INCOMPLETE_ORACLE_DATA = "incomplete_oracle_data"
    STALE_MODEL = "stale_model"
    HIGH_UNCERTAINTY = "high_uncertainty"
    FAILED_SYNC_WITH_VALID_SNAPSHOT = "failed_sync_with_valid_snapshot"
    ODDS_CHANGE_WHILE_OPEN = "odds_change_while_open"
    VOID_RESULT = "void_result"
    QUARANTINED_RESULT = "quarantined_result"


class MockResultState(StrEnum):
    """État de résultat complémentaire à la décision historique immuable."""

    PENDING = "pending"
    VOID = "void"
    QUARANTINED = "quarantined"


class MockScenario(ContractModel):
    """Agrégat de fixture composé uniquement des contrats métier canoniques."""

    scenario_key: MockScenarioKey = Field(alias="scenarioKey")
    opportunity: Opportunity
    current_event: Event = Field(alias="currentEvent")
    current_market: Market = Field(alias="currentMarket")
    odds_history: tuple[OddsSnapshot, ...] = Field(alias="oddsHistory", min_length=1)
    model_summary: ModelSummary = Field(alias="modelSummary")
    mapping_review: MappingReview | None = Field(default=None, alias="mappingReview")
    paper_bet: PaperBet | None = Field(default=None, alias="paperBet")
    source_sync_failed: bool = Field(default=False, alias="sourceSyncFailed")
    last_valid_snapshot_id: UUID | None = Field(default=None, alias="lastValidSnapshotId")
    odds_changed_while_open: bool = Field(default=False, alias="oddsChangedWhileOpen")
    result_state: MockResultState = Field(default=MockResultState.PENDING, alias="resultState")
    quarantine_reason: NonEmptyText | None = Field(default=None, alias="quarantineReason")

    @model_validator(mode="after")
    def shared_contract_references_are_consistent(self) -> Self:
        event_id = self.opportunity.event.event_id
        market_id = self.opportunity.market.market_id
        if self.opportunity.meta.data_mode is not DataMode.MOCK:
            raise ValueError("Un scénario mock doit exposer dataMode=mock")
        if self.current_event.event_id != event_id or self.current_market.event_id != event_id:
            raise ValueError("Les projections courantes doivent référencer le même événement")
        if self.current_market.market_id != market_id:
            raise ValueError("La projection de marché doit référencer le même marché")
        if self.model_summary.model_version_id != self.opportunity.model.model_version_id:
            raise ValueError("Le résumé modèle doit correspondre à la prédiction")
        for snapshot in self.odds_history:
            if snapshot.event_id != event_id or snapshot.market_id != market_id:
                raise ValueError("L'historique de cotes doit rester dans le même marché")
        snapshot_ids = tuple(snapshot.odds_snapshot_id for snapshot in self.odds_history)
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise ValueError("Les snapshots de cotes d'un scénario doivent être uniques")
        if self.opportunity.book.odds_snapshot_id not in snapshot_ids:
            raise ValueError("La cote du signal doit être conservée dans son historique")
        return self

    @model_validator(mode="after")
    def operational_state_is_consistent(self) -> Self:
        snapshot_ids = {snapshot.odds_snapshot_id for snapshot in self.odds_history}
        if self.source_sync_failed != (self.last_valid_snapshot_id is not None):
            raise ValueError("Un échec de sync doit référencer son dernier snapshot valide")
        if (
            self.last_valid_snapshot_id is not None
            and self.last_valid_snapshot_id not in snapshot_ids
        ):
            raise ValueError("Le dernier snapshot valide doit appartenir à l'historique")
        if self.odds_changed_while_open != (len(self.odds_history) > 1):
            raise ValueError("Un changement de cote doit conserver plusieurs snapshots")
        if self.mapping_review is not None:
            if self.mapping_review.status is not MappingReviewStatus.PENDING:
                raise ValueError("Le mapping ambigu mock doit rester en attente")
            if self.opportunity.quality.mapping_confidence >= Decimal("0.80"):
                raise ValueError("Un mapping ambigu doit rester sous le seuil d'admission")
        return self

    @model_validator(mode="after")
    def result_state_is_consistent(self) -> Self:
        if self.result_state is MockResultState.VOID:
            if self.current_event.status is not EventStatus.CANCELLED:
                raise ValueError("Un résultat void doit exposer un événement annulé")
            if self.current_market.status is not MarketStatus.VOID:
                raise ValueError("Un résultat void doit exposer un marché void")
            if self.paper_bet is None or self.paper_bet.status is not PaperBetStatus.VOID:
                raise ValueError("Un résultat void doit conserver son règlement paper")
        elif self.result_state is MockResultState.QUARANTINED:
            if self.quarantine_reason is None:
                raise ValueError("Un résultat en quarantaine doit conserver sa raison")
            if self.paper_bet is None or self.paper_bet.status is not PaperBetStatus.PENDING_REVIEW:
                raise ValueError("Un résultat en quarantaine doit attendre une revue paper")
        elif self.paper_bet is not None:
            raise ValueError("Un résultat en attente ne doit pas avoir de paper bet de résultat")
        if self.result_state is not MockResultState.QUARANTINED and self.quarantine_reason:
            raise ValueError("Une raison de quarantaine exige un résultat en quarantaine")
        if self.paper_bet is not None:
            if self.paper_bet.signal_id != self.opportunity.signal_id:
                raise ValueError("Le paper bet doit référencer le signal du scénario")
            if self.paper_bet.prediction_id != self.opportunity.model.prediction_id:
                raise ValueError("Le paper bet doit référencer la prédiction du scénario")
            if self.paper_bet.odds_snapshot_id != self.opportunity.book.odds_snapshot_id:
                raise ValueError("Le paper bet doit référencer la cote du signal")
        return self


class MockScenarioCatalog(ContractModel):
    """Catalogue complet, versionné et adressable par clé stable."""

    seed: NonEmptyText
    reference_time: UtcDateTime = Field(alias="referenceTime")
    scenarios: tuple[MockScenario, ...] = Field(min_length=12, max_length=12)

    @model_validator(mode="after")
    def contains_each_normative_scenario_once(self) -> Self:
        actual = tuple(scenario.scenario_key for scenario in self.scenarios)
        if len(actual) != len(set(actual)):
            raise ValueError("Les clés de scénarios mock doivent être uniques")
        if set(actual) != set(MockScenarioKey):
            raise ValueError("Le catalogue doit contenir les douze scénarios normatifs")
        return self

    def __getitem__(self, key: MockScenarioKey) -> MockScenario:
        for scenario in self.scenarios:
            if scenario.scenario_key is key:
                return scenario
        raise KeyError(key)


@dataclass(frozen=True, slots=True)
class _ScenarioProfile:
    key: MockScenarioKey
    decimal_odds: Decimal
    raw_probability: Decimal
    no_vig_probability: Decimal
    probability: Decimal
    probability_low: Decimal
    probability_high: Decimal
    confidence: Decimal
    data_coverage: Decimal
    distribution_distance: Decimal
    fair_odds: Decimal
    edge: Decimal
    expected_value: Decimal
    conservative_expected_value: Decimal
    grade: ValueGrade
    abstentions: tuple[AbstentionReason, ...] = ()
    freshness: FreshnessStatus = FreshnessStatus.FRESH
    market_status: MarketStatus = MarketStatus.OPEN
    publishable: bool = False
    mapping_confidence: Decimal = Decimal("0.99")
    captured_age_seconds: int = 20
    model_age_days: int = 30
    source_sync_failed: bool = False
    odds_changed: bool = False
    result_state: MockResultState = MockResultState.PENDING


_PROFILES = (
    _ScenarioProfile(
        MockScenarioKey.LOW_VALUE,
        Decimal("1.80"),
        Decimal("0.555556"),
        Decimal("0.545000"),
        Decimal("0.540000"),
        Decimal("0.510000"),
        Decimal("0.570000"),
        Decimal("0.910000"),
        Decimal("0.980000"),
        Decimal("0.080000"),
        Decimal("1.851852"),
        Decimal("-0.005000"),
        Decimal("-0.028000"),
        Decimal("-0.082000"),
        ValueGrade.NO_EDGE,
        abstentions=(AbstentionReason.EDGE_TOO_SMALL,),
    ),
    _ScenarioProfile(
        MockScenarioKey.OUTSIDER_VALUE,
        Decimal("4.50"),
        Decimal("0.222222"),
        Decimal("0.215000"),
        Decimal("0.280000"),
        Decimal("0.240000"),
        Decimal("0.330000"),
        Decimal("0.860000"),
        Decimal("0.950000"),
        Decimal("0.180000"),
        Decimal("3.571429"),
        Decimal("0.065000"),
        Decimal("0.260000"),
        Decimal("0.080000"),
        ValueGrade.STRONG_VALUE,
        publishable=True,
        captured_age_seconds=25,
    ),
    _ScenarioProfile(
        MockScenarioKey.STALE_ODDS,
        Decimal("2.20"),
        Decimal("0.454545"),
        Decimal("0.440000"),
        Decimal("0.500000"),
        Decimal("0.460000"),
        Decimal("0.540000"),
        Decimal("0.840000"),
        Decimal("0.940000"),
        Decimal("0.220000"),
        Decimal("2.000000"),
        Decimal("0.060000"),
        Decimal("0.100000"),
        Decimal("0.012000"),
        ValueGrade.BLOCKED,
        abstentions=(AbstentionReason.ODDS_STALE,),
        freshness=FreshnessStatus.STALE,
        captured_age_seconds=600,
    ),
    _ScenarioProfile(
        MockScenarioKey.SUSPENDED_MARKET,
        Decimal("2.05"),
        Decimal("0.487805"),
        Decimal("0.475000"),
        Decimal("0.520000"),
        Decimal("0.480000"),
        Decimal("0.560000"),
        Decimal("0.880000"),
        Decimal("0.970000"),
        Decimal("0.110000"),
        Decimal("1.923077"),
        Decimal("0.045000"),
        Decimal("0.066000"),
        Decimal("-0.016000"),
        ValueGrade.BLOCKED,
        abstentions=(AbstentionReason.MARKET_SUSPENDED,),
        market_status=MarketStatus.SUSPENDED,
        captured_age_seconds=15,
    ),
    _ScenarioProfile(
        MockScenarioKey.AMBIGUOUS_MAPPING,
        Decimal("2.80"),
        Decimal("0.357143"),
        Decimal("0.345000"),
        Decimal("0.410000"),
        Decimal("0.360000"),
        Decimal("0.460000"),
        Decimal("0.790000"),
        Decimal("0.900000"),
        Decimal("0.310000"),
        Decimal("2.439024"),
        Decimal("0.065000"),
        Decimal("0.148000"),
        Decimal("0.008000"),
        ValueGrade.BLOCKED,
        abstentions=(AbstentionReason.EVENT_MAPPING_AMBIGUOUS,),
        mapping_confidence=Decimal("0.620000"),
        captured_age_seconds=30,
    ),
    _ScenarioProfile(
        MockScenarioKey.INCOMPLETE_ORACLE_DATA,
        Decimal("2.35"),
        Decimal("0.425532"),
        Decimal("0.410000"),
        Decimal("0.470000"),
        Decimal("0.330000"),
        Decimal("0.610000"),
        Decimal("0.480000"),
        Decimal("0.420000"),
        Decimal("0.720000"),
        Decimal("2.127660"),
        Decimal("0.060000"),
        Decimal("0.104500"),
        Decimal("-0.224500"),
        ValueGrade.BLOCKED,
        abstentions=(AbstentionReason.INSUFFICIENT_HISTORY,),
        freshness=FreshnessStatus.DEGRADED,
        captured_age_seconds=35,
    ),
    _ScenarioProfile(
        MockScenarioKey.STALE_MODEL,
        Decimal("2.60"),
        Decimal("0.384615"),
        Decimal("0.370000"),
        Decimal("0.440000"),
        Decimal("0.390000"),
        Decimal("0.490000"),
        Decimal("0.760000"),
        Decimal("0.930000"),
        Decimal("0.390000"),
        Decimal("2.272727"),
        Decimal("0.070000"),
        Decimal("0.144000"),
        Decimal("0.014000"),
        ValueGrade.BLOCKED,
        abstentions=(AbstentionReason.MODEL_STALE,),
        freshness=FreshnessStatus.DEGRADED,
        captured_age_seconds=45,
        model_age_days=240,
    ),
    _ScenarioProfile(
        MockScenarioKey.HIGH_UNCERTAINTY,
        Decimal("3.10"),
        Decimal("0.322581"),
        Decimal("0.310000"),
        Decimal("0.450000"),
        Decimal("0.200000"),
        Decimal("0.720000"),
        Decimal("0.310000"),
        Decimal("0.780000"),
        Decimal("1.840000"),
        Decimal("2.222222"),
        Decimal("0.140000"),
        Decimal("0.395000"),
        Decimal("-0.380000"),
        ValueGrade.BLOCKED,
        abstentions=(AbstentionReason.OUT_OF_DISTRIBUTION,),
        captured_age_seconds=50,
    ),
    _ScenarioProfile(
        MockScenarioKey.FAILED_SYNC_WITH_VALID_SNAPSHOT,
        Decimal("2.15"),
        Decimal("0.465116"),
        Decimal("0.450000"),
        Decimal("0.510000"),
        Decimal("0.470000"),
        Decimal("0.550000"),
        Decimal("0.820000"),
        Decimal("0.920000"),
        Decimal("0.280000"),
        Decimal("1.960784"),
        Decimal("0.060000"),
        Decimal("0.096500"),
        Decimal("0.010500"),
        ValueGrade.BLOCKED,
        abstentions=(AbstentionReason.SOURCE_STALE,),
        freshness=FreshnessStatus.DEGRADED,
        captured_age_seconds=3600,
        source_sync_failed=True,
    ),
    _ScenarioProfile(
        MockScenarioKey.ODDS_CHANGE_WHILE_OPEN,
        Decimal("4.20"),
        Decimal("0.238095"),
        Decimal("0.230000"),
        Decimal("0.290000"),
        Decimal("0.250000"),
        Decimal("0.340000"),
        Decimal("0.850000"),
        Decimal("0.950000"),
        Decimal("0.190000"),
        Decimal("3.448276"),
        Decimal("0.060000"),
        Decimal("0.218000"),
        Decimal("0.050000"),
        ValueGrade.VALUE,
        publishable=True,
        captured_age_seconds=40,
        odds_changed=True,
    ),
    _ScenarioProfile(
        MockScenarioKey.VOID_RESULT,
        Decimal("2.40"),
        Decimal("0.416667"),
        Decimal("0.405000"),
        Decimal("0.470000"),
        Decimal("0.430000"),
        Decimal("0.510000"),
        Decimal("0.870000"),
        Decimal("0.960000"),
        Decimal("0.160000"),
        Decimal("2.127660"),
        Decimal("0.065000"),
        Decimal("0.128000"),
        Decimal("0.032000"),
        ValueGrade.VALUE,
        publishable=True,
        captured_age_seconds=36000,
        result_state=MockResultState.VOID,
    ),
    _ScenarioProfile(
        MockScenarioKey.QUARANTINED_RESULT,
        Decimal("2.70"),
        Decimal("0.370370"),
        Decimal("0.355000"),
        Decimal("0.420000"),
        Decimal("0.380000"),
        Decimal("0.470000"),
        Decimal("0.830000"),
        Decimal("0.940000"),
        Decimal("0.240000"),
        Decimal("2.380952"),
        Decimal("0.065000"),
        Decimal("0.134000"),
        Decimal("0.026000"),
        ValueGrade.VALUE,
        publishable=True,
        captured_age_seconds=43200,
        result_state=MockResultState.QUARANTINED,
    ),
)


def _stable_id(seed: str, scenario: MockScenarioKey, entity: str) -> UUID:
    return uuid5(_MOCK_NAMESPACE, f"metiquo:mock:v1:{seed}:{scenario.value}:{entity}")


def _stable_hash(seed: str, scenario: MockScenarioKey, entity: str) -> str:
    value = f"metiquo:mock:v1:{seed}:{scenario.value}:{entity}".encode()
    return sha256(value).hexdigest()


def _build_event(
    seed: str,
    profile: _ScenarioProfile,
    index: int,
    reference_time: datetime,
    captured_at: datetime,
) -> Event:
    starts_at = reference_time + timedelta(hours=4, minutes=30 * index)
    if profile.result_state is not MockResultState.PENDING:
        starts_at = reference_time - timedelta(hours=4 + (index - 10) * 2)
    return Event(
        event_id=_stable_id(seed, profile.key, "event"),
        game_title=GameTitle.LEAGUE_OF_LEGENDS,
        competition=f"Ligue Démo {index + 1:02d}",
        team_a_id=_stable_id(seed, profile.key, "team-a"),
        team_a=f"Aurore {index + 1:02d}",
        team_b_id=_stable_id(seed, profile.key, "team-b"),
        team_b=f"Bastion {index + 1:02d}",
        starts_at=starts_at,
        best_of=3,
        status=EventStatus.SCHEDULED,
        observed_at=captured_at - timedelta(minutes=5),
    )


def _build_market(seed: str, profile: _ScenarioProfile, event: Event) -> Market:
    return Market(
        market_id=_stable_id(seed, profile.key, "market"),
        event_id=event.event_id,
        type=MarketType.MATCH_WINNER,
        period=MarketPeriod.SERIES,
        selection=SelectionType.TEAM_B,
        selection_label=event.team_b,
        status=profile.market_status,
        settlement_rules_version=_SETTLEMENT_RULES_VERSION,
    )


def _build_odds_snapshot(
    seed: str,
    profile: _ScenarioProfile,
    event: Event,
    market: Market,
    captured_at: datetime,
    reference_time: datetime,
) -> OddsSnapshot:
    return OddsSnapshot(
        odds_snapshot_id=_stable_id(seed, profile.key, "odds-1"),
        event_id=event.event_id,
        market_id=market.market_id,
        selection=market.selection,
        provider="mock-provider",
        provider_status=ProviderStatus.OPERATIONAL,
        market_status=profile.market_status,
        decimal_odds=profile.decimal_odds,
        captured_at=captured_at,
        age_seconds=int((reference_time - captured_at).total_seconds()),
        raw_implied_probability=profile.raw_probability,
        no_vig_probability=profile.no_vig_probability,
        informational_only=False,
        provenance_reference=f"mock-v1:{seed}:{profile.key.value}:odds-1",
    )


def _build_prediction(
    seed: str,
    profile: _ScenarioProfile,
    event: Event,
    market: Market,
    captured_at: datetime,
) -> Prediction:
    return Prediction(
        prediction_id=_stable_id(seed, profile.key, "prediction"),
        event_id=event.event_id,
        market_id=market.market_id,
        selection=market.selection,
        probability=profile.probability,
        probability_low=profile.probability_low,
        probability_high=profile.probability_high,
        confidence=profile.confidence,
        confidence_reduction_reasons=tuple(reason.value for reason in profile.abstentions),
        data_coverage=profile.data_coverage,
        out_of_distribution_distance=profile.distribution_distance,
        prediction_cutoff=captured_at - timedelta(seconds=1),
        model_version_id=_stable_id(seed, profile.key, "model"),
        model_version=f"mock-mw-v1-{profile.key.value}",
        feature_snapshot_id=_stable_id(seed, profile.key, "features"),
        created_at=captured_at,
    )


def _build_opportunity(
    seed: str,
    profile: _ScenarioProfile,
    event: Event,
    market: Market,
    book: OddsSnapshot,
    prediction: Prediction,
    captured_at: datetime,
) -> Opportunity:
    return Opportunity(
        signal_id=_stable_id(seed, profile.key, "signal"),
        event=event,
        market=market,
        book=book,
        model=prediction,
        value=Value(
            fair_odds=profile.fair_odds,
            edge=profile.edge,
            expected_value=profile.expected_value,
            conservative_expected_value=profile.conservative_expected_value,
            grade=profile.grade,
        ),
        quality=Quality(
            mapping_confidence=profile.mapping_confidence,
            source_freshness=profile.freshness,
            data_coverage=profile.data_coverage,
            model_status=ModelStatus.CHAMPION,
            abstention_reasons=profile.abstentions,
            publishable=profile.publishable,
        ),
        meta=ContractMetadata(
            data_mode=DataMode.MOCK,
            freshness=profile.freshness,
            as_of=captured_at,
            computed_at=captured_at + timedelta(seconds=2),
            app_version=_APP_VERSION,
        ),
        explanation_reference=f"mock-v1:{profile.key.value}",
    )


def _build_model_summary(
    seed: str,
    profile: _ScenarioProfile,
    prediction: Prediction,
    captured_at: datetime,
) -> ModelSummary:
    created_at = captured_at - timedelta(days=profile.model_age_days)
    return ModelSummary(
        model_version_id=prediction.model_version_id,
        model_version=prediction.model_version,
        game_title=GameTitle.LEAGUE_OF_LEGENDS,
        market_type=MarketType.MATCH_WINNER,
        algorithm="baseline-logistic-regression",
        feature_version="mock-features-v1",
        dataset_hash=_stable_hash(seed, profile.key, "dataset"),
        artifact_hash=_stable_hash(seed, profile.key, "artifact"),
        code_commit=_stable_hash(seed, profile.key, "code"),
        train_cutoff=created_at - timedelta(days=1),
        status=ModelStatus.CHAMPION,
        metrics={"log_loss": Decimal("0.612000"), "brier": Decimal("0.208000")},
        baseline_metrics={"log_loss": Decimal("0.693000"), "brier": Decimal("0.250000")},
        created_at=created_at,
        promoted_at=created_at + timedelta(days=1),
        promotion_reason="Validation walk-forward et calibration mock",
    )


def _build_mapping_review(
    seed: str,
    profile: _ScenarioProfile,
    event: Event,
    captured_at: datetime,
) -> MappingReview | None:
    if profile.key is not MockScenarioKey.AMBIGUOUS_MAPPING:
        return None
    return MappingReview(
        mapping_review_id=_stable_id(seed, profile.key, "mapping-review"),
        provider="mock-provider",
        provider_event_id=f"mock-event-{profile.key.value}",
        raw_competition="Ligue Démo",
        raw_participants=(event.team_a, event.team_b),
        candidates=(
            MappingCandidate(
                event_id=event.event_id,
                label=f"{event.team_a} — {event.team_b}",
                confidence=Decimal("0.620000"),
                reasons=("Participants proches", "Compétition incertaine"),
            ),
            MappingCandidate(
                event_id=_stable_id(seed, profile.key, "alternate-event"),
                label=f"{event.team_a} Academy — {event.team_b}",
                confidence=Decimal("0.590000"),
                reasons=("Alias partagé", "Horaire proche"),
            ),
        ),
        status=MappingReviewStatus.PENDING,
        created_at=captured_at,
    )


def _build_updated_odds(
    seed: str,
    profile: _ScenarioProfile,
    book: OddsSnapshot,
    reference_time: datetime,
) -> OddsSnapshot | None:
    if not profile.odds_changed:
        return None
    return OddsSnapshot(
        odds_snapshot_id=_stable_id(seed, profile.key, "odds-2"),
        event_id=book.event_id,
        market_id=book.market_id,
        selection=book.selection,
        provider=book.provider,
        provider_status=ProviderStatus.OPERATIONAL,
        market_status=MarketStatus.OPEN,
        decimal_odds=Decimal("3.60"),
        captured_at=reference_time - timedelta(seconds=5),
        age_seconds=5,
        raw_implied_probability=Decimal("0.277778"),
        no_vig_probability=Decimal("0.265000"),
        informational_only=False,
        provenance_reference=f"mock-v1:{seed}:{profile.key.value}:odds-2",
    )


def _build_current_projections(
    event: Event,
    market: Market,
    profile: _ScenarioProfile,
    reference_time: datetime,
) -> tuple[Event, Market]:
    if profile.result_state is MockResultState.PENDING:
        return event, market
    event_status = (
        EventStatus.CANCELLED
        if profile.result_state is MockResultState.VOID
        else EventStatus.FINISHED
    )
    market_status = (
        MarketStatus.VOID if profile.result_state is MockResultState.VOID else MarketStatus.SETTLED
    )
    current_event = Event.model_validate(
        {**event.model_dump(), "status": event_status, "observed_at": reference_time}
    )
    current_market = Market.model_validate({**market.model_dump(), "status": market_status})
    return current_event, current_market


def _build_paper_bet(
    seed: str,
    profile: _ScenarioProfile,
    opportunity: Opportunity,
    captured_at: datetime,
    reference_time: datetime,
) -> PaperBet | None:
    if profile.result_state is MockResultState.PENDING:
        return None
    is_void = profile.result_state is MockResultState.VOID
    return PaperBet(
        paper_bet_id=_stable_id(seed, profile.key, "paper-bet"),
        signal_id=opportunity.signal_id,
        prediction_id=opportunity.model.prediction_id,
        odds_snapshot_id=opportunity.book.odds_snapshot_id,
        entry_odds=opportunity.book.decimal_odds,
        stake_amount=Decimal("10.00"),
        currency="EUR",
        placed_at=captured_at + timedelta(seconds=10),
        status=PaperBetStatus.VOID if is_void else PaperBetStatus.PENDING_REVIEW,
        settlement_rules_version=_SETTLEMENT_RULES_VERSION,
        settled_at=reference_time if is_void else None,
        profit_loss=Decimal("0.00") if is_void else None,
        settlement_reason="Rencontre annulée, mise fictive remboursée" if is_void else None,
    )


def _build_scenario(
    seed: str,
    profile: _ScenarioProfile,
    index: int,
    reference_time: datetime,
) -> MockScenario:
    captured_at = reference_time - timedelta(seconds=profile.captured_age_seconds)
    event = _build_event(seed, profile, index, reference_time, captured_at)
    market = _build_market(seed, profile, event)
    book = _build_odds_snapshot(seed, profile, event, market, captured_at, reference_time)
    prediction = _build_prediction(seed, profile, event, market, captured_at)
    opportunity = _build_opportunity(seed, profile, event, market, book, prediction, captured_at)
    updated_odds = _build_updated_odds(seed, profile, book, reference_time)
    odds_history = (book,) if updated_odds is None else (book, updated_odds)
    current_event, current_market = _build_current_projections(
        event, market, profile, reference_time
    )
    return MockScenario(
        scenario_key=profile.key,
        opportunity=opportunity,
        current_event=current_event,
        current_market=current_market,
        odds_history=odds_history,
        model_summary=_build_model_summary(seed, profile, prediction, captured_at),
        mapping_review=_build_mapping_review(seed, profile, event, captured_at),
        paper_bet=_build_paper_bet(seed, profile, opportunity, captured_at, reference_time),
        source_sync_failed=profile.source_sync_failed,
        last_valid_snapshot_id=book.odds_snapshot_id if profile.source_sync_failed else None,
        odds_changed_while_open=profile.odds_changed,
        result_state=profile.result_state,
        quarantine_reason=(
            "Le résultat reçu contredit les games canoniques"
            if profile.result_state is MockResultState.QUARANTINED
            else None
        ),
    )


def build_mock_scenario_catalog(seed: str, clock: Clock) -> MockScenarioCatalog:
    """Construire les douze scénarios sans réseau, aléa ni temps système implicite."""

    normalized_seed = seed.strip()
    if not normalized_seed:
        raise ValueError("La graine mock ne peut pas être vide")
    reference_time = clock.now().value
    scenarios = tuple(
        _build_scenario(normalized_seed, profile, index, reference_time)
        for index, profile in enumerate(_PROFILES)
    )
    return MockScenarioCatalog(
        seed=normalized_seed,
        reference_time=reference_time,
        scenarios=scenarios,
    )
