"""Roster OE as-of, régularisation et confiance explicite."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid4

from metiquo.features import (
    AsOfGameBatch,
    FeatureCutoff,
    HistoricalGame,
    HistoricalPlayerGame,
    HistoricalRosterObservation,
    RosterFeatureCalculator,
    roster_feature_definitions,
)

_TEAM_A = UUID("11111111-1111-4111-8111-111111111111")
_TEAM_B = UUID("22222222-2222-4222-8222-222222222222")
_SNAPSHOT = UUID("33333333-3333-4333-8333-333333333333")
_RUN = UUID("44444444-4444-4444-8444-444444444444")
_CUTOFF = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
_PLAYERS = {name: uuid4() for name in ("top1", "top2", "jng1", "mid1", "bot1", "sup1")}


def test_roster_features_use_only_prior_observations_and_regularize_strength() -> None:
    games = (
        _game(
            5,
            {"top": "top1", "jng": "mid1", "mid": "jng1", "bot": "bot1", "sup": "sup1"},
            won=True,
        ),
        _game(
            3,
            {"top": "top1", "jng": "jng1", "mid": "mid1", "bot": "bot1", "sup": "sup1"},
            won=False,
        ),
        _game(
            1,
            {"top": "top2", "jng": "jng1", "mid": "mid1", "bot": "bot1", "sup": "sup1"},
            won=True,
            top_confidence=Decimal("0.65"),
        ),
    )
    result = RosterFeatureCalculator().calculate(
        _batch(games),
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
    )

    assert result.team_a.expected_roster["top"].player_id == _PLAYERS["top2"]
    assert result.team_a.coverage == Decimal("1.000000")
    assert result.team_a.games_together == 1
    assert result.team_a.five_continuity == Decimal("0.333333")
    assert result.team_a.role_change_players == 2
    assert result.team_a.player_games["top"] == 1
    assert result.team_a.player_strengths["top"] == Decimal("0.583333")
    assert result.team_a.individual_games == 13
    assert result.team_a.synergy_games_by_pair["bot_sup"] == 3
    assert result.team_a.synergy_strengths["bot_sup"] == Decimal("0.583333")
    assert result.team_a.confidence > Decimal("0.6")
    assert result.team_a.low_confidence is False


def test_absent_roster_stays_missing_and_low_confidence_is_explicit() -> None:
    result = RosterFeatureCalculator().calculate(
        _batch(()),
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
    )

    assert result.team_a.coverage == 0
    assert result.team_a.five_continuity is None
    assert result.team_a.individual_strength is None
    assert result.team_a.synergy_strength is None
    assert result.team_a.confidence == 0
    assert result.team_a.low_confidence is True
    assert result.values["roster.team_a.player.top.strength"] is None
    assert result.values["roster.team_a.player.top.games"] == 0

    definitions = roster_feature_definitions()
    assert {item.definition_version for item in definitions} == {"roster-players-v1"}
    assert all(item.parameters["external_roster_sources"] == "forbidden" for item in definitions)


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
    roster: dict[str, str],
    *,
    won: bool,
    top_confidence: Decimal = Decimal(1),
) -> HistoricalGame:
    game_id = uuid4()
    event_time = _CUTOFF - timedelta(days=days_ago)
    player_stats: list[HistoricalPlayerGame] = []
    observations: list[HistoricalRosterObservation] = []
    for role, player_name in roster.items():
        player_id = _PLAYERS[player_name]
        revision_id = uuid4()
        player_stats.append(
            HistoricalPlayerGame(
                player_stat_id=uuid4(),
                player_id=player_id,
                team_id=_TEAM_A,
                side="Blue",
                position=role,
                champion=None,
                result=won,
                kills=None,
                deaths=None,
                assists=None,
                creep_score=None,
                gold=None,
                availability=MappingProxyType({"result": True}),
                source_revision_id=revision_id,
                source_snapshot_id=_SNAPSHOT,
                source_run_id=_RUN,
                source_processed_at=_CUTOFF - timedelta(hours=1),
            )
        )
        observations.append(
            HistoricalRosterObservation(
                observation_id=uuid4(),
                team_id=_TEAM_A,
                player_id=player_id,
                role=role,
                observed_at=event_time,
                continuity_status="confirmed",
                confidence=top_confidence if role == "top" else Decimal(1),
                source_revision_id=uuid4(),
                source_snapshot_id=_SNAPSHOT,
                source_run_id=_RUN,
                source_processed_at=_CUTOFF - timedelta(hours=1),
            )
        )
    return HistoricalGame(
        game_id=game_id,
        source_game_id=f"roster-{game_id}",
        event_time=event_time,
        competition_id=None,
        patch_id=None,
        series_id=None,
        game_length_seconds=None,
        best_of=1,
        game_number=1,
        usable_for_training=True,
        quality_status="complete",
        team_stats=(),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=_CUTOFF - timedelta(hours=1),
        player_stats=tuple(player_stats),
        roster_observations=tuple(observations),
    )
