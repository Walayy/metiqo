"""Rating Elo pré-game déterministe construit sur les lots as-of audités."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from uuid import UUID

from metiquo.features.registry import FeatureDefinitionSpec, FeatureValue
from metiquo.features.temporal import AsOfGameBatch, FeatureCutoff, HistoricalGame

_RATING_QUANTUM = Decimal("0.0001")
_PROBABILITY_QUANTUM = Decimal("0.000001")
_CODE_VERSION = "elo-pregame-v1"


@dataclass(frozen=True, slots=True)
class EloParameters:
    """Paramètres versionnés de la baseline Elo."""

    initial_rating: Decimal = Decimal("1500")
    k_factor: Decimal = Decimal("32")
    scale: Decimal = Decimal("400")
    competition_priors: Mapping[UUID, Decimal] = field(default_factory=dict)
    version: str = "elo-pregame-v1"

    def __post_init__(self) -> None:
        for name, value in (
            ("initial_rating", self.initial_rating),
            ("k_factor", self.k_factor),
            ("scale", self.scale),
        ):
            if not value.is_finite() or value <= 0:
                raise ValueError(f"paramètre Elo invalide: {name}")
        if not self.version.strip():
            raise ValueError("version Elo requise")
        if any(not value.is_finite() or value <= 0 for value in self.competition_priors.values()):
            raise ValueError("les priors de compétition doivent être finis et positifs")
        object.__setattr__(
            self,
            "competition_priors",
            MappingProxyType(dict(self.competition_priors)),
        )

    def document(self) -> dict[str, object]:
        return {
            "competition_priors": {
                str(key): str(value)
                for key, value in sorted(
                    self.competition_priors.items(), key=lambda item: str(item[0])
                )
            },
            "initial_rating": str(self.initial_rating),
            "k_factor": str(self.k_factor),
            "scale": str(self.scale),
        }


@dataclass(frozen=True, slots=True)
class TeamRating:
    team_id: UUID
    rating: Decimal
    games_played: int


@dataclass(frozen=True, slots=True)
class RatingTransition:
    """État pré-game et mise à jour auditables d'une observation passée."""

    game_id: UUID
    event_time: datetime
    team_a_id: UUID
    team_b_id: UUID
    team_a_before: Decimal
    team_b_before: Decimal
    expected_team_a: Decimal
    result_team_a: Decimal
    delta_team_a: Decimal


@dataclass(frozen=True, slots=True)
class RatingFeatureResult:
    parameters_version: str
    cutoff_at: datetime
    max_input_time: datetime | None
    team_a: TeamRating
    team_b: TeamRating
    transitions: tuple[RatingTransition, ...]

    @property
    def values(self) -> Mapping[str, FeatureValue]:
        return MappingProxyType(
            {
                "rating.team_a": self.team_a.rating,
                "rating.team_b": self.team_b.rating,
                "rating.difference": self.team_a.rating - self.team_b.rating,
                "rating.games_a": self.team_a.games_played,
                "rating.games_b": self.team_b.games_played,
            }
        )


def rating_feature_definitions(
    parameters: EloParameters | None = None,
) -> tuple[FeatureDefinitionSpec, ...]:
    """Déclarer les colonnes exactes produites par le rating."""

    resolved = parameters or EloParameters()
    document = resolved.document()
    return tuple(
        FeatureDefinitionSpec(
            name=name,
            domain="rating",
            definition_version=resolved.version,
            parameters=document,
            availability="required",
            code_version=_CODE_VERSION,
        )
        for name in (
            "rating.team_a",
            "rating.team_b",
            "rating.difference",
            "rating.games_a",
            "rating.games_b",
        )
    )


class EloRatingCalculator:
    """Rejouer les résultats antérieurs sans ordonner artificiellement les ex æquo temporels."""

    def __init__(self, parameters: EloParameters | None = None) -> None:
        self._parameters = parameters or EloParameters()

    def calculate(
        self,
        batch: AsOfGameBatch,
        *,
        team_a_id: UUID,
        team_b_id: UUID,
        target_competition_id: UUID | None = None,
    ) -> RatingFeatureResult:
        if team_a_id == team_b_id:
            raise ValueError("les deux équipes cibles doivent être distinctes")
        cutoff = FeatureCutoff(batch.audit.cutoff_at)
        cutoff.audit(
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
        ratings: dict[UUID, Decimal] = {}
        games_played: dict[UUID, int] = defaultdict(int)
        transitions: list[RatingTransition] = []
        games = sorted(batch.games, key=lambda game: (game.event_time, game.game_id))
        for event_time, simultaneous in _group_by_time(games):
            deltas: dict[UUID, Decimal] = defaultdict(Decimal)
            increments: dict[UUID, int] = defaultdict(int)
            for game in simultaneous:
                participants = _participants(game)
                if participants is None:
                    continue
                team_a, team_b, result_a = participants
                rating_a = ratings.get(team_a, self._initial(game.competition_id))
                rating_b = ratings.get(team_b, self._initial(game.competition_id))
                expected_a = _expected(rating_a, rating_b, self._parameters.scale)
                delta_a = _quantize(self._parameters.k_factor * (result_a - expected_a))
                deltas[team_a] += delta_a
                deltas[team_b] -= delta_a
                increments[team_a] += 1
                increments[team_b] += 1
                transitions.append(
                    RatingTransition(
                        game_id=game.game_id,
                        event_time=event_time,
                        team_a_id=team_a,
                        team_b_id=team_b,
                        team_a_before=rating_a,
                        team_b_before=rating_b,
                        expected_team_a=expected_a,
                        result_team_a=result_a,
                        delta_team_a=delta_a,
                    )
                )
            for team_id, delta in deltas.items():
                current = ratings.get(team_id, self._initial(_competition(simultaneous)))
                ratings[team_id] = _quantize(current + delta)
                games_played[team_id] += increments[team_id]
        initial = self._initial(target_competition_id)
        return RatingFeatureResult(
            parameters_version=self._parameters.version,
            cutoff_at=batch.audit.cutoff_at,
            max_input_time=batch.audit.max_input_time,
            team_a=TeamRating(
                team_a_id,
                ratings.get(team_a_id, initial),
                games_played[team_a_id],
            ),
            team_b=TeamRating(
                team_b_id,
                ratings.get(team_b_id, initial),
                games_played[team_b_id],
            ),
            transitions=tuple(transitions),
        )

    def _initial(self, competition_id: UUID | None) -> Decimal:
        if competition_id is None:
            return self._parameters.initial_rating
        return self._parameters.competition_priors.get(
            competition_id,
            self._parameters.initial_rating,
        )


def _group_by_time(
    games: list[HistoricalGame],
) -> tuple[tuple[datetime, tuple[HistoricalGame, ...]], ...]:
    grouped: dict[datetime, list[HistoricalGame]] = {}
    for game in games:
        grouped.setdefault(game.event_time, []).append(game)
    return tuple(
        (timestamp, tuple(values))
        for timestamp, values in sorted(grouped.items(), key=lambda item: item[0])
    )


def _participants(game: HistoricalGame) -> tuple[UUID, UUID, Decimal] | None:
    if not game.usable_for_training or len(game.team_stats) != 2:
        return None
    first, second = game.team_stats
    if first.result is None or second.result is None or first.result == second.result:
        return None
    return first.team_id, second.team_id, Decimal(int(first.result))


def _competition(games: tuple[HistoricalGame, ...]) -> UUID | None:
    return games[0].competition_id if games else None


def _expected(rating_a: Decimal, rating_b: Decimal, scale: Decimal) -> Decimal:
    exponent = float((rating_b - rating_a) / scale)
    probability = 1.0 / (1.0 + math.pow(10.0, exponent))
    return Decimal(str(probability)).quantize(_PROBABILITY_QUANTUM, rounding=ROUND_HALF_EVEN)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_RATING_QUANTUM, rounding=ROUND_HALF_EVEN)
