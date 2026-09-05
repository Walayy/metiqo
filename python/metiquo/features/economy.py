"""Économie, rythme et objectifs activés uniquement par capability."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from uuid import UUID

from metiquo.canonical.capabilities import CapabilityState
from metiquo.features.registry import FeatureDefinitionSpec, FeatureValue
from metiquo.features.temporal import AsOfGameBatch, FeatureCutoff, HistoricalGame

_QUANTUM = Decimal("0.000001")
_CODE_VERSION = "economy-objectives-v1"


@dataclass(frozen=True, slots=True)
class EconomyParameters:
    timestamps: tuple[int, ...] = (10, 15, 20, 25)
    pace_capability: str = "feature.pace"
    timed_capability: str = "feature.economy_timestamps"
    objective_total_capability: str = "feature.objectives_total"
    objective_first_capability: str = "feature.objectives_first"
    version: str = "economy-objectives-v1"

    def __post_init__(self) -> None:
        if (
            not self.timestamps
            or any(value <= 0 for value in self.timestamps)
            or len(self.timestamps) != len(set(self.timestamps))
        ):
            raise ValueError("timestamps doit contenir des minutes positives uniques")
        if any(
            not value.strip()
            for value in (
                self.pace_capability,
                self.timed_capability,
                self.objective_total_capability,
                self.objective_first_capability,
                self.version,
            )
        ):
            raise ValueError("capacités et version économie requises")

    def document(self) -> dict[str, object]:
        return {
            "objective_first_capability": self.objective_first_capability,
            "objective_total_capability": self.objective_total_capability,
            "pace_capability": self.pace_capability,
            "timed_capability": self.timed_capability,
            "timestamps": list(self.timestamps),
        }


@dataclass(frozen=True, slots=True)
class TeamEconomyMetrics:
    team_id: UUID
    pace_games: int
    kills_per_minute: Decimal | None
    duration_seconds: Decimal | None
    timed_means: Mapping[str, Decimal | None]
    timed_games: Mapping[str, int]
    conversion_rate: Decimal | None
    conversion_games: int
    comeback_rate: Decimal | None
    comeback_games: int
    objective_rates: Mapping[str, Decimal | None]
    objective_games: Mapping[str, int]
    first_objective_rates: Mapping[str, Decimal | None]
    first_objective_games: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class EconomyFeatureResult:
    parameters_version: str
    cutoff_at: datetime
    max_input_time: datetime | None
    availability: Mapping[str, bool]
    team_a: TeamEconomyMetrics
    team_b: TeamEconomyMetrics

    @property
    def values(self) -> Mapping[str, FeatureValue]:
        values: dict[str, FeatureValue] = {
            f"{group}.available": available for group, available in self.availability.items()
        }
        _write_team(values, "team_a", self.team_a)
        _write_team(values, "team_b", self.team_b)
        return MappingProxyType(values)


def economy_feature_definitions(
    parameters: EconomyParameters | None = None,
) -> tuple[FeatureDefinitionSpec, ...]:
    """Déclarer sorties, indicateurs et capacités requises."""

    resolved = parameters or EconomyParameters()
    document = resolved.document()
    definitions = [
        _definition("economy.pace.available", resolved.pace_capability, resolved, document, True),
        _definition("economy.timed.available", resolved.timed_capability, resolved, document, True),
        _definition(
            "objectives.total.available",
            resolved.objective_total_capability,
            resolved,
            document,
            True,
        ),
        _definition(
            "objectives.first.available",
            resolved.objective_first_capability,
            resolved,
            document,
            True,
        ),
    ]
    for team in ("team_a", "team_b"):
        for name in ("pace_games", "kills_per_minute", "duration_seconds"):
            definitions.append(
                _definition(f"economy.{team}.{name}", resolved.pace_capability, resolved, document)
            )
        for metric in ("gold", "xp", "cs"):
            for minute in resolved.timestamps:
                prefix = f"economy.{team}.{metric}_diff_at_{minute}"
                definitions.extend(
                    (
                        _definition(prefix, resolved.timed_capability, resolved, document),
                        _definition(
                            f"{prefix}_games", resolved.timed_capability, resolved, document
                        ),
                    )
                )
        for name in (
            "conversion_rate",
            "conversion_games",
            "comeback_rate",
            "comeback_games",
        ):
            definitions.append(
                _definition(f"economy.{team}.{name}", resolved.timed_capability, resolved, document)
            )
        for objective in ("towers", "dragons", "barons"):
            prefix = f"objectives.{team}.{objective}"
            definitions.extend(
                (
                    _definition(
                        f"{prefix}_per_minute",
                        resolved.objective_total_capability,
                        resolved,
                        document,
                    ),
                    _definition(
                        f"{prefix}_games",
                        resolved.objective_total_capability,
                        resolved,
                        document,
                    ),
                )
            )
        for objective in ("blood", "tower", "dragon", "herald", "baron"):
            prefix = f"objectives.{team}.first_{objective}"
            definitions.extend(
                (
                    _definition(
                        f"{prefix}_rate",
                        resolved.objective_first_capability,
                        resolved,
                        document,
                    ),
                    _definition(
                        f"{prefix}_games",
                        resolved.objective_first_capability,
                        resolved,
                        document,
                    ),
                )
            )
    return tuple(definitions)


class EconomyFeatureCalculator:
    """Calculer uniquement les groupes explicitement enabled pour le snapshot."""

    def __init__(self, parameters: EconomyParameters | None = None) -> None:
        self._parameters = parameters or EconomyParameters()

    def calculate(
        self,
        batch: AsOfGameBatch,
        *,
        team_a_id: UUID,
        team_b_id: UUID,
        capabilities: Mapping[str, CapabilityState | str],
    ) -> EconomyFeatureResult:
        if team_a_id == team_b_id:
            raise ValueError("les deux équipes cibles doivent être distinctes")
        FeatureCutoff(batch.audit.cutoff_at).audit(
            (game.event_time for game in batch.games),
            source_knowledge_times=(
                timestamp
                for game in batch.games
                for timestamp in (
                    game.source_processed_at,
                    *(stat.source_processed_at for stat in game.team_stats),
                )
            ),
        )
        availability = MappingProxyType(
            {
                "economy.pace": _enabled(capabilities, self._parameters.pace_capability),
                "economy.timed": _enabled(capabilities, self._parameters.timed_capability),
                "objectives.total": _enabled(
                    capabilities, self._parameters.objective_total_capability
                ),
                "objectives.first": _enabled(
                    capabilities, self._parameters.objective_first_capability
                ),
            }
        )
        return EconomyFeatureResult(
            parameters_version=self._parameters.version,
            cutoff_at=batch.audit.cutoff_at,
            max_input_time=batch.audit.max_input_time,
            availability=availability,
            team_a=_team_metrics(batch.games, team_a_id, availability, self._parameters.timestamps),
            team_b=_team_metrics(batch.games, team_b_id, availability, self._parameters.timestamps),
        )


def _team_metrics(
    games: Sequence[HistoricalGame],
    team_id: UUID,
    availability: Mapping[str, bool],
    timestamps: tuple[int, ...],
) -> TeamEconomyMetrics:
    observations = tuple(
        (game, stat)
        for game in games
        if game.usable_for_training
        for stat in game.team_stats
        if stat.team_id == team_id
    )
    durations = tuple(
        Decimal(game.game_length_seconds)
        for game, _ in observations
        if game.game_length_seconds is not None
    )
    kills_per_minute = tuple(
        _per_minute(stat.kills, game.game_length_seconds)
        for game, stat in observations
        if stat.kills is not None and game.game_length_seconds is not None
    )
    if not availability["economy.pace"]:
        durations = ()
        kills_per_minute = ()
    timed_names = tuple(
        f"{metric}_diff_at_{minute}" for metric in ("gold", "xp", "cs") for minute in timestamps
    )
    timed_values = {
        name: tuple(
            Decimal(value)
            for _, stat in observations
            if (value := stat.stats.get(name)) is not None and not isinstance(value, bool)
        )
        if availability["economy.timed"]
        else ()
        for name in timed_names
    }
    gold_at_15 = tuple(
        (Decimal(value), stat.result)
        for _, stat in observations
        if availability["economy.timed"]
        and (value := stat.stats.get("gold_diff_at_15")) is not None
        and not isinstance(value, bool)
        and stat.result is not None
    )
    conversions = tuple(Decimal(int(result)) for value, result in gold_at_15 if value > 0)
    comebacks = tuple(Decimal(int(result)) for value, result in gold_at_15 if value < 0)
    objective_values = {
        name: tuple(
            _per_minute(getattr(stat, name), game.game_length_seconds)
            for game, stat in observations
            if getattr(stat, name) is not None and game.game_length_seconds is not None
        )
        if availability["objectives.total"]
        else ()
        for name in ("towers", "dragons", "barons")
    }
    first_values = {
        name: tuple(
            Decimal(int(value))
            for _, stat in observations
            if (value := stat.stats.get(name)) is not None and isinstance(value, bool)
        )
        if availability["objectives.first"]
        else ()
        for name in ("first_blood", "first_tower", "first_dragon", "first_herald", "first_baron")
    }
    return TeamEconomyMetrics(
        team_id=team_id,
        pace_games=len(kills_per_minute),
        kills_per_minute=_mean(kills_per_minute),
        duration_seconds=_mean(durations),
        timed_means=MappingProxyType(
            {name: _mean(values) for name, values in timed_values.items()}
        ),
        timed_games=MappingProxyType({name: len(values) for name, values in timed_values.items()}),
        conversion_rate=_mean(conversions),
        conversion_games=len(conversions),
        comeback_rate=_mean(comebacks),
        comeback_games=len(comebacks),
        objective_rates=MappingProxyType(
            {name: _mean(values) for name, values in objective_values.items()}
        ),
        objective_games=MappingProxyType(
            {name: len(values) for name, values in objective_values.items()}
        ),
        first_objective_rates=MappingProxyType(
            {name: _mean(values) for name, values in first_values.items()}
        ),
        first_objective_games=MappingProxyType(
            {name: len(values) for name, values in first_values.items()}
        ),
    )


def _enabled(capabilities: Mapping[str, CapabilityState | str], name: str) -> bool:
    value = capabilities.get(name)
    status = value.status if isinstance(value, CapabilityState) else value
    return status == "enabled"


def _per_minute(value: int | None, duration_seconds: int | None) -> Decimal:
    if value is None or duration_seconds is None or duration_seconds <= 0:
        raise ValueError("une statistique par minute exige valeur et durée positive")
    return _quantize(Decimal(value) / (Decimal(duration_seconds) / Decimal(60)))


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return _quantize(sum(values, Decimal()) / Decimal(len(values)))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def _definition(
    name: str,
    capability: str,
    parameters: EconomyParameters,
    document: Mapping[str, object],
    availability_indicator: bool = False,
) -> FeatureDefinitionSpec:
    return FeatureDefinitionSpec(
        name=name,
        domain="economy" if name.startswith("economy.") else "objectives",
        definition_version=parameters.version,
        parameters=document,
        availability="required" if availability_indicator else "capability_gated",
        required_capability=None if availability_indicator else capability,
        code_version=_CODE_VERSION,
    )


def _write_team(
    target: dict[str, FeatureValue],
    label: str,
    metrics: TeamEconomyMetrics,
) -> None:
    target[f"economy.{label}.pace_games"] = metrics.pace_games
    target[f"economy.{label}.kills_per_minute"] = metrics.kills_per_minute
    target[f"economy.{label}.duration_seconds"] = metrics.duration_seconds
    for name, value in metrics.timed_means.items():
        target[f"economy.{label}.{name}"] = value
        target[f"economy.{label}.{name}_games"] = metrics.timed_games[name]
    target[f"economy.{label}.conversion_rate"] = metrics.conversion_rate
    target[f"economy.{label}.conversion_games"] = metrics.conversion_games
    target[f"economy.{label}.comeback_rate"] = metrics.comeback_rate
    target[f"economy.{label}.comeback_games"] = metrics.comeback_games
    for name, value in metrics.objective_rates.items():
        target[f"objectives.{label}.{name}_per_minute"] = value
        target[f"objectives.{label}.{name}_games"] = metrics.objective_games[name]
    for name, value in metrics.first_objective_rates.items():
        target[f"objectives.{label}.{name}_rate"] = value
        target[f"objectives.{label}.{name}_games"] = metrics.first_objective_games[name]
