"""Sentinelles bloquantes contre les principales fuites temporelles."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest

from metiquo.features import (
    AsOfGameBatch,
    CutoffViolationError,
    EloRatingCalculator,
    FeatureCutoff,
    HistoricalGame,
    HistoricalTeamGame,
)
from metiquo.features.temporal import AsOfInputAudit

_TEAM_A = UUID("11111111-1111-4111-8111-111111111111")
_TEAM_B = UUID("22222222-2222-4222-8222-222222222222")
_SNAPSHOT = UUID("33333333-3333-4333-8333-333333333333")
_RUN = UUID("44444444-4444-4444-8444-444444444444")
_CUTOFF = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def test_property_every_nonnegative_event_offset_is_rejected() -> None:
    cutoff = FeatureCutoff(_CUTOFF)
    for microseconds in range(-64, 65):
        instant = _CUTOFF + timedelta(microseconds=microseconds)
        if microseconds < 0:
            assert cutoff.audit([instant]).max_input_time == instant
        else:
            with pytest.raises(CutoffViolationError, match="strictement antérieur"):
                cutoff.audit([instant])


def test_future_game_and_late_revision_fail_before_aggregate() -> None:
    valid = _game(
        event_time=_CUTOFF - timedelta(days=1),
        processed_at=_CUTOFF - timedelta(hours=1),
    )
    future = _game(
        event_time=_CUTOFF,
        processed_at=_CUTOFF - timedelta(hours=1),
    )
    late_revision = _game(
        event_time=_CUTOFF - timedelta(days=2),
        processed_at=_CUTOFF + timedelta(microseconds=1),
    )
    empty_audit = AsOfInputAudit(
        cutoff_at=_CUTOFF,
        max_input_time=None,
        max_knowledge_time=None,
        input_count=0,
    )

    valid_result = EloRatingCalculator().calculate(
        AsOfGameBatch((valid,), FeatureCutoff(_CUTOFF).audit([valid.event_time]), (), ()),
        team_a_id=_TEAM_A,
        team_b_id=_TEAM_B,
    )
    assert valid_result.max_input_time == valid.event_time

    with pytest.raises(CutoffViolationError, match="strictement antérieur"):
        EloRatingCalculator().calculate(
            AsOfGameBatch((valid, future), empty_audit, (), ()),
            team_a_id=_TEAM_A,
            team_b_id=_TEAM_B,
        )
    with pytest.raises(CutoffViolationError, match="connue après"):
        EloRatingCalculator().calculate(
            AsOfGameBatch((valid, late_revision), empty_audit, (), ()),
            team_a_id=_TEAM_A,
            team_b_id=_TEAM_B,
        )


def _game(*, event_time: datetime, processed_at: datetime) -> HistoricalGame:
    game_id = uuid4()
    return HistoricalGame(
        game_id=game_id,
        source_game_id=f"leakage-{game_id}",
        event_time=event_time,
        competition_id=None,
        patch_id=None,
        series_id=None,
        game_length_seconds=1800,
        best_of=1,
        game_number=1,
        usable_for_training=True,
        quality_status="complete",
        team_stats=(
            _team_stat(_TEAM_A, _TEAM_B, True, processed_at),
            _team_stat(_TEAM_B, _TEAM_A, False, processed_at),
        ),
        source_revision_id=uuid4(),
        source_snapshot_id=_SNAPSHOT,
        source_run_id=_RUN,
        source_processed_at=processed_at,
    )


def _team_stat(
    team_id: UUID,
    opponent_id: UUID,
    result: bool,
    processed_at: datetime,
) -> HistoricalTeamGame:
    return HistoricalTeamGame(
        team_stat_id=uuid4(),
        team_id=team_id,
        opponent_id=opponent_id,
        side="Blue" if result else "Red",
        result=result,
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
        source_processed_at=processed_at,
    )
