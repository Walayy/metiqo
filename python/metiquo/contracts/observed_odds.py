"""Cotes observées avant résolution des identités canoniques."""

from uuid import UUID

from pydantic import Field

from metiquo.contracts.base import ContractModel, DecimalOddsValue, NonEmptyText, UtcDateTime
from metiquo.contracts.enums import FreshnessStatus, MarketPeriod, MarketStatus, ProviderStatus
from metiquo.contracts.odds_provider import ProviderEvent


class ObservedOddsQuote(ContractModel):
    """Dernière observation d'une sélection, distincte d'un signal de value."""

    odds_snapshot_id: UUID = Field(alias="oddsSnapshotId")
    provider: NonEmptyText
    provider_type: NonEmptyText = Field(alias="providerType")
    provider_status: ProviderStatus = Field(alias="providerStatus")
    event: ProviderEvent
    market_label: NonEmptyText = Field(alias="marketLabel")
    period: MarketPeriod
    market_status: MarketStatus = Field(alias="marketStatus")
    selection_label: NonEmptyText = Field(alias="selectionLabel")
    decimal_odds: DecimalOddsValue = Field(alias="decimalOdds")
    captured_at: UtcDateTime = Field(alias="capturedAt")
    age_seconds: int = Field(alias="ageSeconds", ge=0)
    freshness: FreshnessStatus
    informational_only: bool = Field(alias="informationalOnly")
