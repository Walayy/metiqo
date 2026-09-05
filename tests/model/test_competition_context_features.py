"""Contexte OE prouvé et calendrier strictement as-of."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from metiquo.features import (
    AsOfGameBatch,
    CompetitionContextFeatureCalculator,
    ContextField,
    CutoffViolationError,
    FeatureCutoff,
    HistoricalGame,
    HistoricalTeamGame,
    TargetCompetitionContext,
    competition_context_feature_definitions,
)

_TEAM_A = UUID("11111111-1111-4111-8111-111111111111")
_TEAM_B = UUID("22222222-2222-4222-8222-222222222222")
_TEAM_C = UUID("33333333-3333-4333-8333-333333333333")
_SNAPSHOT = UUID("44444444-4444-4444-8444-444444444444")
_RUN = UUID("55555555-5555-4555-8555-555555555555")
_REVISION = UUID("66666666-6666-4666-8666-666666666666")
_CUTOFF = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def test_context_carries_provenance_and_schedule_uses_only_prior_games() -> None:
    known_at = _CUTOFF - timedelta(hours=1)
    target = TargetCompetitionContext(
        competition=ContextField.oe(
            UUID("77777777-7777-4777-8777-777777777777"),
            source_revision_id=_REVISION,
            known_at=known_at,
        ),
        league=ContextField.oe(
            "World Championship",
            source_revision_id=_REVISION,
            known_at=known_at,
        ),
        tournament=ContextField.oe(
            "Worlds 2026",
            source_revision_id=_REVISION,
            known_at=known_at,
        ),
        stage=ContextField.oe(
            "Swiss",
            source_revision_id=_REVISION,
            known_at=known_at,
        ),
        international=ContextField.oe(
            True,
            source_revision_id=_REVISION,
            known_at=known_at,
        ),
        best_of=ContextField.oe(
            3,
            source_revision_id=_REVISION,
            known_at=known_at,
        ),
        patch=ContextField.oe(
            "16.18",
            source_revision_id=_REVISION,
            known_at=known_at,
        ),
    )
    result = CompetitionContextFeatureCalculator().calculate(
        _batch((_game(9, _TEAM_A, _TEAM_B, 3), _game(2, _TEAM_A, _TEAM_C, 1))),
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
        target=target,
    )

    assert result.competition == "77777777-7777-4777-8777-777777777777"
    assert result.league == "World Championship"
    assert result.region is None
    assert result.stage == "Swiss"
    assert result.phase == "international"
    assert result.best_of == 3
    assert result.patch == "16.18"
    assert result.team_a.rest_days == Decimal("2.000000")
    assert result.team_a.density_games == 2
    assert result.team_a.format_experience_games == 1
    assert result.team_b.rest_days == Decimal("9.000000")
    assert result.team_b.density_games == 1
    assert result.provenance["context.league"] == f"canonical_oe:{_REVISION}"
    assert result.provenance["context.region"] == "unknown"
    assert result.provenance["context.team_a.rest_days"] == "derived:canonical_oe_history"
    assert result.values["context.region_known"] is False
    assert result.values["context.team_a.density_games_14d"] == 2


def test_unknowns_external_context_and_late_provenance_are_explicitly_guarded() -> None:
    unknown = CompetitionContextFeatureCalculator().calculate(
        _batch(()),
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
        target=TargetCompetitionContext(),
    )
    assert unknown.phase is None
    assert unknown.best_of is None
    assert unknown.team_a.rest_days is None
    assert unknown.team_a.format_experience_games is None
    assert set(unknown.provenance.values()) <= {
        "unknown",
        "derived:canonical_oe_history",
    }

    with pytest.raises(ValueError, match="canonical_oe"):
        ContextField(
            "news-value",
            cast(Any, "external_news"),
            _REVISION,
            _CUTOFF - timedelta(hours=1),
        )
    with pytest.raises(CutoffViolationError, match="connue après"):
        CompetitionContextFeatureCalculator().calculate(
            _batch(()),
            team_a_id=_TEAM_A,
            team_b_id=_TEAM_B,
            target=TargetCompetitionContext(
                league=ContextField.oe(
                    "Late League",
                    source_revision_id=_REVISION,
                    known_at=_CUTOFF + timedelta(seconds=1),
                )
            ),
        )

    definitions = competition_context_feature_definitions()
    assert {item.definition_version for item in definitions} == {"competition-context-v1"}
    assert all(item.parameters["external_news"] == "forbidden" for item in definitions)


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


def _game(days_ago: int, team_a: UUID, team_b: UUID, best_of: int) -> HistoricalGame:
    game_id = uuid4()
    return HistoricalGame(
        game_id=game_id,
        source_game_id=f"context-{game_id}",
        event_time=_CUTOFF - timedelta(days=days_ago),
        competition_id=None,
        patch_id=None,
        series_id=None,
        game_length_seconds=1800,
        best_of=best_of,
        game_number=1,
        usable_for_training=True,
        quality_status="complete",
        team_stats=(
            _team_stat(team_a, team_b, True),
            _team_stat(team_b, team_a, False),
        ),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=_CUTOFF - timedelta(hours=1),
    )


def _team_stat(team_id: UUID, opponent_id: UUID, won: bool) -> HistoricalTeamGame:
    return HistoricalTeamGame(
        team_stat_id=uuid4(),
        team_id=team_id,
        opponent_id=opponent_id,
        side="Blue" if won else "Red",
        result=won,
        kills=None,
        deaths=None,
        gold=None,
        towers=None,
        dragons=None,
        barons=None,
        availability=MappingProxyType({"result": True}),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=_CUTOFF - timedelta(hours=1),
    )
