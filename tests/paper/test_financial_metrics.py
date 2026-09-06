"""Petit ledger calculable à la main, pertes incluses et incertitude explicite."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from metiquo.contracts import PaperBet
from metiquo.contracts.enums import PaperBetStatus as Status
from metiquo.paper.metrics import FinancialMetricsEngine, FinancialObservation


def observation(
    index: int,
    status: Status,
    stake: str,
    odds: str,
    pnl: str | None,
    day: int,
    clv: str | None = None,
) -> FinancialObservation:
    placed = datetime(2026, 9, day, 1, tzinfo=UTC) + timedelta(minutes=index)
    bet = PaperBet(
        paper_bet_id=UUID(int=index),
        signal_id=UUID(int=100 + index),
        prediction_id=UUID(int=200 + index),
        odds_snapshot_id=UUID(int=300 + index),
        entry_odds=Decimal(odds),
        stake_amount=Decimal(stake),
        currency="EUR",
        placed_at=placed,
        status=status,
        settlement_rules_version="fixture-v1",
        settled_at=placed + timedelta(hours=12) if pnl is not None else None,
        profit_loss=Decimal(pnl) if pnl is not None else None,
    )
    return FinancialObservation(
        bet,
        UUID(int=day),
        "MATCH_WINNER/SERIES",
        "league-fixture",
        "model-fixture",
        "VALUE",
        Decimal("0.1"),
        Decimal(clv) if clv is not None else None,
        "a" * 64,
    )


def test_financial_metrics_include_losses_voids_and_open_exposure() -> None:
    ledger = (
        observation(1, Status.WON, "10", "3", "20", 1, "0.1"),
        observation(2, Status.LOST, "10", "2", "-10", 1, "-0.2"),
        observation(3, Status.LOST, "20", "2", "-20", 2),
        observation(4, Status.VOID, "5", "2", "0", 3),
        observation(5, Status.OPEN, "10", "8", None, 2),
    )
    engine = FinancialMetricsEngine()
    report = engine.calculate(ledger, signals_count=8, currency="EUR")
    metrics = report.estimates
    assert (report.signals, report.bets, report.settled, report.open) == (8, 5, 4, 1)
    assert metrics["turnover"].value == 55
    assert metrics["settled_turnover"].value == 40
    assert metrics["profit_loss"].value == -10
    assert metrics["yield"].value == Decimal("-0.25")
    assert metrics["hit_rate"].value == Decimal(1) / 3
    assert metrics["hit_rate"].sample_size == 3
    assert metrics["max_drawdown"].value == 30
    assert metrics["return_volatility"].value is not None
    assert abs(metrics["return_volatility"].value ** 2 - 3) < Decimal("1e-20")
    assert metrics["clv"].value == Decimal("-0.05") and metrics["clv"].sample_size == 2
    assert metrics["open_exposure"].value == 10
    assert metrics["void_rate"].value == Decimal("0.25")
    assert metrics["announced_ev"].value == Decimal("0.1")
    assert metrics["realized_minus_announced"].value == Decimal("-0.35")
    assert metrics["yield_ci_low"].value == -1
    assert metrics["yield_ci_high"].value == Decimal("0.5")
    assert metrics["yield_ci_low"].sample_size == 2
    assert report == engine.calculate(ledger, signals_count=8, currency="EUR")
    assert all(segment.sample_size > 0 for segment in report.segments)


def test_empty_report_does_not_invent_roi_or_confidence() -> None:
    report = FinancialMetricsEngine().calculate((), signals_count=0, currency="EUR")
    for name in ("yield", "hit_rate", "clv", "yield_ci_low", "return_volatility"):
        assert report.estimates[name].value is None
        assert report.estimates[name].unavailable_reason
        assert report.estimates[name].sample_size == 0


def test_one_temporal_block_and_unverified_odds_are_explicit() -> None:
    from dataclasses import replace

    item = observation(1, Status.LOST, "10", "2", "-10", 1)
    report = FinancialMetricsEngine().calculate((item,), signals_count=1, currency="EUR")
    assert report.estimates["yield_ci_low"].value is None
    assert report.estimates["yield_ci_low"].sample_size == 1
    with pytest.raises(ValueError, match="provenance"):
        FinancialMetricsEngine().calculate(
            (replace(item, quote_fingerprint=""),), signals_count=1, currency="EUR"
        )


def test_correlations_use_paired_days_and_keep_the_sample_size() -> None:
    from dataclasses import replace

    items: list[FinancialObservation] = []
    for day in range(1, 4):
        won = day % 2 == 1
        left = observation(
            day, Status.WON if won else Status.LOST, "10", "2", "10" if won else "-10", day
        )
        right = observation(
            day + 3, Status.LOST if won else Status.WON, "10", "2", "-10" if won else "10", day
        )
        items.extend((replace(left, competition="left"), replace(right, competition="right")))
    report = FinancialMetricsEngine().calculate(items, signals_count=6, currency="EUR")
    assert len(report.correlations) == 1
    assert report.correlations[0].estimate.value == -1
    assert report.correlations[0].estimate.sample_size == 3
