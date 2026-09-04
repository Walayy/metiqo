"""Contrat append-only d'un pari fictif et de son règlement."""

from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from metiquo.contracts.base import (
    ContractModel,
    DecimalOddsValue,
    FiniteDecimal,
    NonEmptyText,
    PositiveDecimal,
    UtcDateTime,
    VersionText,
)
from metiquo.contracts.enums import PaperBetStatus

SETTLED_PAPER_STATUSES = frozenset(
    {
        PaperBetStatus.WON,
        PaperBetStatus.LOST,
        PaperBetStatus.PUSH,
        PaperBetStatus.VOID,
    }
)


class PaperBet(ContractModel):
    """Décision paper liée aux cotes et prédictions observées à l'entrée."""

    paper_bet_id: UUID = Field(alias="paperBetId")
    signal_id: UUID = Field(alias="signalId")
    prediction_id: UUID = Field(alias="predictionId")
    odds_snapshot_id: UUID = Field(alias="oddsSnapshotId")
    closing_odds_snapshot_id: UUID | None = Field(default=None, alias="closingOddsSnapshotId")
    entry_odds: DecimalOddsValue = Field(alias="entryOdds")
    stake_amount: PositiveDecimal = Field(alias="stakeAmount")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    placed_at: UtcDateTime = Field(alias="placedAt")
    status: PaperBetStatus
    settlement_rules_version: VersionText = Field(alias="settlementRulesVersion")
    settled_at: UtcDateTime | None = Field(default=None, alias="settledAt")
    profit_loss: FiniteDecimal | None = Field(default=None, alias="profitLoss")
    settlement_reason: NonEmptyText | None = Field(default=None, alias="settlementReason")

    @model_validator(mode="after")
    def settlement_fields_match_status(self) -> Self:
        is_settled = self.status in SETTLED_PAPER_STATUSES
        has_settlement = self.settled_at is not None and self.profit_loss is not None
        if is_settled != has_settlement:
            raise ValueError("Le statut et les données de règlement paper sont incohérents")
        if self.settled_at is not None and self.settled_at < self.placed_at:
            raise ValueError("Un règlement ne peut pas précéder la décision paper")
        return self
