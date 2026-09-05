"""Contrats de prédiction, de value et d'opportunité."""

from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from metiquo.contracts.base import (
    ContractModel,
    DecimalOddsValue,
    ExpectedValueDecimal,
    NonEmptyText,
    NonNegativeDecimal,
    ProbabilityValue,
    SignedUnitValue,
    UtcDateTime,
    VersionText,
)
from metiquo.contracts.entities import Event, Market, OddsSnapshot
from metiquo.contracts.enums import (
    AbstentionReason,
    DataMode,
    FreshnessStatus,
    ModelStatus,
    SelectionType,
    ValueGrade,
)


class Prediction(ContractModel):
    """Probabilité indépendante des cotes et liée à son cutoff."""

    prediction_id: UUID = Field(alias="predictionId")
    event_id: UUID = Field(alias="eventId")
    market_id: UUID = Field(alias="marketId")
    selection: SelectionType
    probability: ProbabilityValue
    probability_low: ProbabilityValue = Field(alias="probabilityLow")
    probability_high: ProbabilityValue = Field(alias="probabilityHigh")
    confidence: ProbabilityValue
    confidence_reduction_reasons: tuple[NonEmptyText, ...] = Field(
        default=(),
        alias="confidenceReductionReasons",
    )
    data_coverage: ProbabilityValue = Field(alias="dataCoverage")
    out_of_distribution_distance: NonNegativeDecimal = Field(alias="outOfDistributionDistance")
    prediction_cutoff: UtcDateTime = Field(alias="predictionCutoff")
    model_version_id: UUID = Field(alias="modelVersionId")
    model_version: VersionText = Field(alias="modelVersion")
    feature_snapshot_id: UUID = Field(alias="featureSnapshotId")
    created_at: UtcDateTime = Field(alias="createdAt")

    @model_validator(mode="after")
    def interval_contains_probability(self) -> Self:
        if not self.probability_low <= self.probability <= self.probability_high:
            raise ValueError("La probabilité doit appartenir à son intervalle")
        if self.created_at < self.prediction_cutoff:
            raise ValueError("La prédiction ne peut pas être créée avant son cutoff")
        return self


class Value(ContractModel):
    """Comparaison exacte entre prix du modèle et prix observé."""

    policy_version: VersionText = Field(alias="policyVersion")
    fair_odds: DecimalOddsValue = Field(alias="fairOdds")
    edge: SignedUnitValue
    expected_value: ExpectedValueDecimal = Field(alias="expectedValue")
    conservative_expected_value: ExpectedValueDecimal = Field(alias="conservativeExpectedValue")
    grade: ValueGrade


class Quality(ContractModel):
    """Qualité, fraîcheur et abstentions associées à une décision."""

    mapping_confidence: ProbabilityValue = Field(alias="mappingConfidence")
    source_freshness: FreshnessStatus = Field(alias="sourceFreshness")
    data_coverage: ProbabilityValue = Field(alias="dataCoverage")
    model_status: ModelStatus = Field(alias="modelStatus")
    abstention_reasons: tuple[AbstentionReason, ...] = Field(
        default=(),
        alias="abstentionReasons",
    )
    publishable: bool

    @model_validator(mode="after")
    def publication_matches_abstention(self) -> Self:
        if self.publishable and self.abstention_reasons:
            raise ValueError("Une décision avec abstention ne peut pas être publiable")
        return self


class ContractMetadata(ContractModel):
    """Mode, fraîcheur et version d'une réponse métier."""

    data_mode: DataMode = Field(alias="dataMode")
    freshness: FreshnessStatus
    as_of: UtcDateTime = Field(alias="asOf")
    computed_at: UtcDateTime = Field(alias="computedAt")
    app_version: VersionText = Field(alias="appVersion")

    @model_validator(mode="after")
    def computation_follows_knowledge(self) -> Self:
        if self.computed_at < self.as_of:
            raise ValueError("Le calcul ne peut pas précéder l'instant de connaissance")
        return self


class Opportunity(ContractModel):
    """Signal complet partageable entre implémentations mock et réelle."""

    signal_id: UUID = Field(alias="signalId")
    event: Event
    market: Market
    book: OddsSnapshot
    model: Prediction
    value: Value
    quality: Quality
    meta: ContractMetadata
    explanation_reference: NonEmptyText | None = Field(
        default=None,
        alias="explanationReference",
    )

    @model_validator(mode="after")
    def references_are_consistent(self) -> Self:
        if self.market.event_id != self.event.event_id:
            raise ValueError("Le marché ne référence pas l'événement de l'opportunité")
        if self.book.event_id != self.event.event_id or self.model.event_id != self.event.event_id:
            raise ValueError("La cote ou la prédiction référence un autre événement")
        if self.book.market_id != self.market.market_id:
            raise ValueError("La cote référence un autre marché")
        if self.model.market_id != self.market.market_id:
            raise ValueError("La prédiction référence un autre marché")
        if (
            self.book.selection != self.market.selection
            or self.model.selection != self.market.selection
        ):
            raise ValueError("La sélection doit être identique dans tous les sous-contrats")
        if self.model.prediction_cutoff >= self.event.starts_at:
            raise ValueError("Le cutoff de prédiction doit précéder le début de l'événement")
        if self.value.grade is ValueGrade.BLOCKED and self.quality.publishable:
            raise ValueError("Une opportunité bloquée ne peut pas être publiable")
        if self.quality.publishable and self.book.informational_only:
            raise ValueError("Une cote informative ne peut pas produire une opportunité publiable")
        if self.quality.publishable and self.book.no_vig_probability is None:
            raise ValueError("Une opportunité publiable exige une probabilité bookmaker sans marge")
        if self.quality.publishable and self.market.settlement_rules_version is None:
            raise ValueError("Une opportunité publiable exige des règles de règlement versionnées")
        return self
