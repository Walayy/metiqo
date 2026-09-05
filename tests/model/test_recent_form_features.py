"""Fenêtres de forme récente, missingness et statistiques adverses."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid4

from metiquo.features import (
    AsOfGameBatch,
    FeatureCutoff,
    HistoricalGame,
    HistoricalTeamGame,
    RecentFormCalculator,
    recent_form_feature_definitions,
)

_TEAM_A = UUID("11111111-1111-4111-8111-111111111111")
_TEAM_B = UUID("22222222-2222-4222-8222-222222222222")
_TEAM_C = UUID("33333333-3333-4333-8333-333333333333")
_COMPETITION = UUID("44444444-4444-4444-8444-444444444444")
_SNAPSHOT = UUID("55555555-5555-4555-8555-555555555555")
_RUN = UUID("66666666-6666-4666-8666-666666666666")
_CUTOFF = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
_PROCESSED = _CUTOFF - timedelta(hours=1)


def test_recent_form_keeps_game_and_day_windows_without_imputing_missing_result() -> None:
    games = (
        _game(50, True),
        _game(25, False),
        _game(20, True),
        _game(15, None),
        _game(10, True),
        _game(5, False),
    )
    batch = _batch(games)

    result = RecentFormCalculator().calculate(
        batch,
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
    )

    five = result.team_a.game_windows[5]
    assert five.observed_games == 5
    assert five.usable_games == 4
    assert five.win_rate == Decimal("0.500000")
    assert five.completeness == Decimal("0.800000")
    assert result.team_a.day_windows[30] == five
    assert result.team_a.day_windows[60].observed_games == 6
    assert result.team_a.day_windows[60].usable_games == 5
    assert result.team_a.day_windows[60].win_rate == Decimal("0.600000")
    assert result.team_b.game_windows[5].win_rate == Decimal("0.500000")
    assert result.team_a.usable_games == 5
    assert result.team_a.ewm_win_rate is not None
    assert Decimal() <= result.team_a.ewm_win_rate <= Decimal(1)
    assert result.team_a.trend is not None
    assert result.team_a.volatility is not None
    assert result.team_a.opponent_rating is not None
    assert result.max_input_time == games[-1].event_time
    assert result.values["form.team_a.win_rate_games_5"] == Decimal("0.500000")
    assert result.values["form.team_a.completeness_games_5"] == Decimal("0.800000")


def test_new_team_exposes_absence_and_sample_size_instead_of_zero_imputation() -> None:
    result = RecentFormCalculator().calculate(
        _batch((_game(5, True),)),
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_C,
    )

    assert result.team_b.usable_games == 0
    assert result.team_b.game_windows[5].observed_games == 0
    assert result.team_b.game_windows[5].win_rate is None
    assert result.team_b.game_windows[5].completeness is None
    assert result.team_b.ewm_win_rate is None
    assert result.team_b.trend is None
    assert result.team_b.volatility is None
    assert result.team_b.opponent_rating is None
    assert result.values["form.team_b.usable_games"] == 0
    assert result.values["form.team_b.win_rate_games_5"] is None

    definitions = recent_form_feature_definitions()
    names = {definition.name for definition in definitions}
    assert "form.team_a.win_rate_games_5" in names
    assert "form.team_b.win_rate_games_20" in names
    assert "form.team_a.win_rate_days_90" in names
    assert "form.team_b.opponent_rating_20" in names
    assert all(definition.definition_version == "recent-form-v1" for definition in definitions)


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


def _game(days_ago: int, team_a_wins: bool | None) -> HistoricalGame:
    game_id = uuid4()
    usable = team_a_wins is not None
    return HistoricalGame(
        game_id=game_id,
        source_game_id=f"form-{game_id}",
        event_time=_CUTOFF - timedelta(days=days_ago),
        competition_id=_COMPETITION,
        patch_id=None,
        series_id=None,
        game_length_seconds=1800,
        best_of=1,
        game_number=1,
        usable_for_training=usable,
        quality_status="complete" if usable else "incomplete",
        team_stats=(
            _team_stat(game_id, _TEAM_A, _TEAM_B, "Blue", team_a_wins),
            _team_stat(
                game_id,
                _TEAM_B,
                _TEAM_A,
                "Red",
                None if team_a_wins is None else not team_a_wins,
            ),
        ),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=_PROCESSED,
    )


def _team_stat(
    game_id: UUID,
    team_id: UUID,
    opponent_id: UUID,
    side: str,
    result: bool | None,
) -> HistoricalTeamGame:
    return HistoricalTeamGame(
        team_stat_id=uuid4(),
        team_id=team_id,
        opponent_id=opponent_id,
        side=side,
        result=result,
        kills=10 if result is not None else None,
        deaths=5 if result is not None else None,
        gold=None,
        towers=None,
        dragons=None,
        barons=None,
        availability=MappingProxyType({"result": result is not None}),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=_PROCESSED,
    )
