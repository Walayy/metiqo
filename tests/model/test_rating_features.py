"""Séquences Elo pré-game calculables à la main."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest

from metiquo.features import (
    AsOfGameBatch,
    CutoffViolationError,
    EloParameters,
    EloRatingCalculator,
    FeatureCutoff,
    HistoricalGame,
    HistoricalTeamGame,
    rating_feature_definitions,
)

_TEAM_A = UUID("11111111-1111-4111-8111-111111111111")
_TEAM_B = UUID("22222222-2222-4222-8222-222222222222")
_COMPETITION = UUID("33333333-3333-4333-8333-333333333333")
_SNAPSHOT = UUID("44444444-4444-4444-8444-444444444444")
_RUN = UUID("55555555-5555-4555-8555-555555555555")
_PROCESSED = datetime(2026, 9, 6, 10, 0, tzinfo=UTC)
_CUTOFF = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def test_one_game_elo_is_hand_checkable_and_uses_only_pregame_state() -> None:
    game = _game(datetime(2026, 9, 5, 18, 0, tzinfo=UTC), team_a_wins=True)
    batch = _batch((game,))
    calculator = EloRatingCalculator()

    result = calculator.calculate(batch, team_a_id=_TEAM_A, team_b_id=_TEAM_B)

    assert result == calculator.calculate(batch, team_a_id=_TEAM_A, team_b_id=_TEAM_B)
    assert result.team_a.rating == Decimal("1516.0000")
    assert result.team_b.rating == Decimal("1484.0000")
    assert result.values == {
        "rating.team_a": Decimal("1516.0000"),
        "rating.team_b": Decimal("1484.0000"),
        "rating.difference": Decimal("32.0000"),
        "rating.games_a": 1,
        "rating.games_b": 1,
    }
    transition = result.transitions[0]
    assert transition.team_a_before == Decimal("1500")
    assert transition.team_b_before == Decimal("1500")
    assert transition.expected_team_a == Decimal("0.500000")
    assert transition.delta_team_a == Decimal("16.0000")
    assert result.max_input_time == game.event_time


def test_simultaneous_games_do_not_leak_one_result_into_the_other() -> None:
    timestamp = datetime(2026, 9, 5, 18, 0, tzinfo=UTC)
    games = (
        _game(timestamp, team_a_wins=True),
        _game(timestamp, team_a_wins=True),
    )

    result = EloRatingCalculator().calculate(
        _batch(tuple(reversed(games))),
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
    )

    assert result.team_a.rating == Decimal("1532.0000")
    assert result.team_b.rating == Decimal("1468.0000")
    assert {transition.team_a_before for transition in result.transitions} == {Decimal("1500")}
    assert {transition.expected_team_a for transition in result.transitions} == {
        Decimal("0.500000")
    }


def test_rating_parameters_are_versioned_and_future_input_is_blocked() -> None:
    parameters = EloParameters(competition_priors={_COMPETITION: Decimal("1600")})
    definitions = rating_feature_definitions(parameters)
    empty = _batch(())
    result = EloRatingCalculator(parameters).calculate(
        empty,
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
        target_competition_id=_COMPETITION,
    )

    assert result.team_a.rating == Decimal("1600")
    assert result.team_b.rating == Decimal("1600")
    assert [definition.name for definition in definitions] == [
        "rating.team_a",
        "rating.team_b",
        "rating.difference",
        "rating.games_a",
        "rating.games_b",
    ]
    assert all(definition.definition_version == parameters.version for definition in definitions)
    assert definitions[0].parameters["competition_priors"] == {str(_COMPETITION): "1600"}

    target_game = _game(_CUTOFF, team_a_wins=False)
    tampered = AsOfGameBatch(
        games=(target_game,),
        audit=FeatureCutoff(_CUTOFF).audit([]),
        source_revision_ids=(),
        source_snapshot_ids=(),
    )
    with pytest.raises(CutoffViolationError, match="strictement antérieur"):
        EloRatingCalculator().calculate(
            tampered,
            team_a_id=_TEAM_A,
            team_b_id=_TEAM_B,
        )
    with pytest.raises(ValueError, match="distinctes"):
        EloRatingCalculator().calculate(empty, team_a_id=_TEAM_A, team_b_id=_TEAM_A)


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


def _game(event_time: datetime, *, team_a_wins: bool) -> HistoricalGame:
    game_id = uuid4()
    return HistoricalGame(
        game_id=game_id,
        source_game_id=f"rating-{game_id}",
        event_time=event_time,
        competition_id=_COMPETITION,
        patch_id=None,
        series_id=None,
        game_length_seconds=1800,
        best_of=1,
        game_number=1,
        usable_for_training=True,
        quality_status="complete",
        team_stats=(
            _team_stat(game_id, _TEAM_A, _TEAM_B, "Blue", team_a_wins),
            _team_stat(game_id, _TEAM_B, _TEAM_A, "Red", not team_a_wins),
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
    result: bool,
) -> HistoricalTeamGame:
    return HistoricalTeamGame(
        team_stat_id=uuid4(),
        team_id=team_id,
        opponent_id=opponent_id,
        side=side,
        result=result,
        kills=10,
        deaths=5,
        gold=None,
        towers=8,
        dragons=3,
        barons=1,
        availability=MappingProxyType({"result": True}),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=_PROCESSED - timedelta(minutes=1),
    )
