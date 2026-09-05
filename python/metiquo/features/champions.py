"""Champion pools et méta pré-draft, calculés sur l'historique OE antérieur."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from uuid import UUID

from metiquo.features.registry import FeatureDefinitionSpec, FeatureValue
from metiquo.features.temporal import (
    AsOfGameBatch,
    CutoffViolationError,
    FeatureCutoff,
    HistoricalGame,
    HistoricalPlayerGame,
)

_ROLES = ("top", "jng", "mid", "bot", "sup")
_QUANTUM = Decimal("0.000001")
_CODE_VERSION = "champion-meta-v1"


@dataclass(frozen=True, slots=True)
class ChampionMetaParameters:
    roles: tuple[str, ...] = _ROLES
    version: str = "champion-meta-v1"

    def __post_init__(self) -> None:
        if self.roles != _ROLES:
            raise ValueError("les cinq rôles LoL canoniques sont requis dans l'ordre")
        if not self.version.strip():
            raise ValueError("version champion/méta requise")

    def document(self) -> dict[str, object]:
        return {
            "draft_scope": "historical_pre_draft_only",
            "roles": list(self.roles),
            "source": "canonical_oracles_elixir_history",
        }


@dataclass(frozen=True, slots=True)
class RoleChampionPool:
    role: str
    picks: int
    unique_champions: int
    effective_depth: Decimal | None
    top_pick_share: Decimal | None
    win_rate: Decimal | None
    champion_win_rate_mean: Decimal | None


@dataclass(frozen=True, slots=True)
class TeamChampionMeta:
    team_id: UUID
    roles: Mapping[str, RoleChampionPool]
    patch_known: bool
    patch_games: int
    patch_win_rate: Decimal | None
    patch_unique_champions: int
    patch_adaptation_delta: Decimal | None
    composition_games: int
    unique_compositions: int
    composition_repeat_rate: Decimal | None


@dataclass(frozen=True, slots=True)
class ChampionMetaFeatureResult:
    parameters_version: str
    cutoff_at: datetime
    max_input_time: datetime | None
    target_patch_id: UUID | None
    team_a: TeamChampionMeta
    team_b: TeamChampionMeta

    @property
    def values(self) -> Mapping[str, FeatureValue]:
        values: dict[str, FeatureValue] = {}
        _write_team_values(values, "team_a", self.team_a)
        _write_team_values(values, "team_b", self.team_b)
        return MappingProxyType(values)


def champion_meta_feature_definitions(
    parameters: ChampionMetaParameters | None = None,
) -> tuple[FeatureDefinitionSpec, ...]:
    """Déclarer des résumés de pools fixes qui n'encodent aucun pick cible."""

    resolved = parameters or ChampionMetaParameters()
    names: list[str] = []
    optional: set[str] = set()
    for team in ("team_a", "team_b"):
        base = f"champion.{team}"
        for role in resolved.roles:
            role_base = f"{base}.role.{role}"
            names.extend(
                (
                    f"{role_base}.picks",
                    f"{role_base}.unique",
                    f"{role_base}.effective_depth",
                    f"{role_base}.top_pick_share",
                    f"{role_base}.win_rate",
                    f"{role_base}.champion_win_rate_mean",
                )
            )
            optional.update(
                {
                    f"{role_base}.effective_depth",
                    f"{role_base}.top_pick_share",
                    f"{role_base}.win_rate",
                    f"{role_base}.champion_win_rate_mean",
                }
            )
        names.extend(
            (
                f"{base}.patch_known",
                f"{base}.patch_games",
                f"{base}.patch_win_rate",
                f"{base}.patch_unique_champions",
                f"{base}.patch_adaptation_delta",
                f"{base}.composition_games",
                f"{base}.unique_compositions",
                f"{base}.composition_repeat_rate",
            )
        )
        optional.update(
            {
                f"{base}.patch_win_rate",
                f"{base}.patch_adaptation_delta",
                f"{base}.composition_repeat_rate",
            }
        )
    document = resolved.document()
    return tuple(
        FeatureDefinitionSpec(
            name=name,
            domain="champion_meta",
            definition_version=resolved.version,
            parameters=document,
            availability="optional" if name in optional else "required",
            code_version=_CODE_VERSION,
        )
        for name in names
    )


class ChampionMetaFeatureCalculator:
    """Résumer les picks historiques sans jamais recevoir le draft de la cible."""

    def __init__(self, parameters: ChampionMetaParameters | None = None) -> None:
        self._parameters = parameters or ChampionMetaParameters()

    def calculate(
        self,
        batch: AsOfGameBatch,
        *,
        team_a_id: UUID,
        team_b_id: UUID,
        target_patch_id: UUID | None,
        target_game_id: UUID | None = None,
    ) -> ChampionMetaFeatureResult:
        if team_a_id == team_b_id:
            raise ValueError("les deux équipes cibles doivent être distinctes")
        if target_game_id is not None and any(
            game.game_id == target_game_id for game in batch.games
        ):
            raise CutoffViolationError(
                "la game cible et son draft ne peuvent pas entrer dans les features"
            )
        cutoff = FeatureCutoff(batch.audit.cutoff_at)
        audit = cutoff.audit(
            (game.event_time for game in batch.games),
            source_knowledge_times=(
                timestamp
                for game in batch.games
                for timestamp in (
                    game.source_processed_at,
                    *(player.source_processed_at for player in game.player_stats),
                )
            ),
        )
        return ChampionMetaFeatureResult(
            parameters_version=self._parameters.version,
            cutoff_at=cutoff.at,
            max_input_time=audit.max_input_time,
            target_patch_id=target_patch_id,
            team_a=self._team(batch.games, team_a_id, target_patch_id),
            team_b=self._team(batch.games, team_b_id, target_patch_id),
        )

    def _team(
        self,
        games: Sequence[HistoricalGame],
        team_id: UUID,
        target_patch_id: UUID | None,
    ) -> TeamChampionMeta:
        usable = tuple(game for game in games if game.usable_for_training)
        players = tuple(
            player
            for game in usable
            for player in game.player_stats
            if player.team_id == team_id and player.champion is not None
        )
        roles = {
            role: _role_pool(role, tuple(player for player in players if player.position == role))
            for role in self._parameters.roles
        }
        team_games = tuple(
            game
            for game in usable
            if any(player.team_id == team_id for player in game.player_stats)
        )
        overall_results = _team_results(team_games, team_id)
        patch_games = (
            tuple(game for game in team_games if game.patch_id == target_patch_id)
            if target_patch_id is not None
            else ()
        )
        patch_results = _team_results(patch_games, team_id)
        patch_champions = {
            player.champion
            for game in patch_games
            for player in game.player_stats
            if player.team_id == team_id and player.champion is not None
        }
        compositions = tuple(
            composition
            for game in team_games
            if (composition := _composition(game, team_id)) is not None
        )
        frequencies = Counter(compositions)
        repeated = sum(count for count in frequencies.values() if count > 1)
        overall_rate = _mean(overall_results)
        patch_rate = _mean(patch_results)
        return TeamChampionMeta(
            team_id=team_id,
            roles=MappingProxyType(roles),
            patch_known=target_patch_id is not None,
            patch_games=len(patch_games),
            patch_win_rate=patch_rate,
            patch_unique_champions=len(patch_champions),
            patch_adaptation_delta=(
                _quantize(patch_rate - overall_rate)
                if patch_rate is not None and overall_rate is not None
                else None
            ),
            composition_games=len(compositions),
            unique_compositions=len(frequencies),
            composition_repeat_rate=(_ratio(repeated, len(compositions)) if compositions else None),
        )


def _role_pool(role: str, players: Sequence[HistoricalPlayerGame]) -> RoleChampionPool:
    champions = tuple(player.champion for player in players if player.champion is not None)
    counts = Counter(champions)
    results = tuple(Decimal(int(player.result)) for player in players if player.result is not None)
    champion_rates = tuple(
        rate
        for champion in counts
        if (
            rate := _mean(
                tuple(
                    Decimal(int(player.result))
                    for player in players
                    if player.champion == champion and player.result is not None
                )
            )
        )
        is not None
    )
    return RoleChampionPool(
        role=role,
        picks=len(champions),
        unique_champions=len(counts),
        effective_depth=_effective_depth(tuple(counts.values())),
        top_pick_share=(_ratio(max(counts.values()), len(champions)) if champions else None),
        win_rate=_mean(results),
        champion_win_rate_mean=_mean(champion_rates),
    )


def _team_results(games: Sequence[HistoricalGame], team_id: UUID) -> tuple[Decimal, ...]:
    results: list[Decimal] = []
    for game in games:
        result = next(
            (
                player.result
                for player in game.player_stats
                if player.team_id == team_id and player.result is not None
            ),
            None,
        )
        if result is not None:
            results.append(Decimal(int(result)))
    return tuple(results)


def _composition(game: HistoricalGame, team_id: UUID) -> tuple[str, ...] | None:
    by_role = {
        player.position: player.champion
        for player in game.player_stats
        if player.team_id == team_id and player.champion is not None
    }
    if any(role not in by_role for role in _ROLES):
        return None
    return tuple(str(by_role[role]) for role in _ROLES)


def _effective_depth(counts: tuple[int, ...]) -> Decimal | None:
    total = sum(counts)
    if total == 0:
        return None
    entropy = -sum((count / total) * math.log(count / total) for count in counts if count > 0)
    return _quantize(Decimal(str(math.exp(entropy))))


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
    meta: TeamChampionMeta,
) -> None:
    base = f"champion.{label}"
    for role in _ROLES:
        pool = meta.roles[role]
        role_base = f"{base}.role.{role}"
        target[f"{role_base}.picks"] = pool.picks
        target[f"{role_base}.unique"] = pool.unique_champions
        target[f"{role_base}.effective_depth"] = pool.effective_depth
        target[f"{role_base}.top_pick_share"] = pool.top_pick_share
        target[f"{role_base}.win_rate"] = pool.win_rate
        target[f"{role_base}.champion_win_rate_mean"] = pool.champion_win_rate_mean
    target[f"{base}.patch_known"] = meta.patch_known
    target[f"{base}.patch_games"] = meta.patch_games
    target[f"{base}.patch_win_rate"] = meta.patch_win_rate
    target[f"{base}.patch_unique_champions"] = meta.patch_unique_champions
    target[f"{base}.patch_adaptation_delta"] = meta.patch_adaptation_delta
    target[f"{base}.composition_games"] = meta.composition_games
    target[f"{base}.unique_compositions"] = meta.unique_compositions
    target[f"{base}.composition_repeat_rate"] = meta.composition_repeat_rate
