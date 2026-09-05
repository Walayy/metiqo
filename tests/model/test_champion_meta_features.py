"""Champion pools historiques et garde-fous pré-draft."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest

from metiquo.features import (
    AsOfGameBatch,
    ChampionMetaFeatureCalculator,
    CutoffViolationError,
    FeatureCutoff,
    HistoricalGame,
    HistoricalPlayerGame,
    champion_meta_feature_definitions,
)

_TEAM_A = UUID("11111111-1111-4111-8111-111111111111")
_TEAM_B = UUID("22222222-2222-4222-8222-222222222222")
_PATCH = UUID("33333333-3333-4333-8333-333333333333")
_OLD_PATCH = UUID("44444444-4444-4444-8444-444444444444")
_SNAPSHOT = UUID("55555555-5555-4555-8555-555555555555")
_RUN = UUID("66666666-6666-4666-8666-666666666666")
_CUTOFF = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def test_champion_pool_patch_adaptation_and_compositions_are_historical() -> None:
    first = {"top": "TopA", "jng": "JungleA", "mid": "MidA", "bot": "BotA", "sup": "SupA"}
    second = {"top": "TopB", "jng": "JungleB", "mid": "MidA", "bot": "BotA", "sup": "SupB"}
    games = (
        _game(5, _PATCH, first, won=True),
        _game(3, _PATCH, second, won=False),
        _game(1, _OLD_PATCH, first, won=True),
    )

    result = ChampionMetaFeatureCalculator().calculate(
        _batch(games),
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
        target_patch_id=_PATCH,
    )

    top = result.team_a.roles["top"]
    assert top.picks == 3
    assert top.unique_champions == 2
    assert top.effective_depth == Decimal("1.889882")
    assert top.top_pick_share == Decimal("0.666667")
    assert top.win_rate == Decimal("0.666667")
    assert top.champion_win_rate_mean == Decimal("0.500000")
    assert result.team_a.patch_known is True
    assert result.team_a.patch_games == 2
    assert result.team_a.patch_win_rate == Decimal("0.500000")
    assert result.team_a.patch_adaptation_delta == Decimal("-0.166667")
    assert result.team_a.composition_games == 3
    assert result.team_a.unique_compositions == 2
    assert result.team_a.composition_repeat_rate == Decimal("0.666667")


def test_unknown_patch_is_explicit_and_target_draft_is_rejected() -> None:
    historical = _game(
        2,
        _OLD_PATCH,
        {"top": "TopA", "jng": "JungleA", "mid": "MidA", "bot": "BotA", "sup": "SupA"},
        won=True,
    )
    calculator = ChampionMetaFeatureCalculator()
    unknown = calculator.calculate(
        _batch((historical,)),
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
        target_patch_id=None,
    )

    assert unknown.team_a.patch_known is False
    assert unknown.team_a.patch_games == 0
    assert unknown.team_a.patch_win_rate is None
    assert unknown.team_a.patch_unique_champions == 0
    assert unknown.team_a.patch_adaptation_delta is None

    target = _game(
        1,
        _PATCH,
        {
            "top": "FutureTop",
            "jng": "FutureJungle",
            "mid": "FutureMid",
            "bot": "FutureBot",
            "sup": "FutureSupport",
        },
        won=True,
    )
    with pytest.raises(CutoffViolationError, match="game cible et son draft"):
        calculator.calculate(
            _batch((historical, target)),
            team_a_id=_TEAM_A,
            team_b_id=_TEAM_B,
            target_patch_id=_PATCH,
            target_game_id=target.game_id,
        )

    definitions = champion_meta_feature_definitions()
    assert {item.definition_version for item in definitions} == {"champion-meta-v1"}
    assert not any(".target" in item.name or ".actual_pick" in item.name for item in definitions)


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
    patch_id: UUID,
    champions: dict[str, str],
    *,
    won: bool,
) -> HistoricalGame:
    game_id = uuid4()
    return HistoricalGame(
        game_id=game_id,
        source_game_id=f"champion-{game_id}",
        event_time=_CUTOFF - timedelta(days=days_ago),
        competition_id=None,
        patch_id=patch_id,
        series_id=None,
        game_length_seconds=1800,
        best_of=3,
        game_number=1,
        usable_for_training=True,
        quality_status="complete",
        team_stats=(),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=_CUTOFF - timedelta(hours=1),
        player_stats=tuple(
            _player(game_id, role, champion, won) for role, champion in champions.items()
        ),
    )


def _player(game_id: UUID, role: str, champion: str, won: bool) -> HistoricalPlayerGame:
    return HistoricalPlayerGame(
        player_stat_id=uuid4(),
        player_id=uuid4(),
        team_id=_TEAM_A,
        side="Blue",
        position=role,
        champion=champion,
        result=won,
        kills=None,
        deaths=None,
        assists=None,
        creep_score=None,
        gold=None,
        availability=MappingProxyType({"champion": True, "result": True}),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=_CUTOFF - timedelta(hours=1),
    )
