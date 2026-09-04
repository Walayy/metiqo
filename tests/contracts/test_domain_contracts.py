"""Tests des contrats canoniques partagés par mock et réel."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from metiquo.contracts import (
    DOMAIN_CONTRACT_MODELS,
    BacktestSummary,
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
from metiquo.contracts.enums import (
    AbstentionReason,
    BacktestKind,
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

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "python" / "metiquo" / "contracts"

EVENT_ID = UUID("00000000-0000-4000-8000-000000000001")
OTHER_EVENT_ID = UUID("00000000-0000-4000-8000-000000000002")
TEAM_A_ID = UUID("00000000-0000-4000-8000-000000000003")
TEAM_B_ID = UUID("00000000-0000-4000-8000-000000000004")
MARKET_ID = UUID("00000000-0000-4000-8000-000000000005")
ODDS_SNAPSHOT_ID = UUID("00000000-0000-4000-8000-000000000006")
PREDICTION_ID = UUID("00000000-0000-4000-8000-000000000007")
MODEL_VERSION_ID = UUID("00000000-0000-4000-8000-000000000008")
FEATURE_SNAPSHOT_ID = UUID("00000000-0000-4000-8000-000000000009")
SIGNAL_ID = UUID("00000000-0000-4000-8000-000000000010")
BACKTEST_ID = UUID("00000000-0000-4000-8000-000000000011")
PAPER_BET_ID = UUID("00000000-0000-4000-8000-000000000012")
MAPPING_REVIEW_ID = UUID("00000000-0000-4000-8000-000000000013")
STARTS_AT = datetime(2026, 9, 5, 18, tzinfo=UTC)
OBSERVED_AT = datetime(2026, 9, 5, 12, tzinfo=UTC)


def build_event() -> Event:
    return Event(
        event_id=EVENT_ID,
        game_title=GameTitle.LEAGUE_OF_LEGENDS,
        competition="Example League",
        team_a_id=TEAM_A_ID,
        team_a="Team A",
        team_b_id=TEAM_B_ID,
        team_b="Team B",
        starts_at=STARTS_AT,
        best_of=3,
        status=EventStatus.SCHEDULED,
        observed_at=OBSERVED_AT,
    )


def build_market() -> Market:
    return Market(
        market_id=MARKET_ID,
        event_id=EVENT_ID,
        type=MarketType.MATCH_WINNER,
        period=MarketPeriod.SERIES,
        selection=SelectionType.TEAM_B,
        selection_label="Team B",
        status=MarketStatus.OPEN,
        settlement_rules_version="match-winner-v1",
    )


def build_odds_snapshot() -> OddsSnapshot:
    return OddsSnapshot(
        odds_snapshot_id=ODDS_SNAPSHOT_ID,
        event_id=EVENT_ID,
        market_id=MARKET_ID,
        selection=SelectionType.TEAM_B,
        provider="licensed-provider",
        provider_status=ProviderStatus.OPERATIONAL,
        market_status=MarketStatus.OPEN,
        decimal_odds=Decimal("4.0"),
        captured_at=OBSERVED_AT,
        age_seconds=12,
        raw_implied_probability=Decimal("0.25"),
        no_vig_probability=Decimal("0.2381"),
        informational_only=False,
        provenance_reference="manual-import-0001",
    )


def build_prediction() -> Prediction:
    return Prediction(
        prediction_id=PREDICTION_ID,
        event_id=EVENT_ID,
        market_id=MARKET_ID,
        selection=SelectionType.TEAM_B,
        probability=Decimal("0.30"),
        probability_low=Decimal("0.27"),
        probability_high=Decimal("0.34"),
        confidence=Decimal("0.88"),
        confidence_reduction_reasons=(),
        data_coverage=Decimal("0.96"),
        out_of_distribution_distance=Decimal("0.12"),
        prediction_cutoff=OBSERVED_AT - timedelta(seconds=1),
        model_version_id=MODEL_VERSION_ID,
        model_version="mw_2026_09_04_01",
        feature_snapshot_id=FEATURE_SNAPSHOT_ID,
        created_at=OBSERVED_AT,
    )


def build_opportunity() -> Opportunity:
    return Opportunity(
        signal_id=SIGNAL_ID,
        event=build_event(),
        market=build_market(),
        book=build_odds_snapshot(),
        model=build_prediction(),
        value=Value(
            fair_odds=Decimal("3.3333"),
            edge=Decimal("0.0619"),
            expected_value=Decimal("0.20"),
            conservative_expected_value=Decimal("0.08"),
            grade=ValueGrade.VALUE,
        ),
        quality=Quality(
            mapping_confidence=Decimal("0.99"),
            source_freshness=FreshnessStatus.FRESH,
            data_coverage=Decimal("0.96"),
            model_status=ModelStatus.CHAMPION,
            abstention_reasons=(),
            publishable=True,
        ),
        meta=ContractMetadata(
            data_mode=DataMode.MOCK,
            freshness=FreshnessStatus.FRESH,
            as_of=OBSERVED_AT,
            computed_at=OBSERVED_AT + timedelta(seconds=13),
            app_version="0.1.0",
        ),
    )


def test_required_contracts_are_exported_and_round_trip_as_json() -> None:
    required_names = {
        "Opportunity",
        "Event",
        "Market",
        "OddsSnapshot",
        "Prediction",
        "Value",
        "Quality",
        "ModelSummary",
        "BacktestSummary",
        "PaperBet",
        "MappingReview",
    }

    assert required_names <= {model.__name__ for model in DOMAIN_CONTRACT_MODELS}

    opportunity = build_opportunity()
    serialized = opportunity.model_dump_json(by_alias=True)
    restored = Opportunity.model_validate_json(serialized)

    assert restored == opportunity
    assert '"signalId"' in serialized
    assert '"dataMode":"mock"' in serialized
    assert '"predictionCutoff"' in serialized


def test_normative_enums_have_stable_values() -> None:
    assert [game.value for game in GameTitle] == ["lol"]
    assert [market.value for market in MarketType] == ["MATCH_WINNER"]
    assert [grade.value for grade in ValueGrade] == [
        "STRONG_VALUE",
        "VALUE",
        "WATCH",
        "NO_EDGE",
        "BLOCKED",
    ]
    assert {status.value for status in FreshnessStatus} == {
        "fresh",
        "stale",
        "degraded",
        "failed",
        "quarantined",
    }
    assert {reason.value for reason in AbstentionReason} == {
        "ODDS_STALE",
        "MARKET_SUSPENDED",
        "EVENT_MAPPING_AMBIGUOUS",
        "INSUFFICIENT_HISTORY",
        "ROSTER_UNCERTAIN",
        "SOURCE_STALE",
        "MODEL_STALE",
        "OUT_OF_DISTRIBUTION",
        "CALIBRATION_FAILED",
        "EDGE_TOO_SMALL",
        "CONSERVATIVE_EV_NEGATIVE",
        "MARKET_RULES_UNKNOWN",
        "PATCH_CONTEXT_UNKNOWN",
        "EVENT_ALREADY_STARTED",
        "CAPABILITY_DISABLED",
    }


def test_contracts_reject_extra_fields_and_float_quantities() -> None:
    event_data = build_event().model_dump()
    event_data["unexpected"] = "forbidden"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Event.model_validate(event_data)

    value_data = build_opportunity().value.model_dump()
    value_data["edge"] = 0.1
    with pytest.raises(ValidationError, match="instance of Decimal"):
        Value.model_validate(value_data)

    high_ev_data = build_opportunity().value.model_dump()
    high_ev_data["expected_value"] = Decimal("2.5")
    assert Value.model_validate(high_ev_data).expected_value == Decimal("2.5")


def test_contract_times_require_timezone_and_are_normalized_to_utc() -> None:
    event_data = build_event().model_dump()
    event_data["starts_at"] = STARTS_AT.replace(tzinfo=None)

    with pytest.raises(ValidationError, match="fuseau horaire"):
        Event.model_validate(event_data)

    offset_event = build_event().model_copy(
        update={"starts_at": datetime.fromisoformat("2026-09-05T20:00:00+02:00")}
    )
    reparsed = Event.model_validate(offset_event.model_dump())

    assert reparsed.starts_at == STARTS_AT
    assert reparsed.starts_at.tzinfo is UTC


def test_prediction_interval_and_opportunity_references_are_validated() -> None:
    prediction_data = build_prediction().model_dump()
    prediction_data["probability_low"] = Decimal("0.31")

    with pytest.raises(ValidationError, match="appartenir à son intervalle"):
        Prediction.model_validate(prediction_data)

    mismatched_market = build_market().model_copy(update={"event_id": OTHER_EVENT_ID})
    opportunity_data = build_opportunity().model_dump()
    opportunity_data["market"] = mismatched_market

    with pytest.raises(ValidationError, match="marché ne référence"):
        Opportunity.model_validate(opportunity_data)


def test_financial_backtest_requires_real_observed_odds() -> None:
    common = {
        "backtest_id": BACKTEST_ID,
        "model_version_id": MODEL_VERSION_ID,
        "kind": BacktestKind.FINANCIAL,
        "starts_at": datetime(2025, 1, 1, tzinfo=UTC),
        "ends_at": datetime(2026, 1, 1, tzinfo=UTC),
        "sample_count": 50,
        "metrics": {"roi": Decimal("0.02")},
        "baseline_metrics": {},
        "observed_odds_count": 0,
        "uses_only_observed_odds": False,
        "final_test_untouched": True,
        "completed_at": datetime(2026, 1, 2, tzinfo=UTC),
    }

    with pytest.raises(ValidationError, match="cotes réellement observées"):
        BacktestSummary.model_validate(common)

    valid = BacktestSummary.model_validate(
        {**common, "observed_odds_count": 50, "uses_only_observed_odds": True}
    )

    assert valid.validation_scheme == "walk_forward"


def test_model_champion_requires_promotion_provenance() -> None:
    with pytest.raises(ValidationError, match="motif de promotion"):
        ModelSummary(
            model_version_id=MODEL_VERSION_ID,
            model_version="mw-v1",
            game_title=GameTitle.LEAGUE_OF_LEGENDS,
            market_type=MarketType.MATCH_WINNER,
            algorithm="logistic-regression",
            feature_version="features-v1",
            dataset_hash="a" * 64,
            artifact_hash="b" * 64,
            code_commit="abcdef1",
            train_cutoff=OBSERVED_AT,
            status=ModelStatus.CHAMPION,
            metrics={"log_loss": Decimal("0.61")},
            baseline_metrics={"log_loss": Decimal("0.69")},
            created_at=OBSERVED_AT,
        )


def test_paper_settlement_and_mapping_decisions_keep_provenance() -> None:
    with pytest.raises(ValidationError, match="règlement paper"):
        PaperBet(
            paper_bet_id=PAPER_BET_ID,
            signal_id=SIGNAL_ID,
            prediction_id=PREDICTION_ID,
            odds_snapshot_id=ODDS_SNAPSHOT_ID,
            entry_odds=Decimal("4.0"),
            stake_amount=Decimal("10"),
            currency="EUR",
            placed_at=OBSERVED_AT,
            status=PaperBetStatus.WON,
            settlement_rules_version="match-winner-v1",
        )

    candidate = MappingCandidate(
        event_id=EVENT_ID,
        label="Team A — Team B",
        confidence=Decimal("0.78"),
        reasons=("participants proches",),
    )
    with pytest.raises(ValidationError, match="provenance de décision"):
        MappingReview(
            mapping_review_id=MAPPING_REVIEW_ID,
            provider="licensed-provider",
            provider_event_id="provider-event-1",
            raw_competition="Example League",
            raw_participants=("Team A", "Team B"),
            candidates=(candidate,),
            status=MappingReviewStatus.APPROVED,
            created_at=OBSERVED_AT,
        )


def test_contract_package_has_no_orm_or_bookmaker_html_dependency() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8").casefold() for path in CONTRACT_ROOT.glob("*.py")
    )

    assert "sqlalchemy" not in source
    assert "selenium" not in source
    assert "beautifulsoup" not in source
    assert "stakeauthorizedprovider" not in source
