"""Contrats synthétiques du registre de modèles et des backtests."""

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from metiquo.contracts.base import (
    ContractModel,
    FiniteDecimal,
    NonEmptyText,
    UtcDateTime,
    VersionText,
)
from metiquo.contracts.enums import BacktestKind, GameTitle, MarketType, ModelStatus


class ModelSummary(ContractModel):
    """Version de modèle traçable avec métriques hors échantillon."""

    model_version_id: UUID = Field(alias="modelVersionId")
    model_version: VersionText = Field(alias="modelVersion")
    game_title: GameTitle = Field(alias="gameTitle")
    market_type: MarketType = Field(alias="marketType")
    algorithm: NonEmptyText
    feature_version: VersionText = Field(alias="featureVersion")
    dataset_hash: str = Field(alias="datasetHash", pattern=r"^[0-9a-f]{64}$")
    artifact_hash: str = Field(alias="artifactHash", pattern=r"^[0-9a-f]{64}$")
    code_commit: str = Field(alias="codeCommit", pattern=r"^[0-9a-f]{7,64}$")
    train_cutoff: UtcDateTime = Field(alias="trainCutoff")
    status: ModelStatus
    metrics: dict[NonEmptyText, FiniteDecimal]
    baseline_metrics: dict[NonEmptyText, FiniteDecimal] = Field(alias="baselineMetrics")
    created_at: UtcDateTime = Field(alias="createdAt")
    promoted_at: UtcDateTime | None = Field(default=None, alias="promotedAt")
    promotion_reason: NonEmptyText | None = Field(default=None, alias="promotionReason")

    @model_validator(mode="after")
    def champion_has_promotion_provenance(self) -> Self:
        if self.status is ModelStatus.CHAMPION and (
            self.promoted_at is None or self.promotion_reason is None
        ):
            raise ValueError("Un champion doit conserver la date et le motif de promotion")
        if self.promoted_at is not None and self.promoted_at < self.created_at:
            raise ValueError("Une promotion ne peut pas précéder la création du modèle")
        return self


class BacktestSummary(ContractModel):
    """Validation temporelle distinguant statistique et financier."""

    backtest_id: UUID = Field(alias="backtestId")
    model_version_id: UUID = Field(alias="modelVersionId")
    kind: BacktestKind
    validation_scheme: Literal["walk_forward"] = Field(
        default="walk_forward",
        alias="validationScheme",
    )
    starts_at: UtcDateTime = Field(alias="startsAt")
    ends_at: UtcDateTime = Field(alias="endsAt")
    sample_count: int = Field(alias="sampleCount", ge=0)
    metrics: dict[NonEmptyText, FiniteDecimal]
    baseline_metrics: dict[NonEmptyText, FiniteDecimal] = Field(alias="baselineMetrics")
    observed_odds_count: int = Field(default=0, alias="observedOddsCount", ge=0)
    uses_only_observed_odds: bool = Field(default=False, alias="usesOnlyObservedOdds")
    final_test_untouched: bool = Field(alias="finalTestUntouched")
    completed_at: UtcDateTime = Field(alias="completedAt")

    @model_validator(mode="after")
    def validate_temporal_and_financial_provenance(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("La fin du backtest doit suivre son début")
        if self.kind is BacktestKind.FINANCIAL and (
            not self.uses_only_observed_odds or self.observed_odds_count == 0
        ):
            raise ValueError("Un backtest financier exige des cotes réellement observées")
        if self.completed_at < self.ends_at:
            raise ValueError("Le backtest ne peut pas être terminé avant sa période évaluée")
        return self
