"""Contrats indépendants des fournisseurs pour la collecte de cotes."""

from decimal import Decimal
from typing import Self

from pydantic import Field, model_validator

from metiquo.contracts.base import (
    ContractModel,
    DecimalOddsValue,
    NonEmptyText,
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


class ProviderEvent(ContractModel):
    """Projection minimale d'un événement dans le vocabulaire du fournisseur."""

    provider_event_id: NonEmptyText = Field(alias="providerEventId")
    game_title: GameTitle = Field(alias="gameTitle")
    competition: NonEmptyText
    participants: tuple[NonEmptyText, ...] = Field(min_length=2)
    starts_at: UtcDateTime = Field(alias="startsAt")
    best_of: int | None = Field(default=None, alias="bestOf", ge=1, le=9)
    status: EventStatus
    collected_at: UtcDateTime = Field(alias="collectedAt")
    source_reference: VersionText = Field(alias="sourceReference")

    @model_validator(mode="after")
    def participants_are_distinct(self) -> Self:
        normalized = {participant.strip().casefold() for participant in self.participants}
        if len(normalized) != len(self.participants):
            raise ValueError("Les participants fournisseur doivent être distincts")
        return self


class ProviderSelection(ContractModel):
    """Sélection brute accompagnée de sa normalisation canonique."""

    provider_selection_id: NonEmptyText = Field(alias="providerSelectionId")
    selection: SelectionType
    label: NonEmptyText
    decimal_odds: DecimalOddsValue = Field(alias="decimalOdds")


class ProviderMarket(ContractModel):
    """Marché fournisseur suffisant pour le mapping et la capture."""

    provider_event_id: NonEmptyText = Field(alias="providerEventId")
    provider_market_id: NonEmptyText = Field(alias="providerMarketId")
    raw_label: NonEmptyText = Field(alias="rawLabel")
    market_type: MarketType = Field(alias="marketType")
    period: MarketPeriod
    line: Decimal | None = Field(default=None, allow_inf_nan=False)
    selections: tuple[ProviderSelection, ...] = Field(min_length=1)
    status: MarketStatus
    captured_at: UtcDateTime = Field(alias="capturedAt")
    settlement_rules_version: VersionText = Field(alias="settlementRulesVersion")

    @model_validator(mode="after")
    def selections_are_distinct(self) -> Self:
        identities = {selection.provider_selection_id for selection in self.selections}
        normalized = {selection.selection for selection in self.selections}
        if len(identities) != len(self.selections) or len(normalized) != len(self.selections):
            raise ValueError("Les sélections fournisseur doivent être distinctes")
        return self


class OddsCaptureResult(ContractModel):
    """Résultat immuable d'une collecte pour un événement fournisseur."""

    provider_event_id: NonEmptyText = Field(alias="providerEventId")
    captured_at: UtcDateTime = Field(alias="capturedAt")
    snapshots: tuple["OddsSnapshot", ...]

    @model_validator(mode="after")
    def snapshots_match_capture_time(self) -> Self:
        if any(snapshot.captured_at > self.captured_at for snapshot in self.snapshots):
            raise ValueError("Une observation ne peut pas être postérieure à sa capture")
        return self


class ProviderHealth(ContractModel):
    """Santé observable d'un fournisseur sans révéler sa configuration."""

    provider_code: NonEmptyText = Field(alias="providerCode")
    status: ProviderStatus
    checked_at: UtcDateTime = Field(alias="checkedAt")
    last_success_at: UtcDateTime | None = Field(default=None, alias="lastSuccessAt")
    detail: NonEmptyText | None = None

    @model_validator(mode="after")
    def last_success_is_not_in_the_future(self) -> Self:
        if self.last_success_at is not None and self.last_success_at > self.checked_at:
            raise ValueError("Le dernier succès ne peut pas suivre le contrôle de santé")
        return self


from metiquo.contracts.entities import OddsSnapshot  # noqa: E402

OddsCaptureResult.model_rebuild()
