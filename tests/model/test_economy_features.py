"""Économie et objectifs fermés par défaut selon les capabilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid4

from metiquo.canonical.capabilities import DEFAULT_CAPABILITY_DEFINITIONS
from metiquo.features import (
    AsOfGameBatch,
    EconomyFeatureCalculator,
    FeatureCutoff,
    HistoricalGame,
    HistoricalTeamGame,
    economy_feature_definitions,
)

_TEAM_A = UUID("11111111-1111-4111-8111-111111111111")
_TEAM_B = UUID("22222222-2222-4222-8222-222222222222")
_COMPETITION = UUID("33333333-3333-4333-8333-333333333333")
_SNAPSHOT = UUID("44444444-4444-4444-8444-444444444444")
_RUN = UUID("55555555-5555-4555-8555-555555555555")
_CUTOFF = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

_ENABLED = {
    "feature.pace": "enabled",
    "feature.economy_timestamps": "enabled",
    "feature.objectives_total": "enabled",
    "feature.objectives_first": "enabled",
}


def test_enabled_capabilities_compute_historical_rates_and_conversion_without_leakage() -> None:
    batch = _batch(
        (
            _game(
                days_ago=2,
                team_a_wins=True,
                kills_a=12,
                towers_a=9,
                dragons_a=4,
                barons_a=1,
                gold_diff_a=500,
                first_a=True,
            ),
            _game(
                days_ago=1,
                team_a_wins=False,
                kills_a=6,
                towers_a=3,
                dragons_a=2,
                barons_a=1,
                gold_diff_a=-200,
                first_a=False,
            ),
        )
    )

    result = EconomyFeatureCalculator().calculate(
        batch,
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
        capabilities=_ENABLED,
    )

    assert result.availability == {
        "economy.pace": True,
        "economy.timed": True,
        "objectives.total": True,
        "objectives.first": True,
    }
    assert result.team_a.pace_games == 2
    assert result.team_a.kills_per_minute == Decimal("0.300000")
    assert result.team_a.duration_seconds == Decimal("1800.000000")
    assert result.team_a.timed_means["gold_diff_at_15"] == Decimal("150.000000")
    assert result.team_a.timed_means["xp_diff_at_15"] == Decimal("75.000000")
    assert result.team_a.timed_means["cs_diff_at_15"] == Decimal("7.500000")
    assert result.team_a.conversion_rate == Decimal("1.000000")
    assert result.team_a.conversion_games == 1
    assert result.team_a.comeback_rate == Decimal("0.000000")
    assert result.team_a.comeback_games == 1
    assert result.team_a.objective_rates["towers"] == Decimal("0.200000")
    assert result.team_a.first_objective_rates["first_blood"] == Decimal("0.500000")
    assert result.values["economy.team_a.gold_diff_at_10"] is None
    assert result.values["objectives.team_a.first_blood_games"] == 2


def test_missing_capabilities_disable_groups_instead_of_using_present_columns() -> None:
    result = EconomyFeatureCalculator().calculate(
        _batch(
            (
                _game(
                    days_ago=1,
                    team_a_wins=True,
                    kills_a=12,
                    towers_a=9,
                    dragons_a=4,
                    barons_a=1,
                    gold_diff_a=500,
                    first_a=True,
                ),
            )
        ),
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
        capabilities={name: "disabled" for name in _ENABLED},
    )

    assert all(available is False for available in result.availability.values())
    assert result.team_a.pace_games == 0
    assert result.team_a.kills_per_minute is None
    assert result.team_a.timed_means["gold_diff_at_15"] is None
    assert result.team_a.timed_games["gold_diff_at_15"] == 0
    assert result.team_a.conversion_rate is None
    assert result.team_a.objective_rates["towers"] is None
    assert result.team_a.first_objective_rates["first_blood"] is None

    definitions = economy_feature_definitions()
    gold = next(item for item in definitions if item.name == "economy.team_a.gold_diff_at_15")
    first = next(item for item in definitions if item.name == "objectives.team_a.first_blood_rate")
    assert gold.availability == "capability_gated"
    assert gold.required_capability == "feature.economy_timestamps"
    assert first.required_capability == "feature.objectives_first"
    capability_names = {item.name for item in DEFAULT_CAPABILITY_DEFINITIONS}
    assert set(_ENABLED) <= capability_names


def _batch(games: tuple[HistoricalGame, ...]) -> AsOfGameBatch:
    cutoff = FeatureCutoff(_CUTOFF)
    return AsOfGameBatch(
        games=games,
        audit=cutoff.audit(
            (game.event_time for game in games),
            source_knowledge_times=(game.source_processed_at for game in games),
        ),
        source_revision_ids=tuple(game.source_revision_id for game in games),
        source_snapshot_ids=(_SNAPSHOT,),
    )


def _game(
    *,
    days_ago: int,
    team_a_wins: bool,
    kills_a: int,
    towers_a: int,
    dragons_a: int,
    barons_a: int,
    gold_diff_a: int,
    first_a: bool,
) -> HistoricalGame:
    game_id = uuid4()
    return HistoricalGame(
        game_id=game_id,
        source_game_id=f"economy-{game_id}",
        event_time=_CUTOFF - timedelta(days=days_ago),
        competition_id=_COMPETITION,
        patch_id=None,
        series_id=None,
        game_length_seconds=1800,
        best_of=1,
        game_number=1,
        usable_for_training=True,
        quality_status="complete",
        team_stats=(
            _team_stat(
                game_id,
                _TEAM_A,
                _TEAM_B,
                "Blue",
                team_a_wins,
                kills_a,
                towers_a,
                dragons_a,
                barons_a,
                gold_diff_a,
                first_a,
            ),
            _team_stat(
                game_id,
                _TEAM_B,
                _TEAM_A,
                "Red",
                not team_a_wins,
                18 - kills_a,
                12 - towers_a,
                6 - dragons_a,
                2 - barons_a,
                -gold_diff_a,
                not first_a,
            ),
        ),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=_CUTOFF - timedelta(hours=1),
    )


def _team_stat(
    game_id: UUID,
    team_id: UUID,
    opponent_id: UUID,
    side: str,
    result: bool,
    kills: int,
    towers: int,
    dragons: int,
    barons: int,
    gold_diff: int,
    first: bool,
) -> HistoricalTeamGame:
    return HistoricalTeamGame(
        team_stat_id=uuid4(),
        team_id=team_id,
        opponent_id=opponent_id,
        side=side,
        result=result,
        kills=kills,
        deaths=18 - kills,
        gold=None,
        towers=towers,
        dragons=dragons,
        barons=barons,
        availability=MappingProxyType(
            {"kills": True, "towers": True, "dragons": True, "barons": True}
        ),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=_CUTOFF - timedelta(hours=1),
        stats=MappingProxyType(
            {
                "gold_diff_at_15": gold_diff,
                "xp_diff_at_15": gold_diff // 2,
                "cs_diff_at_15": gold_diff // 20,
                "first_blood": first,
                "first_tower": first,
                "first_dragon": first,
                "first_herald": first,
                "first_baron": first,
            }
        ),
    )
