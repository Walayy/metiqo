"""Observations publiques, y compris les marchés hors modèle de pricing."""

from typing import Literal, Self

from pydantic import Field, model_validator

from metiquo.contracts.base import ContractModel, DecimalOddsValue, NonEmptyText, UtcDateTime
from metiquo.contracts.enums import FreshnessStatus
from metiquo.contracts.odds_provider import ProviderEvent


class ScrapedOutcome(ContractModel):
    label: NonEmptyText
    displayed_label: str = Field(alias="displayedLabel", max_length=512)
    odds_text: str = Field(alias="oddsText", max_length=64)
    decimal_odds: DecimalOddsValue | None = Field(alias="decimalOdds")
    status: Literal["open", "suspended", "unavailable"]

    @model_validator(mode="after")
    def open_has_price(self) -> Self:
        if self.status == "open" and self.decimal_odds is None:
            raise ValueError("Une sélection ouverte exige une cote observée")
        return self


class ScrapedMarket(ContractModel):
    label: NonEmptyText
    tab: NonEmptyText
    captured_at: UtcDateTime = Field(alias="capturedAt")
    expanded: bool
    raw_text: str = Field(alias="rawText", max_length=20000)
    outcomes: tuple[ScrapedOutcome, ...] = Field(max_length=512)


class StakeEventCapture(ContractModel):
    event: ProviderEvent
    source_url: str = Field(alias="sourceUrl", max_length=512)
    observed_at: UtcDateTime = Field(alias="observedAt")
    expected_tabs: tuple[str, ...] = Field(alias="expectedTabs", max_length=16)
    visited_tabs: tuple[str, ...] = Field(alias="visitedTabs", max_length=16)
    markets: tuple[ScrapedMarket, ...] = Field(max_length=512)
    warnings: tuple[str, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def capture_is_consistent(self) -> Self:
        if self.source_url != self.event.source_reference:
            raise ValueError("La page source doit correspondre à celle de l'événement")
        if any(m.captured_at > self.observed_at for m in self.markets):
            raise ValueError("Une cote ne peut pas suivre la fin de sa capture")
        if not set(self.visited_tabs) <= set(self.expected_tabs):
            raise ValueError("Onglet non annoncé par la page")
        if set(self.expected_tabs) - set(self.visited_tabs) and not self.warnings:
            raise ValueError("Une capture incomplète exige un avertissement")
        if self.event.collected_at > self.observed_at:
            raise ValueError("L'événement ne peut pas être observé après la fin de la capture")
        return self


class StakePublicEvent(ContractModel):
    capture: StakeEventCapture
    age_seconds: int = Field(alias="ageSeconds", ge=0)
    expires_at: UtcDateTime = Field(alias="expiresAt")
    freshness: FreshnessStatus


class StakeCollectionStatus(ContractModel):
    enabled: bool
    state: Literal[
        "disabled", "never_collected", "operational", "partial", "blocked", "failed", "stale"
    ]
    checked_at: UtcDateTime | None = Field(alias="checkedAt")
    last_success_at: UtcDateTime | None = Field(alias="lastSuccessAt")
    next_attempt_at: UtcDateTime | None = Field(alias="nextAttemptAt")
    detail: str | None
    event_count: int = Field(alias="eventCount", ge=0)
