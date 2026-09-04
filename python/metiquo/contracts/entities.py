"""Contrats d'événement, de marché et de cote observée."""

from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from metiquo.contracts.base import (
    ContractModel,
    DecimalOddsValue,
    NonEmptyText,
    ProbabilityValue,
    UtcDateTime,
    VersionText,
)
from metiquo.contracts.enums import (
    EventStatus,
    GameTitle,
    MarketPeriod,
    MarketStatus,
    MarketType,
    ProviderStatus,
    SelectionType,
)


class Event(ContractModel):
    """Événement canonique sans dépendance à un fournisseur."""

    event_id: UUID = Field(alias="eventId")
    game_title: GameTitle = Field(alias="gameTitle")
    competition: NonEmptyText
    team_a_id: UUID = Field(alias="teamAId")
    team_a: NonEmptyText = Field(alias="teamA")
    team_b_id: UUID = Field(alias="teamBId")
    team_b: NonEmptyText = Field(alias="teamB")
    starts_at: UtcDateTime = Field(alias="startsAt")
    best_of: int = Field(alias="bestOf", ge=1, le=9)
    status: EventStatus
    observed_at: UtcDateTime = Field(alias="observedAt")

    @model_validator(mode="after")
    def teams_are_distinct(self) -> Self:
        if self.team_a_id == self.team_b_id or self.team_a.casefold() == self.team_b.casefold():
            raise ValueError("Les deux participants d'un événement doivent être distincts")
        return self


class Market(ContractModel):
    """Marché canonique et sélection normalisée."""

    market_id: UUID = Field(alias="marketId")
    event_id: UUID = Field(alias="eventId")
    type: MarketType
    period: MarketPeriod
    selection: SelectionType
    selection_label: NonEmptyText = Field(alias="selectionLabel")
    line: Decimal | None = Field(default=None, allow_inf_nan=False)
    status: MarketStatus
    settlement_rules_version: VersionText | None = Field(
        default=None,
        alias="settlementRulesVersion",
    )


class OddsSnapshot(ContractModel):
    """Observation de cote immuable, horodatée et traçable."""

    odds_snapshot_id: UUID = Field(alias="oddsSnapshotId")
    event_id: UUID = Field(alias="eventId")
    market_id: UUID = Field(alias="marketId")
    selection: SelectionType
    provider: NonEmptyText
    provider_status: ProviderStatus = Field(alias="providerStatus")
    market_status: MarketStatus = Field(alias="marketStatus")
    decimal_odds: DecimalOddsValue = Field(alias="decimalOdds")
    captured_at: UtcDateTime = Field(alias="capturedAt")
    age_seconds: int = Field(alias="ageSeconds", ge=0)
    raw_implied_probability: ProbabilityValue = Field(alias="rawImpliedProbability")
    no_vig_probability: ProbabilityValue | None = Field(alias="noVigProbability")
    informational_only: bool = Field(default=False, alias="informationalOnly")
    provenance_reference: VersionText = Field(alias="provenanceReference")
