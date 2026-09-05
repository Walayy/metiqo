"""Contrats de revue des mappings ambigus."""

from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from metiquo.contracts.base import ContractModel, NonEmptyText, ProbabilityValue, UtcDateTime
from metiquo.contracts.enums import MappingReviewStatus


class MappingCandidate(ContractModel):
    """Événement canonique candidat et raisons de son score."""

    event_id: UUID = Field(alias="eventId")
    label: NonEmptyText
    confidence: ProbabilityValue
    reasons: tuple[NonEmptyText, ...]
    team_a_id: UUID | None = Field(default=None, alias="teamAId")
    team_a: NonEmptyText | None = Field(default=None, alias="teamA")
    team_b_id: UUID | None = Field(default=None, alias="teamBId")
    team_b: NonEmptyText | None = Field(default=None, alias="teamB")
    selections_inverted: bool = Field(default=False, alias="selectionsInverted")


class MappingReview(ContractModel):
    """Ambiguïté de mapping dont toute décision reste auditée."""

    mapping_review_id: UUID = Field(alias="mappingReviewId")
    provider: NonEmptyText
    provider_event_id: NonEmptyText = Field(alias="providerEventId")
    raw_competition: NonEmptyText = Field(alias="rawCompetition")
    raw_participants: tuple[NonEmptyText, ...] = Field(alias="rawParticipants", min_length=2)
    candidates: tuple[MappingCandidate, ...]
    status: MappingReviewStatus
    selected_event_id: UUID | None = Field(default=None, alias="selectedEventId")
    affected_snapshot_count: int = Field(default=0, alias="affectedSnapshotCount", ge=0)
    historical_signals_rewritten: int = Field(default=0, alias="historicalSignalsRewritten", ge=0)
    created_at: UtcDateTime = Field(alias="createdAt")
    reviewed_at: UtcDateTime | None = Field(default=None, alias="reviewedAt")
    reviewer: NonEmptyText | None = None
    decision_reason: NonEmptyText | None = Field(default=None, alias="decisionReason")

    @model_validator(mode="after")
    def review_provenance_matches_status(self) -> Self:
        has_decision = self.reviewed_at is not None and self.reviewer is not None
        if (self.status is MappingReviewStatus.PENDING) == has_decision:
            raise ValueError("Le statut de mapping et sa provenance de décision sont incohérents")
        if self.reviewed_at is not None and self.reviewed_at < self.created_at:
            raise ValueError("La revue de mapping ne peut pas précéder sa création")
        return self
