"""Features roster et joueurs fondées uniquement sur les observations OE antérieures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from uuid import UUID

from metiquo.features.registry import FeatureDefinitionSpec, FeatureValue
from metiquo.features.temporal import (
    AsOfGameBatch,
    FeatureCutoff,
    HistoricalGame,
    HistoricalRosterObservation,
)

_QUANTUM = Decimal("0.000001")
_CODE_VERSION = "roster-players-v1"
_SYNERGY_PAIRS = (("top", "jng"), ("jng", "mid"), ("bot", "sup"))


@dataclass(frozen=True, slots=True)
class RosterParameters:
    roles: tuple[str, ...] = ("top", "jng", "mid", "bot", "sup")
    continuity_window_games: int = 5
    role_change_window_games: int = 10
    player_prior_games: Decimal = Decimal("5")
    player_prior_win_rate: Decimal = Decimal("0.5")
    synergy_prior_games: Decimal = Decimal("3")
    synergy_prior_win_rate: Decimal = Decimal("0.5")
    confidence_together_games: int = 5
    confidence_recency_days: int = 30
    low_confidence_threshold: Decimal = Decimal("0.6")
    version: str = "roster-players-v1"

    def __post_init__(self) -> None:
        if self.roles != ("top", "jng", "mid", "bot", "sup"):
            raise ValueError("les cinq rôles LoL canoniques sont requis dans l'ordre")
        if (
            min(
                self.continuity_window_games,
                self.role_change_window_games,
                self.confidence_together_games,
                self.confidence_recency_days,
            )
            <= 0
        ):
            raise ValueError("les fenêtres roster doivent être positives")
        for name, value in (
            ("player_prior_games", self.player_prior_games),
            ("synergy_prior_games", self.synergy_prior_games),
        ):
            if not value.is_finite() or value <= 0:
                raise ValueError(f"{name} doit être fini et positif")
        for name, value in (
            ("player_prior_win_rate", self.player_prior_win_rate),
            ("synergy_prior_win_rate", self.synergy_prior_win_rate),
            ("low_confidence_threshold", self.low_confidence_threshold),
        ):
            if not value.is_finite() or not Decimal() <= value <= Decimal(1):
                raise ValueError(f"{name} doit être compris entre zéro et un")
        if not self.version.strip():
            raise ValueError("version roster requise")

    def document(self) -> dict[str, object]:
        return {
            "confidence_recency_days": self.confidence_recency_days,
            "confidence_together_games": self.confidence_together_games,
            "continuity_window_games": self.continuity_window_games,
            "external_roster_sources": "forbidden",
            "low_confidence_threshold": str(self.low_confidence_threshold),
            "player_prior_games": str(self.player_prior_games),
            "player_prior_win_rate": str(self.player_prior_win_rate),
            "role_change_window_games": self.role_change_window_games,
            "roles": list(self.roles),
            "source": "canonical_oracles_elixir_history",
            "synergy_prior_games": str(self.synergy_prior_games),
            "synergy_prior_win_rate": str(self.synergy_prior_win_rate),
        }


@dataclass(frozen=True, slots=True)
class ExpectedRosterMember:
    role: str
    player_id: UUID
    observed_at: datetime
    confidence: Decimal
    evidence_observation_id: UUID


@dataclass(frozen=True, slots=True)
class TeamRosterFeatures:
    team_id: UUID
    expected_roster: Mapping[str, ExpectedRosterMember]
    coverage: Decimal
    five_continuity: Decimal | None
    games_together: int
    role_change_players: int
    player_strengths: Mapping[str, Decimal]
    player_games: Mapping[str, int]
    individual_strength: Decimal | None
    individual_games: int
    synergy_strengths: Mapping[str, Decimal]
    synergy_games_by_pair: Mapping[str, int]
    synergy_strength: Decimal | None
    synergy_games: int
    confidence: Decimal
    low_confidence: bool


@dataclass(frozen=True, slots=True)
class RosterFeatureResult:
    parameters_version: str
    cutoff_at: datetime
    max_input_time: datetime | None
    team_a: TeamRosterFeatures
    team_b: TeamRosterFeatures

    @property
    def values(self) -> Mapping[str, FeatureValue]:
        values: dict[str, FeatureValue] = {}
        _write_team_values(values, "team_a", self.team_a)
        _write_team_values(values, "team_b", self.team_b)
        return MappingProxyType(values)


def roster_feature_definitions(
    parameters: RosterParameters | None = None,
) -> tuple[FeatureDefinitionSpec, ...]:
    """Déclarer les sorties roster et leurs priors auditables."""

    resolved = parameters or RosterParameters()
    optional: set[str] = set()
    names: list[str] = []
    for team in ("team_a", "team_b"):
        base = f"roster.{team}"
        team_names = [
            f"{base}.coverage",
            f"{base}.five_continuity",
            f"{base}.games_together",
            f"{base}.role_change_players",
            f"{base}.individual_strength",
            f"{base}.individual_games",
            f"{base}.synergy_strength",
            f"{base}.synergy_games",
            f"{base}.confidence",
            f"{base}.low_confidence",
        ]
        optional.update(
            {f"{base}.five_continuity", f"{base}.individual_strength", f"{base}.synergy_strength"}
        )
        for role in resolved.roles:
            team_names.extend((f"{base}.player.{role}.strength", f"{base}.player.{role}.games"))
        for left, right in _SYNERGY_PAIRS:
            pair = f"{left}_{right}"
            team_names.extend((f"{base}.synergy.{pair}.strength", f"{base}.synergy.{pair}.games"))
        names.extend(team_names)
    document = resolved.document()
    return tuple(
        FeatureDefinitionSpec(
            name=name,
            domain="roster",
            definition_version=resolved.version,
            parameters=document,
            availability="optional"
            if name in optional or name.endswith(".strength")
            else "required",
            code_version=_CODE_VERSION,
        )
        for name in names
    )


class RosterFeatureCalculator:
    """Projeter et évaluer le roster depuis le seul lot canonique as-of."""

    def __init__(self, parameters: RosterParameters | None = None) -> None:
        self._parameters = parameters or RosterParameters()

    def calculate(
        self,
        batch: AsOfGameBatch,
        *,
        team_a_id: UUID,
        team_b_id: UUID,
    ) -> RosterFeatureResult:
        if team_a_id == team_b_id:
            raise ValueError("les deux équipes cibles doivent être distinctes")
        cutoff = FeatureCutoff(batch.audit.cutoff_at)
        input_audit = cutoff.audit(
            (
                timestamp
                for game in batch.games
                for timestamp in (
                    game.event_time,
                    *(item.observed_at for item in game.roster_observations),
                )
            ),
            source_knowledge_times=(
                timestamp
                for game in batch.games
                for timestamp in (
                    game.source_processed_at,
                    *(item.source_processed_at for item in game.player_stats),
                    *(item.source_processed_at for item in game.roster_observations),
                )
            ),
        )
        return RosterFeatureResult(
            parameters_version=self._parameters.version,
            cutoff_at=cutoff.at,
            max_input_time=input_audit.max_input_time,
            team_a=self._team(batch.games, team_a_id, cutoff),
            team_b=self._team(batch.games, team_b_id, cutoff),
        )

    def _team(
        self,
        games: Sequence[HistoricalGame],
        team_id: UUID,
        cutoff: FeatureCutoff,
    ) -> TeamRosterFeatures:
        ordered = tuple(sorted(games, key=lambda item: (item.event_time, item.game_id)))
        observations = tuple(
            observation
            for game in ordered
            for observation in game.roster_observations
            if observation.team_id == team_id and observation.observed_at < cutoff.at
        )
        expected = _expected_roster(observations, self._parameters.roles)
        team_games = tuple(
            game
            for game in ordered
            if any(player.team_id == team_id for player in game.player_stats)
        )
        rosters = tuple(_game_roster(game, team_id) for game in team_games)
        current_ids = frozenset(member.player_id for member in expected.values())
        full = len(expected) == len(self._parameters.roles) and len(current_ids) == len(expected)
        recent_complete = tuple(
            roster
            for roster in rosters[-self._parameters.continuity_window_games :]
            if len(roster) == len(self._parameters.roles)
        )
        games_together = sum(
            1 for roster in rosters if full and frozenset(roster.values()) == current_ids
        )
        five_continuity = (
            _ratio(
                sum(1 for roster in recent_complete if frozenset(roster.values()) == current_ids),
                len(recent_complete),
            )
            if full and recent_complete
            else None
        )
        recent_players = tuple(
            player
            for game in team_games[-self._parameters.role_change_window_games :]
            for player in game.player_stats
            if player.team_id == team_id and player.player_id in current_ids
        )
        role_change_players = sum(
            1
            for role, member in expected.items()
            if any(
                player.player_id == member.player_id and player.position != role
                for player in recent_players
            )
        )
        player_strengths, player_games = self._player_strengths(team_games, expected, team_id)
        synergy_strengths, synergy_games_by_pair = self._synergies(team_games, expected, team_id)
        individual_strength = _mean(tuple(player_strengths.values()))
        individual_games = sum(player_games.values())
        synergy_strength = _mean(tuple(synergy_strengths.values()))
        synergy_games = sum(synergy_games_by_pair.values())
        coverage = _ratio(len(expected), len(self._parameters.roles))
        confidence = self._confidence(
            expected,
            coverage=coverage,
            games_together=games_together,
            cutoff=cutoff,
        )
        return TeamRosterFeatures(
            team_id=team_id,
            expected_roster=MappingProxyType(dict(expected)),
            coverage=coverage,
            five_continuity=five_continuity,
            games_together=games_together,
            role_change_players=role_change_players,
            player_strengths=MappingProxyType(player_strengths),
            player_games=MappingProxyType(player_games),
            individual_strength=individual_strength,
            individual_games=individual_games,
            synergy_strengths=MappingProxyType(synergy_strengths),
            synergy_games_by_pair=MappingProxyType(synergy_games_by_pair),
            synergy_strength=synergy_strength,
            synergy_games=synergy_games,
            confidence=confidence,
            low_confidence=confidence < self._parameters.low_confidence_threshold,
        )

    def _player_strengths(
        self,
        games: Sequence[HistoricalGame],
        expected: Mapping[str, ExpectedRosterMember],
        team_id: UUID,
    ) -> tuple[dict[str, Decimal], dict[str, int]]:
        strengths: dict[str, Decimal] = {}
        counts: dict[str, int] = {}
        for role, member in expected.items():
            results = tuple(
                Decimal(int(player.result))
                for game in games
                for player in game.player_stats
                if game.usable_for_training
                and player.team_id == team_id
                and player.player_id == member.player_id
                and player.result is not None
            )
            counts[role] = len(results)
            strengths[role] = _regularized_rate(
                results,
                self._parameters.player_prior_win_rate,
                self._parameters.player_prior_games,
            )
        return strengths, counts

    def _synergies(
        self,
        games: Sequence[HistoricalGame],
        expected: Mapping[str, ExpectedRosterMember],
        team_id: UUID,
    ) -> tuple[dict[str, Decimal], dict[str, int]]:
        strengths: dict[str, Decimal] = {}
        counts: dict[str, int] = {}
        for left, right in _SYNERGY_PAIRS:
            if left not in expected or right not in expected:
                continue
            pair = f"{left}_{right}"
            player_ids = {expected[left].player_id, expected[right].player_id}
            results: list[Decimal] = []
            for game in games:
                if not game.usable_for_training:
                    continue
                players = tuple(
                    player
                    for player in game.player_stats
                    if player.team_id == team_id and player.player_id in player_ids
                )
                if len({player.player_id for player in players}) != 2:
                    continue
                result = next(
                    (player.result for player in players if player.result is not None), None
                )
                if result is not None:
                    results.append(Decimal(int(result)))
            counts[pair] = len(results)
            strengths[pair] = _regularized_rate(
                tuple(results),
                self._parameters.synergy_prior_win_rate,
                self._parameters.synergy_prior_games,
            )
        return strengths, counts

    def _confidence(
        self,
        roster: Mapping[str, ExpectedRosterMember],
        *,
        coverage: Decimal,
        games_together: int,
        cutoff: FeatureCutoff,
    ) -> Decimal:
        if not roster:
            return Decimal().quantize(_QUANTUM)
        observation = _mean(tuple(member.confidence for member in roster.values())) or Decimal()
        together = min(
            Decimal(games_together) / Decimal(self._parameters.confidence_together_games),
            Decimal(1),
        )
        recency = (
            _mean(
                tuple(
                    max(
                        Decimal(),
                        Decimal(1)
                        - Decimal(str((cutoff.at - member.observed_at).total_seconds()))
                        / Decimal(self._parameters.confidence_recency_days * 86400),
                    )
                    for member in roster.values()
                )
            )
            or Decimal()
        )
        return _quantize(
            coverage
            * (
                Decimal("0.45")
                + Decimal("0.25") * observation
                + Decimal("0.15") * together
                + Decimal("0.15") * recency
            )
        )


def _expected_roster(
    observations: Sequence[HistoricalRosterObservation],
    roles: tuple[str, ...],
) -> dict[str, ExpectedRosterMember]:
    latest: dict[str, ExpectedRosterMember] = {}
    for observation in sorted(
        observations,
        key=lambda item: (item.observed_at, item.observation_id),
    ):
        if observation.role not in roles:
            continue
        latest[observation.role] = ExpectedRosterMember(
            role=observation.role,
            player_id=observation.player_id,
            observed_at=observation.observed_at,
            confidence=observation.confidence,
            evidence_observation_id=observation.observation_id,
        )
    return {role: latest[role] for role in roles if role in latest}


def _game_roster(game: HistoricalGame, team_id: UUID) -> dict[str, UUID]:
    return {
        player.position: player.player_id
        for player in game.player_stats
        if player.team_id == team_id
    }


def _regularized_rate(
    results: Sequence[Decimal],
    prior_rate: Decimal,
    prior_games: Decimal,
) -> Decimal:
    return _quantize(
        (sum(results, Decimal()) + prior_rate * prior_games) / (len(results) + prior_games)
    )


def _ratio(numerator: int, denominator: int) -> Decimal:
    return _quantize(Decimal(numerator) / Decimal(denominator))


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return _quantize(sum(values, Decimal()) / Decimal(len(values)))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def _write_team_values(
    target: dict[str, FeatureValue],
    label: str,
    roster: TeamRosterFeatures,
) -> None:
    base = f"roster.{label}"
    target[f"{base}.coverage"] = roster.coverage
    target[f"{base}.five_continuity"] = roster.five_continuity
    target[f"{base}.games_together"] = roster.games_together
    target[f"{base}.role_change_players"] = roster.role_change_players
    target[f"{base}.individual_strength"] = roster.individual_strength
    target[f"{base}.individual_games"] = roster.individual_games
    target[f"{base}.synergy_strength"] = roster.synergy_strength
    target[f"{base}.synergy_games"] = roster.synergy_games
    target[f"{base}.confidence"] = roster.confidence
    target[f"{base}.low_confidence"] = roster.low_confidence
    for role in ("top", "jng", "mid", "bot", "sup"):
        target[f"{base}.player.{role}.strength"] = roster.player_strengths.get(role)
        target[f"{base}.player.{role}.games"] = roster.player_games.get(role, 0)
    for left, right in _SYNERGY_PAIRS:
        pair = f"{left}_{right}"
        target[f"{base}.synergy.{pair}.strength"] = roster.synergy_strengths.get(pair)
        target[f"{base}.synergy.{pair}.games"] = roster.synergy_games_by_pair.get(pair, 0)
