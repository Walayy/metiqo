"""Force Blue/Red et side cible inconnue sans supposition."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from metiquo.features import (
    AsOfGameBatch,
    FeatureCutoff,
    HistoricalGame,
    HistoricalTeamGame,
    SideFeatureCalculator,
    side_feature_definitions,
)

_TEAM_A = UUID("11111111-1111-4111-8111-111111111111")
_TEAM_B = UUID("22222222-2222-4222-8222-222222222222")
_COMPETITION = UUID("33333333-3333-4333-8333-333333333333")
_SNAPSHOT = UUID("44444444-4444-4444-8444-444444444444")
_RUN = UUID("55555555-5555-4555-8555-555555555555")
_CUTOFF = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def test_side_strength_is_adjusted_and_early_stats_remain_optional() -> None:
    batch = _batch(
        (
            _game(5, "Blue", True, 100),
            _game(4, "Blue", True, None),
            _game(3, "Blue", False, -50),
            _game(2, "Red", False, None),
            _game(1, "Red", False, None),
        )
    )

    result = SideFeatureCalculator().calculate(
        batch,
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
        target_side_a="unknown",
    )

    assert result.team_a.blue.games == 3
    assert result.team_a.blue.wins == 2
    assert result.team_a.blue.adjusted_win_rate == Decimal("0.571429")
    assert result.team_a.blue.early_stat_mean == Decimal("25.000000")
    assert result.team_a.blue.early_stat_games == 2
    assert result.team_a.red.games == 2
    assert result.team_a.red.wins == 0
    assert result.team_a.red.adjusted_win_rate == Decimal("0.333333")
    assert result.team_a.red.early_stat_mean is None
    assert result.team_a.adjusted_differential == Decimal("0.238096")
    assert result.values["side.team_a.red.early_stat_mean"] is None

    assert result.target.team_a_side == "unknown"
    assert result.target.team_b_side == "unknown"
    assert result.target.side_known is False
    assert result.target.team_a_blue_weight == Decimal("0.5")
    assert result.target.team_a_red_weight == Decimal("0.5")


def test_known_side_is_one_hot_and_registry_marks_early_stats_as_gated() -> None:
    result = SideFeatureCalculator().calculate(
        _batch(()),
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
        target_side_a="Blue",
    )

    assert result.team_a.blue.games == 0
    assert result.team_a.blue.adjusted_win_rate == Decimal("0.500000")
    assert result.target.team_a_side == "Blue"
    assert result.target.team_b_side == "Red"
    assert result.target.side_known is True
    assert result.target.team_a_blue_weight == 1
    assert result.target.team_a_red_weight == 0

    definitions = side_feature_definitions()
    early = tuple(item for item in definitions if "early_stat" in item.name)
    assert early
    assert all(item.availability == "capability_gated" for item in early)
    assert all(item.required_capability == "feature.early_game" for item in early)
    assert {item.definition_version for item in definitions} == {"side-strength-v1"}

    with pytest.raises(ValueError, match="side cible invalide"):
        SideFeatureCalculator().calculate(
            _batch(()),
            team_a_id=_TEAM_A,
            team_b_id=_TEAM_B,
            target_side_a=cast(Any, "blue"),
        )


def _batch(games: tuple[HistoricalGame, ...]) -> AsOfGameBatch:
    cutoff = FeatureCutoff(_CUTOFF)
    return AsOfGameBatch(
        games=games,
        audit=cutoff.audit(
            (game.event_time for game in games),
            source_knowledge_times=(game.source_processed_at for game in games),
        ),
        source_revision_ids=tuple(game.source_revision_id for game in games),
        source_snapshot_ids=(_SNAPSHOT,) if games else (),
    )


def _game(
    days_ago: int,
    side_a: str,
    team_a_wins: bool,
    early_gold_a: int | None,
) -> HistoricalGame:
    game_id = uuid4()
    side_b = "Red" if side_a == "Blue" else "Blue"
    early_gold_b = None if early_gold_a is None else -early_gold_a
    return HistoricalGame(
        game_id=game_id,
        source_game_id=f"side-{game_id}",
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
                side_a,
                team_a_wins,
                early_gold_a,
            ),
            _team_stat(
                game_id,
                _TEAM_B,
                _TEAM_A,
                side_b,
                not team_a_wins,
                early_gold_b,
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
    early_gold: int | None,
) -> HistoricalTeamGame:
    stats = {} if early_gold is None else {"gold_diff_at_15": early_gold}
    return HistoricalTeamGame(
        team_stat_id=uuid4(),
        team_id=team_id,
        opponent_id=opponent_id,
        side=side,
        result=result,
        kills=10,
        deaths=5,
        gold=None,
        towers=None,
        dragons=None,
        barons=None,
        availability=MappingProxyType({"result": True}),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=_CUTOFF - timedelta(hours=1),
        stats=MappingProxyType(stats),
    )
