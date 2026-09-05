"""Force historique par side et scénario cible explicitement inconnu."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from metiquo.features.registry import FeatureDefinitionSpec, FeatureValue
from metiquo.features.temporal import AsOfGameBatch, FeatureCutoff, HistoricalGame

type TargetSide = Literal["Blue", "Red", "unknown"]

_QUANTUM = Decimal("0.000001")
_CODE_VERSION = "side-strength-v1"


@dataclass(frozen=True, slots=True)
class SideParameters:
    prior_win_rate: Decimal = Decimal("0.5")
    prior_games: Decimal = Decimal("4")
    early_stat: str = "gold_diff_at_15"
    version: str = "side-strength-v1"

    def __post_init__(self) -> None:
        if (
            not self.prior_win_rate.is_finite()
            or self.prior_win_rate < 0
            or self.prior_win_rate > 1
        ):
            raise ValueError("prior_win_rate doit appartenir à [0, 1]")
        if not self.prior_games.is_finite() or self.prior_games <= 0:
            raise ValueError("prior_games doit être fini et positif")
        if not self.early_stat.strip() or not self.version.strip():
            raise ValueError("early_stat et version sont requis")

    def document(self) -> dict[str, object]:
        return {
            "early_stat": self.early_stat,
            "prior_games": str(self.prior_games),
            "prior_win_rate": str(self.prior_win_rate),
        }


@dataclass(frozen=True, slots=True)
class SideSample:
    side: Literal["Blue", "Red"]
    games: int
    wins: int
    adjusted_win_rate: Decimal
    early_stat_mean: Decimal | None
    early_stat_games: int


@dataclass(frozen=True, slots=True)
class TeamSideStrength:
    team_id: UUID
    blue: SideSample
    red: SideSample

    @property
    def adjusted_differential(self) -> Decimal:
        return self.blue.adjusted_win_rate - self.red.adjusted_win_rate


@dataclass(frozen=True, slots=True)
class TargetSideScenario:
    team_a_side: TargetSide
    team_b_side: TargetSide
    side_known: bool
    team_a_blue_weight: Decimal
    team_a_red_weight: Decimal


@dataclass(frozen=True, slots=True)
class SideFeatureResult:
    parameters_version: str
    cutoff_at: datetime
    max_input_time: datetime | None
    team_a: TeamSideStrength
    team_b: TeamSideStrength
    target: TargetSideScenario

    @property
    def values(self) -> Mapping[str, FeatureValue]:
        values: dict[str, FeatureValue] = {}
        _write_strength(values, "team_a", self.team_a)
        _write_strength(values, "team_b", self.team_b)
        values.update(
            {
                "side.target.team_a": self.target.team_a_side,
                "side.target.team_b": self.target.team_b_side,
                "side.target.known": self.target.side_known,
                "side.target.team_a_blue_weight": self.target.team_a_blue_weight,
                "side.target.team_a_red_weight": self.target.team_a_red_weight,
            }
        )
        return MappingProxyType(values)


def side_feature_definitions(
    parameters: SideParameters | None = None,
) -> tuple[FeatureDefinitionSpec, ...]:
    """Déclarer les sorties side, dont les statistiques early conditionnelles."""

    resolved = parameters or SideParameters()
    document = resolved.document()
    definitions: list[FeatureDefinitionSpec] = []
    for team in ("team_a", "team_b"):
        for side in ("blue", "red"):
            for metric in ("games", "wins", "adjusted_win_rate"):
                definitions.append(_definition(f"side.{team}.{side}.{metric}", resolved, document))
            definitions.extend(
                (
                    _definition(
                        f"side.{team}.{side}.early_stat_mean",
                        resolved,
                        document,
                        gated=True,
                    ),
                    _definition(
                        f"side.{team}.{side}.early_stat_games",
                        resolved,
                        document,
                        gated=True,
                    ),
                )
            )
        definitions.append(_definition(f"side.{team}.adjusted_differential", resolved, document))
    for name in (
        "side.target.team_a",
        "side.target.team_b",
        "side.target.known",
        "side.target.team_a_blue_weight",
        "side.target.team_a_red_weight",
    ):
        definitions.append(_definition(name, resolved, document))
    return tuple(definitions)


class SideFeatureCalculator:
    """Mesurer chaque side passée sans jamais attribuer la side cible inconnue."""

    def __init__(self, parameters: SideParameters | None = None) -> None:
        self._parameters = parameters or SideParameters()

    def calculate(
        self,
        batch: AsOfGameBatch,
        *,
        team_a_id: UUID,
        team_b_id: UUID,
        target_side_a: TargetSide,
    ) -> SideFeatureResult:
        if team_a_id == team_b_id:
            raise ValueError("les deux équipes cibles doivent être distinctes")
        FeatureCutoff(batch.audit.cutoff_at).audit(
            (game.event_time for game in batch.games),
            source_knowledge_times=(game.source_processed_at for game in batch.games),
        )
        if target_side_a not in {"Blue", "Red", "unknown"}:
            raise ValueError("side cible invalide")
        return SideFeatureResult(
            parameters_version=self._parameters.version,
            cutoff_at=batch.audit.cutoff_at,
            max_input_time=batch.audit.max_input_time,
            team_a=self._strength(batch.games, team_a_id),
            team_b=self._strength(batch.games, team_b_id),
            target=_target_scenario(target_side_a),
        )

    def _strength(
        self,
        games: Sequence[HistoricalGame],
        team_id: UUID,
    ) -> TeamSideStrength:
        samples = {
            side: _sample(games, team_id, side, self._parameters) for side in ("Blue", "Red")
        }
        return TeamSideStrength(team_id, samples["Blue"], samples["Red"])


def _sample(
    games: Sequence[HistoricalGame],
    team_id: UUID,
    side: Literal["Blue", "Red"],
    parameters: SideParameters,
) -> SideSample:
    observations = tuple(
        stat
        for game in games
        if game.usable_for_training
        for stat in game.team_stats
        if stat.team_id == team_id and stat.side == side and stat.result is not None
    )
    wins = sum(stat.result is True for stat in observations)
    adjusted = (Decimal(wins) + parameters.prior_games * parameters.prior_win_rate) / (
        Decimal(len(observations)) + parameters.prior_games
    )
    early_values = tuple(
        Decimal(value)
        for stat in observations
        if (value := stat.stats.get(parameters.early_stat)) is not None
        and not isinstance(value, bool)
    )
    return SideSample(
        side=side,
        games=len(observations),
        wins=wins,
        adjusted_win_rate=_quantize(adjusted),
        early_stat_mean=_mean(early_values),
        early_stat_games=len(early_values),
    )


def _target_scenario(side_a: TargetSide) -> TargetSideScenario:
    if side_a == "Blue":
        return TargetSideScenario("Blue", "Red", True, Decimal(1), Decimal())
    if side_a == "Red":
        return TargetSideScenario("Red", "Blue", True, Decimal(), Decimal(1))
    return TargetSideScenario(
        "unknown",
        "unknown",
        False,
        Decimal("0.5"),
        Decimal("0.5"),
    )


def _definition(
    name: str,
    parameters: SideParameters,
    document: Mapping[str, object],
    *,
    gated: bool = False,
) -> FeatureDefinitionSpec:
    return FeatureDefinitionSpec(
        name=name,
        domain="side",
        definition_version=parameters.version,
        parameters=document,
        availability="capability_gated" if gated else "required",
        required_capability="feature.early_game" if gated else None,
        code_version=_CODE_VERSION,
    )


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return _quantize(sum(values, Decimal()) / Decimal(len(values)))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def _write_strength(
    target: dict[str, FeatureValue],
    label: str,
    strength: TeamSideStrength,
) -> None:
    for side, sample in (("blue", strength.blue), ("red", strength.red)):
        prefix = f"side.{label}.{side}"
        target[f"{prefix}.games"] = sample.games
        target[f"{prefix}.wins"] = sample.wins
        target[f"{prefix}.adjusted_win_rate"] = sample.adjusted_win_rate
        target[f"{prefix}.early_stat_mean"] = sample.early_stat_mean
        target[f"{prefix}.early_stat_games"] = sample.early_stat_games
    target[f"side.{label}.adjusted_differential"] = strength.adjusted_differential
