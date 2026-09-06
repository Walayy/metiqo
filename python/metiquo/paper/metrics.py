"""Mesures financières du ledger observé, échantillons et incertitude temporelle."""

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import combinations
from random import Random
from types import MappingProxyType
from uuid import UUID

from metiquo.contracts import PaperBet
from metiquo.contracts.enums import PaperBetStatus as Status
from metiquo.paper.creation import decimal_text

FINANCIAL_METHOD_VERSION = "paper-finance-v1"
_TERMINAL = frozenset({Status.WON, Status.LOST, Status.PUSH, Status.VOID})


@dataclass(frozen=True, slots=True)
class FinancialObservation:
    bet: PaperBet
    event_id: UUID
    market: str
    competition: str
    model_version: str
    grade: str
    announced_ev: Decimal
    clv: Decimal | None
    quote_fingerprint: str


@dataclass(frozen=True, slots=True)
class Estimate:
    value: Decimal | None
    sample_size: int
    unavailable_reason: str | None = None

    def document(self) -> dict[str, object]:
        return {
            "value": decimal_text(self.value) if self.value is not None else None,
            "sampleSize": self.sample_size,
            "unavailableReason": self.unavailable_reason,
        }


@dataclass(frozen=True, slots=True)
class Segment:
    dimension: str
    key: str
    sample_size: int
    turnover: Decimal
    profit_loss: Decimal
    yield_value: Decimal | None


@dataclass(frozen=True, slots=True)
class ReturnCorrelation:
    left: str
    right: str
    estimate: Estimate


@dataclass(frozen=True, slots=True)
class EventExposure:
    event_id: UUID
    bets: int
    stake: Decimal


@dataclass(frozen=True, slots=True)
class FinancialMetrics:
    currency: str
    signals: int
    bets: int
    settled: int
    open: int
    pending_review: int
    estimates: Mapping[str, Estimate]
    segments: tuple[Segment, ...]
    correlations: tuple[ReturnCorrelation, ...]
    event_exposure: tuple[EventExposure, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "estimates", MappingProxyType(dict(self.estimates)))

    def document(self) -> dict[str, object]:
        return {
            "methodVersion": FINANCIAL_METHOD_VERSION,
            "currency": self.currency,
            "signals": self.signals,
            "bets": self.bets,
            "settled": self.settled,
            "open": self.open,
            "pendingReview": self.pending_review,
            "estimates": {name: value.document() for name, value in self.estimates.items()},
            "segments": [
                {
                    "dimension": s.dimension,
                    "key": s.key,
                    "sampleSize": s.sample_size,
                    "turnover": decimal_text(s.turnover),
                    "profitLoss": decimal_text(s.profit_loss),
                    "yield": decimal_text(s.yield_value) if s.yield_value is not None else None,
                }
                for s in self.segments
            ],
            "correlations": [
                {"left": c.left, "right": c.right, **c.estimate.document()}
                for c in self.correlations
            ],
            "eventExposure": [
                {"eventId": str(e.event_id), "bets": e.bets, "stake": decimal_text(e.stake)}
                for e in self.event_exposure
            ],
            "bootstrap": {
                "unit": "UTC entry day",
                "replicates": 2000,
                "seed": 42,
                "confidenceLevel": "0.95",
            },
        }


class FinancialMetricsEngine:
    def calculate(
        self, observations: Sequence[FinancialObservation], *, signals_count: int, currency: str
    ) -> FinancialMetrics:
        items = tuple(sorted(observations, key=lambda item: str(item.bet.paper_bet_id)))
        if signals_count < len(items) or len({i.bet.paper_bet_id for i in items}) != len(items):
            raise ValueError(
                "Le ledger exige des décisions uniques et un compte de signaux complet"
            )
        for item in items:
            if re.fullmatch(r"[0-9a-f]{64}", item.quote_fingerprint) is None:
                raise ValueError("La provenance des cotes observées est requise")
            if item.bet.currency != currency:
                raise ValueError(
                    "Les devises ne peuvent pas être agrégées sans conversion observée"
                )
            if not item.announced_ev.is_finite() or (
                item.clv is not None and not item.clv.is_finite()
            ):
                raise ValueError("Les mesures doivent être finies")
        closed = tuple(i for i in items if i.bet.status in _TERMINAL)
        risked = tuple(i for i in closed if i.bet.status is not Status.VOID)
        decided = tuple(i for i in closed if i.bet.status in {Status.WON, Status.LOST})
        outstanding = tuple(i for i in items if i.bet.status not in _TERMINAL)
        turnover = _stake(items)
        settled_turnover = _stake(risked)
        pnl = _pnl(closed)
        metrics: dict[str, Estimate] = {
            "turnover": Estimate(turnover, len(items)),
            "settled_turnover": Estimate(settled_turnover, len(risked)),
            "profit_loss": Estimate(pnl, len(closed)),
            "yield": _ratio(pnl, settled_turnover, len(risked)),
            "hit_rate": _ratio(
                Decimal(sum(i.bet.status is Status.WON for i in decided)),
                Decimal(len(decided)),
                len(decided),
            ),
            "hit_rate_mean_odds": _mean(tuple(i.bet.entry_odds for i in decided)),
            "void_rate": _ratio(
                Decimal(sum(i.bet.status is Status.VOID for i in closed)),
                Decimal(len(closed)),
                len(closed),
            ),
            "open_exposure": Estimate(_stake(outstanding), len(outstanding)),
            "clv": _mean(tuple(i.clv for i in items if i.clv is not None)),
        }
        metrics["roi"] = metrics["yield"]
        returns = tuple((i.bet.profit_loss or Decimal()) / i.bet.stake_amount for i in risked)
        metrics["return_volatility"] = _volatility(returns)
        announced = sum((i.bet.stake_amount * i.announced_ev for i in risked), Decimal())
        metrics["announced_ev"] = _ratio(announced, settled_turnover, len(risked))
        metrics["realized_minus_announced"] = _ratio(pnl - announced, settled_turnover, len(risked))
        equity = peak = drawdown = Decimal()
        for item in sorted(
            closed, key=lambda i: (i.bet.settled_at or i.bet.placed_at, str(i.bet.paper_bet_id))
        ):
            equity += item.bet.profit_loss or Decimal()
            peak = max(peak, equity)
            drawdown = max(drawdown, peak - equity)
        metrics["max_drawdown"] = Estimate(
            drawdown if closed else None, len(closed), None if closed else "NO_SETTLEMENTS"
        )
        exposure = maximum = Decimal()
        events: list[tuple[datetime, int, Decimal]] = []
        for item in items:
            events.append((item.bet.placed_at, 1, item.bet.stake_amount))
            if item.bet.settled_at is not None:
                events.append((item.bet.settled_at, 0, -item.bet.stake_amount))
        for _, _, change in sorted(events):
            exposure += change
            maximum = max(maximum, exposure)
        metrics["max_simultaneous_exposure"] = Estimate(maximum, len(items))
        low, high = _bootstrap(risked)
        metrics["yield_ci_low"], metrics["yield_ci_high"] = low, high
        group: dict[UUID, list[FinancialObservation]] = defaultdict(list)
        for item in outstanding:
            group[item.event_id].append(item)
        return FinancialMetrics(
            currency,
            signals_count,
            len(items),
            len(closed),
            sum(i.bet.status is Status.OPEN for i in items),
            sum(i.bet.status is Status.PENDING_REVIEW for i in items),
            metrics,
            _segments(items),
            _correlations(risked),
            tuple(
                EventExposure(key, len(values), _stake(values))
                for key, values in sorted(group.items())
            ),
        )


def _stake(items: Sequence[FinancialObservation]) -> Decimal:
    return sum((i.bet.stake_amount for i in items), Decimal())


def _pnl(items: Sequence[FinancialObservation]) -> Decimal:
    return sum((i.bet.profit_loss or Decimal() for i in items), Decimal())


def _ratio(numerator: Decimal, denominator: Decimal, n: int) -> Estimate:
    return Estimate(
        numerator / denominator if denominator else None,
        n,
        None if denominator else "NO_ELIGIBLE_OBSERVATIONS",
    )


def _mean(values: tuple[Decimal, ...]) -> Estimate:
    return _ratio(sum(values, Decimal()), Decimal(len(values)), len(values))


def _volatility(values: tuple[Decimal, ...]) -> Estimate:
    if len(values) < 2:
        return Estimate(None, len(values), "INSUFFICIENT_OBSERVATIONS")
    mean = sum(values, Decimal()) / len(values)
    return Estimate(
        (sum(((v - mean) ** 2 for v in values), Decimal()) / (len(values) - 1)).sqrt(), len(values)
    )


def _daily(items: Sequence[FinancialObservation]) -> dict[date, tuple[Decimal, Decimal]]:
    totals: dict[date, tuple[Decimal, Decimal]] = {}
    for item in items:
        day = item.bet.placed_at.date()
        stake, pnl = totals.get(day, (Decimal(), Decimal()))
        totals[day] = stake + item.bet.stake_amount, pnl + (item.bet.profit_loss or Decimal())
    return totals


def _bootstrap(items: tuple[FinancialObservation, ...]) -> tuple[Estimate, Estimate]:
    blocks = tuple(value for _, value in sorted(_daily(items).items()))
    n = len(blocks)
    if n < 2:
        unavailable = Estimate(None, n, "INSUFFICIENT_TEMPORAL_BLOCKS")
        return unavailable, unavailable
    rng = Random(42)
    results: list[Decimal] = []
    for _ in range(2000):
        sample = [blocks[rng.randrange(n)] for _ in blocks]
        results.append(
            sum((p for _, p in sample), Decimal()) / sum((s for s, _ in sample), Decimal())
        )
    results.sort()
    return Estimate(results[49], n), Estimate(results[1949], n)


def _segments(items: tuple[FinancialObservation, ...]) -> tuple[Segment, ...]:
    groups: dict[tuple[str, str], list[FinancialObservation]] = defaultdict(list)
    for item in items:
        bucket = (
            "favorite"
            if item.bet.entry_odds < 2
            else "standard"
            if item.bet.entry_odds < 4
            else "longshot"
        )
        for dimension, key in (
            ("market", item.market),
            ("competition", item.competition),
            ("model", item.model_version),
            ("odds_bucket", bucket),
            ("grade", item.grade),
        ):
            groups[dimension, key].append(item)
    output: list[Segment] = []
    for (dimension, key), group in sorted(groups.items()):
        closed = tuple(
            i for i in group if i.bet.status in _TERMINAL and i.bet.status is not Status.VOID
        )
        turnover, pnl = _stake(closed), _pnl(closed)
        output.append(
            Segment(dimension, key, len(group), turnover, pnl, pnl / turnover if turnover else None)
        )
    return tuple(output)


def _correlations(items: tuple[FinancialObservation, ...]) -> tuple[ReturnCorrelation, ...]:
    groups: dict[str, list[FinancialObservation]] = defaultdict(list)
    for item in items:
        groups[item.competition].append(item)
    days = {key: _daily(group) for key, group in groups.items()}
    output: list[ReturnCorrelation] = []
    for left, right in combinations(sorted(days), 2):
        common = sorted(days[left].keys() & days[right].keys())
        if len(common) < 3:
            estimate = Estimate(None, len(common), "INSUFFICIENT_PAIRED_DAYS")
        else:
            a = [days[left][d][1] / days[left][d][0] for d in common]
            b = [days[right][d][1] / days[right][d][0] for d in common]
            mean_a, mean_b = sum(a, Decimal()) / len(a), sum(b, Decimal()) / len(b)
            cross = sum(((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True)), Decimal())
            scale = (
                sum(((x - mean_a) ** 2 for x in a), Decimal())
                * sum(((y - mean_b) ** 2 for y in b), Decimal())
            ).sqrt()
            estimate = Estimate(
                max(Decimal(-1), min(Decimal(1), cross / scale)) if scale else None,
                len(common),
                None if scale else "ZERO_RETURN_VARIANCE",
            )
        output.append(ReturnCorrelation(left, right, estimate))
    return tuple(output)
