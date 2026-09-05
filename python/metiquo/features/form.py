"""Forme récente multi-fenêtres sans imputation silencieuse."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from uuid import UUID

from metiquo.features.rating import EloParameters, EloRatingCalculator, RatingTransition
from metiquo.features.registry import FeatureDefinitionSpec, FeatureValue
from metiquo.features.temporal import AsOfGameBatch, HistoricalGame

_QUANTUM = Decimal("0.000001")
_CODE_VERSION = "recent-form-v1"


@dataclass(frozen=True, slots=True)
class RecentFormParameters:
    game_windows: tuple[int, ...] = (5, 10, 20)
    day_windows: tuple[int, ...] = (30, 60, 90)
    ewm_half_life_games: Decimal = Decimal("5")
    trend_window: int = 20
    opponent_window: int = 20
    version: str = "recent-form-v1"

    def __post_init__(self) -> None:
        _positive_unique("game_windows", self.game_windows)
        _positive_unique("day_windows", self.day_windows)
        if not self.ewm_half_life_games.is_finite() or self.ewm_half_life_games <= 0:
            raise ValueError("ewm_half_life_games doit être fini et positif")
        if self.trend_window < 2 or self.opponent_window < 1:
            raise ValueError("fenêtres tendance/adversaire invalides")
        if not self.version.strip():
            raise ValueError("version de forme récente requise")

    def document(self) -> dict[str, object]:
        return {
            "day_windows": list(self.day_windows),
            "ewm_half_life_games": str(self.ewm_half_life_games),
            "game_windows": list(self.game_windows),
            "opponent_window": self.opponent_window,
            "trend_window": self.trend_window,
        }


@dataclass(frozen=True, slots=True)
class FormWindow:
    observed_games: int
    usable_games: int
    win_rate: Decimal | None
    completeness: Decimal | None


@dataclass(frozen=True, slots=True)
class TeamRecentForm:
    team_id: UUID
    game_windows: Mapping[int, FormWindow]
    day_windows: Mapping[int, FormWindow]
    ewm_win_rate: Decimal | None
    trend: Decimal | None
    volatility: Decimal | None
    opponent_rating: Decimal | None
    usable_games: int
    trend_window: int
    opponent_window: int


@dataclass(frozen=True, slots=True)
class RecentFormFeatureResult:
    parameters_version: str
    cutoff_at: datetime
    max_input_time: datetime | None
    team_a: TeamRecentForm
    team_b: TeamRecentForm

    @property
    def values(self) -> Mapping[str, FeatureValue]:
        values: dict[str, FeatureValue] = {}
        _write_team_values(values, "team_a", self.team_a)
        _write_team_values(values, "team_b", self.team_b)
        return MappingProxyType(values)


@dataclass(frozen=True, slots=True)
class _FormObservation:
    game_id: UUID
    event_time: datetime
    result: Decimal | None
    opponent_rating: Decimal | None


def recent_form_feature_definitions(
    parameters: RecentFormParameters | None = None,
) -> tuple[FeatureDefinitionSpec, ...]:
    """Déclarer chaque sortie et sa disponibilité dans le registre."""

    resolved = parameters or RecentFormParameters()
    optional_names: list[str] = []
    required_names: list[str] = []
    for team in ("team_a", "team_b"):
        for window in resolved.game_windows:
            optional_names.extend(
                (
                    f"form.{team}.win_rate_games_{window}",
                    f"form.{team}.completeness_games_{window}",
                )
            )
        for window in resolved.day_windows:
            optional_names.extend(
                (
                    f"form.{team}.win_rate_days_{window}",
                    f"form.{team}.completeness_days_{window}",
                )
            )
        optional_names.extend(
            (
                f"form.{team}.ewm_win_rate",
                f"form.{team}.trend_{resolved.trend_window}",
                f"form.{team}.volatility_{resolved.trend_window}",
                f"form.{team}.opponent_rating_{resolved.opponent_window}",
            )
        )
        required_names.append(f"form.{team}.usable_games")
    document = resolved.document()
    return tuple(
        FeatureDefinitionSpec(
            name=name,
            domain="form",
            definition_version=resolved.version,
            parameters=document,
            availability="optional" if name in optional_names else "required",
            code_version=_CODE_VERSION,
        )
        for name in (*optional_names, *required_names)
    )


class RecentFormCalculator:
    """Calculer la forme depuis les résultats disponibles strictement avant cutoff."""

    def __init__(
        self,
        parameters: RecentFormParameters | None = None,
        *,
        elo_parameters: EloParameters | None = None,
    ) -> None:
        self._parameters = parameters or RecentFormParameters()
        self._elo_parameters = elo_parameters or EloParameters()

    def calculate(
        self,
        batch: AsOfGameBatch,
        *,
        team_a_id: UUID,
        team_b_id: UUID,
    ) -> RecentFormFeatureResult:
        rating = EloRatingCalculator(self._elo_parameters).calculate(
            batch,
            team_a_id=team_a_id,
            team_b_id=team_b_id,
        )
        opponent_ratings = _opponent_ratings(rating.transitions)
        observations = _observations(batch.games, opponent_ratings)
        return RecentFormFeatureResult(
            parameters_version=self._parameters.version,
            cutoff_at=batch.audit.cutoff_at,
            max_input_time=batch.audit.max_input_time,
            team_a=self._team_form(observations.get(team_a_id, ()), team_a_id, batch),
            team_b=self._team_form(observations.get(team_b_id, ()), team_b_id, batch),
        )

    def _team_form(
        self,
        observations: Sequence[_FormObservation],
        team_id: UUID,
        batch: AsOfGameBatch,
    ) -> TeamRecentForm:
        ordered = tuple(sorted(observations, key=lambda item: (item.event_time, item.game_id)))
        game_windows = {size: _window(ordered[-size:]) for size in self._parameters.game_windows}
        day_windows = {
            days: _window(
                tuple(
                    item
                    for item in ordered
                    if item.event_time >= batch.audit.cutoff_at - timedelta(days=days)
                )
            )
            for days in self._parameters.day_windows
        }
        usable = tuple(item for item in ordered if item.result is not None)
        recent = usable[-self._parameters.trend_window :]
        opponents = tuple(
            item.opponent_rating
            for item in usable[-self._parameters.opponent_window :]
            if item.opponent_rating is not None
        )
        return TeamRecentForm(
            team_id=team_id,
            game_windows=MappingProxyType(game_windows),
            day_windows=MappingProxyType(day_windows),
            ewm_win_rate=_ewm(tuple(item.result for item in usable), self._parameters),
            trend=_trend(tuple(item.result for item in recent)),
            volatility=_volatility(tuple(item.result for item in recent)),
            opponent_rating=_mean(opponents),
            usable_games=len(usable),
            trend_window=self._parameters.trend_window,
            opponent_window=self._parameters.opponent_window,
        )


def _observations(
    games: Sequence[HistoricalGame],
    opponent_ratings: Mapping[tuple[UUID, UUID], Decimal],
) -> dict[UUID, tuple[_FormObservation, ...]]:
    grouped: dict[UUID, list[_FormObservation]] = {}
    for game in games:
        for stat in game.team_stats:
            result = (
                Decimal(int(stat.result))
                if game.usable_for_training and stat.result is not None
                else None
            )
            grouped.setdefault(stat.team_id, []).append(
                _FormObservation(
                    game_id=game.game_id,
                    event_time=game.event_time,
                    result=result,
                    opponent_rating=opponent_ratings.get((game.game_id, stat.team_id)),
                )
            )
    return {team_id: tuple(values) for team_id, values in grouped.items()}


def _opponent_ratings(
    transitions: Sequence[RatingTransition],
) -> Mapping[tuple[UUID, UUID], Decimal]:
    values: dict[tuple[UUID, UUID], Decimal] = {}
    for transition in transitions:
        values[(transition.game_id, transition.team_a_id)] = transition.team_b_before
        values[(transition.game_id, transition.team_b_id)] = transition.team_a_before
    return values


def _window(observations: Sequence[_FormObservation]) -> FormWindow:
    results = tuple(item.result for item in observations if item.result is not None)
    return FormWindow(
        observed_games=len(observations),
        usable_games=len(results),
        win_rate=_mean(results),
        completeness=(_decimal_ratio(len(results), len(observations)) if observations else None),
    )


def _ewm(results: tuple[Decimal | None, ...], parameters: RecentFormParameters) -> Decimal | None:
    observed = tuple(value for value in results if value is not None)
    if not observed:
        return None
    half_life = float(parameters.ewm_half_life_games)
    weighted = 0.0
    total = 0.0
    for age, value in enumerate(reversed(observed)):
        weight = math.pow(0.5, age / half_life)
        weighted += float(value) * weight
        total += weight
    return _decimal(weighted / total)


def _trend(results: tuple[Decimal | None, ...]) -> Decimal | None:
    observed = tuple(value for value in results if value is not None)
    if len(observed) < 2:
        return None
    mean_x = Decimal(len(observed) - 1) / Decimal(2)
    mean_y = sum(observed, Decimal()) / Decimal(len(observed))
    numerator = sum(
        (Decimal(index) - mean_x) * (value - mean_y) for index, value in enumerate(observed)
    )
    denominator = sum(
        ((Decimal(index) - mean_x) ** 2 for index in range(len(observed))),
        Decimal(),
    )
    return _quantize(numerator / denominator)


def _volatility(results: tuple[Decimal | None, ...]) -> Decimal | None:
    observed = tuple(value for value in results if value is not None)
    if len(observed) < 2:
        return None
    mean = sum(observed, Decimal()) / Decimal(len(observed))
    variance = sum(((value - mean) ** 2 for value in observed), Decimal()) / Decimal(len(observed))
    return _decimal(math.sqrt(float(variance)))


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return _quantize(sum(values, Decimal()) / Decimal(len(values)))


def _decimal_ratio(numerator: int, denominator: int) -> Decimal:
    return _quantize(Decimal(numerator) / Decimal(denominator))


def _decimal(value: float) -> Decimal:
    return _quantize(Decimal(str(value)))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def _positive_unique(name: str, values: tuple[int, ...]) -> None:
    if not values or any(value <= 0 for value in values) or len(values) != len(set(values)):
        raise ValueError(f"{name} doit contenir des entiers positifs uniques")


def _write_team_values(
    target: dict[str, FeatureValue],
    label: str,
    form: TeamRecentForm,
) -> None:
    for size, window in form.game_windows.items():
        target[f"form.{label}.win_rate_games_{size}"] = window.win_rate
        target[f"form.{label}.completeness_games_{size}"] = window.completeness
    for days, window in form.day_windows.items():
        target[f"form.{label}.win_rate_days_{days}"] = window.win_rate
        target[f"form.{label}.completeness_days_{days}"] = window.completeness
    target[f"form.{label}.ewm_win_rate"] = form.ewm_win_rate
    target[f"form.{label}.trend_{form.trend_window}"] = form.trend
    target[f"form.{label}.volatility_{form.trend_window}"] = form.volatility
    target[f"form.{label}.opponent_rating_{form.opponent_window}"] = form.opponent_rating
    target[f"form.{label}.usable_games"] = form.usable_games
