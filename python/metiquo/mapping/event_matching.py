"""Scoring versionné et audit PostgreSQL du matching d'événements."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, Table, insert, select

from metiquo.contracts import Event
from metiquo.contracts.enums import SelectionType
from metiquo.contracts.odds_provider import ProviderEvent
from metiquo.db.mapping_models import EntityAlias
from metiquo.db.odds_models import (
    EventMappingAttempt,
    EventMappingCandidateScore,
    MappingReviewRecord,
    OddsProviderRecord,
    ProviderOddsEvent,
)
from metiquo.foundation.time import Clock, SystemClock
from metiquo.mapping.normalization import normalize_entity_name

MATCHING_WEIGHTS_VERSION = "event-match-v1"


class EventMappingStatus(StrEnum):
    """Résultat fermé d'une tentative de résolution."""

    AUTO_MATCHED = "auto_matched"
    REVIEW = "review"
    REJECTED = "rejected"


class EventMappingReason(StrEnum):
    """Motif stable de la décision de matching."""

    AUTO_THRESHOLD = "AUTO_THRESHOLD"
    REVIEW_THRESHOLD = "REVIEW_THRESHOLD"
    AMBIGUOUS_CANDIDATES = "AMBIGUOUS_CANDIDATES"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    UNRESOLVED_PARTICIPANT = "UNRESOLVED_PARTICIPANT"
    NO_CANDIDATE = "NO_CANDIDATE"


class UnresolvedEventMappingError(RuntimeError):
    """Un appelant tente d'utiliser une sélection d'un événement non résolu."""


@dataclass(frozen=True, slots=True)
class EventMatchingWeights:
    """Poids initiaux immuables et explicitement versionnés."""

    teams: Decimal = Decimal("0.60")
    time: Decimal = Decimal("0.20")
    competition: Decimal = Decimal("0.15")
    format: Decimal = Decimal("0.05")
    version: str = MATCHING_WEIGHTS_VERSION

    def __post_init__(self) -> None:
        values = (self.teams, self.time, self.competition, self.format)
        if any(value < 0 or value > 1 for value in values) or sum(values) != Decimal(1):
            raise ValueError("les poids de matching doivent être positifs et sommer à 1")
        if not self.version.strip():
            raise ValueError("la version des poids est obligatoire")


@dataclass(frozen=True, slots=True)
class EventMatchingPolicy:
    """Seuils initiaux fermés de décision et de proximité."""

    auto_threshold: Decimal = Decimal("0.95")
    review_threshold: Decimal = Decimal("0.75")
    ambiguity_margin: Decimal = Decimal("0.05")

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.review_threshold <= self.auto_threshold <= Decimal(1):
            raise ValueError("les seuils de matching sont incohérents")
        if not Decimal(0) <= self.ambiguity_margin <= Decimal(1):
            raise ValueError("la marge d'ambiguïté doit être comprise entre 0 et 1")


@dataclass(frozen=True, slots=True)
class EventCandidateScore:
    """Décomposition complète du score d'un candidat canonique."""

    event: Event
    team_score: Decimal
    time_score: Decimal
    competition_score: Decimal
    format_score: Decimal
    total_score: Decimal
    selections_inverted: bool


@dataclass(frozen=True, slots=True)
class EventMappingDecision:
    """Décision qui n'expose une identité utilisable qu'après auto-résolution."""

    status: EventMappingStatus
    reason: EventMappingReason
    candidates: tuple[EventCandidateScore, ...]
    weights_version: str
    selected_event_id: UUID | None = None
    attempt_id: UUID | None = None

    @property
    def resolved(self) -> bool:
        return self.status is EventMappingStatus.AUTO_MATCHED

    @property
    def selections_inverted(self) -> bool:
        return bool(self.resolved and self.candidates and self.candidates[0].selections_inverted)

    def remap_selection(self, selection: SelectionType) -> SelectionType:
        """Appliquer A/B seulement lorsqu'une identité a franchi le seuil automatique."""

        if not self.resolved or self.selected_event_id is None:
            raise UnresolvedEventMappingError(
                "un événement ambigu ou rejeté ne peut pas alimenter une prédiction"
            )
        if not self.selections_inverted:
            return selection
        if selection is SelectionType.TEAM_A:
            return SelectionType.TEAM_B
        if selection is SelectionType.TEAM_B:
            return SelectionType.TEAM_A
        return selection


@dataclass(frozen=True, slots=True)
class EventMatchingScorer:
    """Comparer sans fuzzy merge un événement fournisseur aux candidats canoniques."""

    weights: EventMatchingWeights = field(default_factory=EventMatchingWeights)
    policy: EventMatchingPolicy = field(default_factory=EventMatchingPolicy)

    def evaluate(
        self,
        provider_event: ProviderEvent,
        candidates: Sequence[Event],
        aliases: Mapping[UUID, frozenset[str]] = MappingProxyType({}),
    ) -> EventMappingDecision:
        if _has_unresolved_participant(provider_event.participants):
            return EventMappingDecision(
                EventMappingStatus.REJECTED,
                EventMappingReason.UNRESOLVED_PARTICIPANT,
                (),
                self.weights.version,
            )
        scores = tuple(
            sorted(
                (
                    self._score(provider_event, candidate, aliases)
                    for candidate in candidates
                    if candidate.game_title is provider_event.game_title
                ),
                key=lambda item: (-item.total_score, str(item.event.event_id)),
            )
        )
        if not scores:
            return EventMappingDecision(
                EventMappingStatus.REJECTED,
                EventMappingReason.NO_CANDIDATE,
                (),
                self.weights.version,
            )
        top = scores[0]
        close = (
            len(scores) > 1
            and top.total_score - scores[1].total_score <= self.policy.ambiguity_margin
        )
        if close and top.total_score >= self.policy.review_threshold:
            status = EventMappingStatus.REVIEW
            reason = EventMappingReason.AMBIGUOUS_CANDIDATES
            selected = None
        elif top.total_score >= self.policy.auto_threshold:
            status = EventMappingStatus.AUTO_MATCHED
            reason = EventMappingReason.AUTO_THRESHOLD
            selected = top.event.event_id
        elif top.total_score >= self.policy.review_threshold:
            status = EventMappingStatus.REVIEW
            reason = EventMappingReason.REVIEW_THRESHOLD
            selected = None
        else:
            status = EventMappingStatus.REJECTED
            reason = EventMappingReason.LOW_CONFIDENCE
            selected = None
        return EventMappingDecision(
            status,
            reason,
            scores,
            self.weights.version,
            selected_event_id=selected,
        )

    def _score(
        self,
        provider_event: ProviderEvent,
        candidate: Event,
        aliases: Mapping[UUID, frozenset[str]],
    ) -> EventCandidateScore:
        team_score, inverted = _team_score(provider_event, candidate, aliases)
        time_score = _time_score(provider_event.starts_at, candidate.starts_at)
        competition_score = Decimal(
            normalize_entity_name(provider_event.competition)
            == normalize_entity_name(candidate.competition)
        )
        format_score = Decimal(
            provider_event.best_of is not None and provider_event.best_of == candidate.best_of
        )
        total = (
            team_score * self.weights.teams
            + time_score * self.weights.time
            + competition_score * self.weights.competition
            + format_score * self.weights.format
        )
        return EventCandidateScore(
            candidate,
            team_score,
            time_score,
            competition_score,
            format_score,
            total,
            inverted,
        )


@dataclass(frozen=True, slots=True)
class PostgresEventMatchingService:
    """Charger les aliases datés puis persister toute décision et ses composantes."""

    engine: Engine
    clock: Clock = field(default_factory=SystemClock)
    scorer: EventMatchingScorer = field(default_factory=EventMatchingScorer)

    def match_event(
        self,
        provider_code: str,
        provider_event: ProviderEvent,
        candidates: Sequence[Event],
    ) -> EventMappingDecision:
        evaluated_at = self.clock.now().value
        attempt_id = uuid4()
        with self.engine.begin() as connection:
            stored_event_id = _stored_provider_event_id(
                connection,
                provider_code,
                provider_event.provider_event_id,
            )
            aliases = _team_aliases(
                connection,
                provider_code,
                provider_event.starts_at,
                candidates,
            )
            decision = self.scorer.evaluate(provider_event, candidates, aliases)
            _persist_decision(
                connection,
                attempt_id,
                stored_event_id,
                evaluated_at,
                decision,
            )
        return replace(decision, attempt_id=attempt_id)


def _has_unresolved_participant(participants: Sequence[str]) -> bool:
    if len(participants) != 2:
        return True
    markers = ("tbd", "to be determined", "winner of", "loser of")
    return any(
        any(marker in normalize_entity_name(participant) for marker in markers)
        for participant in participants
    )


def _team_score(
    provider_event: ProviderEvent,
    candidate: Event,
    aliases: Mapping[UUID, frozenset[str]],
) -> tuple[Decimal, bool]:
    raw_a, raw_b = (normalize_entity_name(value) for value in provider_event.participants)
    candidate_a = aliases.get(candidate.team_a_id, frozenset()) | {
        normalize_entity_name(candidate.team_a)
    }
    candidate_b = aliases.get(candidate.team_b_id, frozenset()) | {
        normalize_entity_name(candidate.team_b)
    }
    direct = int(raw_a in candidate_a) + int(raw_b in candidate_b)
    inverted = int(raw_a in candidate_b) + int(raw_b in candidate_a)
    best = max(direct, inverted)
    return Decimal(best) / Decimal(2), inverted > direct


def _time_score(provider_time: datetime, candidate_time: datetime) -> Decimal:
    difference = abs(provider_time - candidate_time)
    if difference <= timedelta(minutes=5):
        return Decimal(1)
    if difference <= timedelta(minutes=30):
        return Decimal("0.75")
    if difference <= timedelta(hours=2):
        return Decimal("0.25")
    return Decimal(0)


def _stored_provider_event_id(
    connection: Connection,
    provider_code: str,
    external_event_id: str,
) -> UUID:
    providers = cast(Table, OddsProviderRecord.__table__)
    events = cast(Table, ProviderOddsEvent.__table__)
    value = connection.execute(
        select(events.c.id)
        .join(providers, providers.c.id == events.c.provider_id)
        .where(
            providers.c.code == provider_code,
            events.c.provider_event_id == external_event_id,
        )
    ).scalar_one_or_none()
    if value is None:
        raise LookupError("l'événement fournisseur doit être capturé avant son matching")
    return cast(UUID, value)


def _team_aliases(
    connection: Connection,
    provider_code: str,
    observed_at: datetime,
    candidates: Sequence[Event],
) -> Mapping[UUID, frozenset[str]]:
    team_ids = {
        identifier for event in candidates for identifier in (event.team_a_id, event.team_b_id)
    }
    if not team_ids:
        return MappingProxyType({})
    aliases = cast(Table, EntityAlias.__table__)
    rows = connection.execute(
        select(aliases.c.canonical_id, aliases.c.normalized_alias).where(
            aliases.c.entity_type == "team",
            aliases.c.provider == provider_code,
            aliases.c.canonical_id.in_(team_ids),
            aliases.c.valid_from <= observed_at,
            (aliases.c.valid_to.is_(None) | (aliases.c.valid_to > observed_at)),
        )
    )
    values: dict[UUID, set[str]] = {}
    for canonical_id, normalized_alias in rows:
        values.setdefault(cast(UUID, canonical_id), set()).add(str(normalized_alias))
    return MappingProxyType(
        {canonical_id: frozenset(names) for canonical_id, names in values.items()}
    )


def _persist_decision(
    connection: Connection,
    attempt_id: UUID,
    provider_event_id: UUID,
    evaluated_at: datetime,
    decision: EventMappingDecision,
) -> None:
    attempts = cast(Table, EventMappingAttempt.__table__)
    candidate_scores = cast(Table, EventMappingCandidateScore.__table__)
    top_score = decision.candidates[0].total_score if decision.candidates else Decimal(0)
    top_inverted = bool(decision.candidates and decision.candidates[0].selections_inverted)
    connection.execute(
        insert(attempts).values(
            id=attempt_id,
            provider_event_id=provider_event_id,
            result_status=decision.status,
            selected_event_id=decision.selected_event_id,
            top_score=top_score,
            selections_inverted=top_inverted,
            weights_version=decision.weights_version,
            reason_code=decision.reason,
            evaluated_at=evaluated_at,
        )
    )
    if decision.candidates:
        connection.execute(
            insert(candidate_scores),
            [
                {
                    "id": uuid4(),
                    "attempt_id": attempt_id,
                    "canonical_event_id": candidate.event.event_id,
                    "rank": rank,
                    "team_score": candidate.team_score,
                    "time_score": candidate.time_score,
                    "competition_score": candidate.competition_score,
                    "format_score": candidate.format_score,
                    "total_score": candidate.total_score,
                    "selections_inverted": candidate.selections_inverted,
                }
                for rank, candidate in enumerate(decision.candidates, start=1)
            ],
        )
    if decision.status is EventMappingStatus.REVIEW:
        reviews = cast(Table, MappingReviewRecord.__table__)
        connection.execute(
            insert(reviews).values(
                id=uuid4(),
                attempt_id=attempt_id,
                status="pending",
                selected_event_id=None,
                created_at=evaluated_at,
                reviewed_at=None,
                reviewer=None,
                decision_reason=None,
            )
        )
