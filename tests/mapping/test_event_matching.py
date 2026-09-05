"""Fixtures du score versionné de matching événement."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest

from metiquo.contracts import Event
from metiquo.contracts.enums import (
    EventStatus,
    GameTitle,
    SelectionType,
)
from metiquo.contracts.odds_provider import ProviderEvent
from metiquo.mapping import (
    MATCHING_WEIGHTS_VERSION,
    EventMappingReason,
    EventMappingStatus,
    EventMatchingScorer,
    EventMatchingWeights,
    UnresolvedEventMappingError,
    normalize_entity_name,
)

_START = datetime(2026, 9, 8, 18, 0, tzinfo=UTC)


def test_initial_weights_and_exact_auto_threshold_are_versioned() -> None:
    weights = EventMatchingWeights()
    event = _event()
    provider = _provider_event()

    decision = EventMatchingScorer().evaluate(provider, (event,))
    missing_format = EventMatchingScorer().evaluate(
        _provider_event(best_of=None),
        (event,),
    )

    assert (weights.teams, weights.time, weights.competition, weights.format) == (
        Decimal("0.60"),
        Decimal("0.20"),
        Decimal("0.15"),
        Decimal("0.05"),
    )
    assert decision.weights_version == MATCHING_WEIGHTS_VERSION
    assert decision.candidates[0].total_score == Decimal("1.00")
    assert decision.status is EventMappingStatus.AUTO_MATCHED
    assert missing_format.candidates[0].total_score == Decimal("0.95")
    assert missing_format.status is EventMappingStatus.AUTO_MATCHED


def test_inverted_participants_remap_team_selections_after_resolution() -> None:
    provider = _provider_event(participants=("Team B", "Team A"))

    decision = EventMatchingScorer().evaluate(provider, (_event(),))

    assert decision.resolved is True
    assert decision.selections_inverted is True
    assert decision.remap_selection(SelectionType.TEAM_A) is SelectionType.TEAM_B
    assert decision.remap_selection(SelectionType.TEAM_B) is SelectionType.TEAM_A
    assert decision.remap_selection(SelectionType.DRAW) is SelectionType.DRAW


def test_dated_aliases_can_match_without_fuzzy_name_merging() -> None:
    event = _event()
    aliases = MappingProxyType(
        {
            event.team_a_id: frozenset({normalize_entity_name("Sponsor Team A")}),
            event.team_b_id: frozenset({normalize_entity_name("Sponsor Team B")}),
        }
    )

    decision = EventMatchingScorer().evaluate(
        _provider_event(participants=("Sponsor Team A", "Sponsor Team B")),
        (event,),
        aliases,
    )

    assert decision.status is EventMappingStatus.AUTO_MATCHED
    assert decision.candidates[0].team_score == Decimal(1)


def test_review_reject_and_close_candidate_rules_never_resolve_ambiguity() -> None:
    event = _event()
    review = EventMatchingScorer().evaluate(
        _provider_event(competition="Another League"),
        (event,),
    )
    rejected = EventMatchingScorer().evaluate(
        _provider_event(
            competition="Another League",
            participants=("Team A", "Different Team"),
        ),
        (event,),
    )
    close = EventMatchingScorer().evaluate(
        _provider_event(),
        (event, _event(event_id=uuid4())),
    )

    assert review.status is EventMappingStatus.REVIEW
    assert review.reason is EventMappingReason.REVIEW_THRESHOLD
    assert review.candidates[0].total_score == Decimal("0.85")
    assert rejected.status is EventMappingStatus.REJECTED
    assert rejected.reason is EventMappingReason.LOW_CONFIDENCE
    assert close.status is EventMappingStatus.REVIEW
    assert close.reason is EventMappingReason.AMBIGUOUS_CANDIDATES
    assert all(decision.selected_event_id is None for decision in (review, rejected, close))
    with pytest.raises(UnresolvedEventMappingError, match="ne peut pas alimenter"):
        close.remap_selection(SelectionType.TEAM_A)


@pytest.mark.parametrize(
    "participants",
    (
        ("TBD", "Team B"),
        ("Winner of Match 1", "Team B"),
        ("Loser of Match 2", "Team B"),
    ),
)
def test_placeholder_participants_are_rejected(
    participants: tuple[str, str],
) -> None:
    decision = EventMatchingScorer().evaluate(
        _provider_event(participants=participants),
        (_event(),),
    )

    assert decision.status is EventMappingStatus.REJECTED
    assert decision.reason is EventMappingReason.UNRESOLVED_PARTICIPANT
    assert decision.candidates == ()


def _event(*, event_id: UUID | None = None) -> Event:
    return Event(
        event_id=event_id or uuid4(),
        game_title=GameTitle.LEAGUE_OF_LEGENDS,
        competition="League One",
        team_a_id=uuid4(),
        team_a="Team A",
        team_b_id=uuid4(),
        team_b="Team B",
        starts_at=_START,
        best_of=3,
        status=EventStatus.SCHEDULED,
        observed_at=_START - timedelta(hours=1),
    )


def _provider_event(
    *,
    participants: tuple[str, str] = ("Team A", "Team B"),
    competition: str = "League One",
    best_of: int | None = 3,
) -> ProviderEvent:
    return ProviderEvent(
        provider_event_id="provider-event",
        game_title=GameTitle.LEAGUE_OF_LEGENDS,
        competition=competition,
        participants=participants,
        starts_at=_START,
        best_of=best_of,
        status=EventStatus.SCHEDULED,
        collected_at=_START - timedelta(minutes=5),
        source_reference="fixture:map-003",
    )
