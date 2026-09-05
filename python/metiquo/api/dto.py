"""DTO HTTP indépendants des modèles de persistance."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from metiquo.config import DataMode
from metiquo.contracts import ContractMetadata
from metiquo.contracts.base import ContractModel, FiniteDecimal, NonEmptyText, PositiveDecimal
from metiquo.contracts.enums import GameTitle, MarketType, PaperBetStatus


class ApiModel(ContractModel):
    """Base stricte des contrats publics."""


class ApiRequestModel(BaseModel):
    """Frontière JSON qui parse les types avant l'appel des services stricts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class HealthResponse(ApiModel):
    """Santé du processus, indépendante des services externes."""

    status: Literal["ok"] = "ok"


class DependencyStatus(ApiModel):
    """État synthétique d'une dépendance de disponibilité."""

    status: Literal["available", "unavailable"]
    reason_code: str | None = Field(default=None, alias="reasonCode")


class ReadyResponse(ApiModel):
    """Disponibilité globale de l'API."""

    status: Literal["ready", "not_ready"]
    dependencies: dict[str, DependencyStatus]


class SystemStatusResponse(ApiModel):
    """État minimal versionné du système."""

    status: Literal["ready", "degraded"]
    api_version: str = Field(alias="apiVersion")
    data_mode: DataMode = Field(alias="dataMode")
    generated_at: datetime = Field(alias="generatedAt")
    dependencies: dict[str, DependencyStatus]


class ProblemDetails(ApiModel):
    """Erreur HTTP compatible RFC 9457, successeur de RFC 7807."""

    type_uri: str = Field(default="about:blank", alias="type")
    title: str
    status: int
    detail: str
    instance: str
    code: str
    context: dict[str, str | int | bool | None] = Field(default_factory=dict)


class PageInfo(ApiModel):
    """Fenêtre de pagination stable pour toute collection."""

    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class PageResponse[ResponseData](ApiModel):
    """Collection métier paginée avec provenance commune."""

    data: tuple[ResponseData, ...]
    page: PageInfo
    meta: ContractMetadata


class ItemResponse[ResponseData](ApiModel):
    """Ressource métier unitaire avec provenance commune."""

    data: ResponseData
    meta: ContractMetadata


class OpportunityExplanation(ApiModel):
    """Explication stable d'une décision de pricing mock."""

    signal_id: UUID = Field(alias="signalId")
    reference: NonEmptyText
    publishable: bool
    reasons: tuple[NonEmptyText, ...]


class CapabilityEvaluationDto(ApiModel):
    """Matrice publique d'une capacité évaluée sur un snapshot précis."""

    snapshot_id: UUID = Field(alias="snapshotId")
    capability: NonEmptyText
    kind: Literal["label", "feature", "market"]
    status: Literal["enabled", "disabled", "pending"]
    reason_codes: tuple[NonEmptyText, ...] = Field(alias="reasonCodes")
    threshold_version: NonEmptyText = Field(alias="thresholdVersion")
    evaluation_revision: int = Field(ge=1, alias="evaluationRevision")
    required_columns: tuple[NonEmptyText, ...] = Field(alias="requiredColumns")
    observed_columns: tuple[NonEmptyText, ...] = Field(alias="observedColumns")
    minimum_completeness: FiniteDecimal = Field(alias="minimumCompleteness")
    observed_completeness: FiniteDecimal = Field(alias="observedCompleteness")
    minimum_sample_size: int = Field(ge=0, alias="minimumSampleSize")
    observed_sample_size: int = Field(ge=0, alias="observedSampleSize")
    gates: dict[str, bool | None]
    evaluated_at: datetime = Field(alias="evaluatedAt")


class TrainModelRequest(ApiRequestModel):
    game_title: GameTitle = Field(default=GameTitle.LEAGUE_OF_LEGENDS, alias="gameTitle")
    market_type: MarketType = Field(default=MarketType.MATCH_WINNER, alias="marketType")


class ModelDecisionRequest(ApiRequestModel):
    reason: NonEmptyText


class CreatePaperBetRequest(ApiRequestModel):
    signal_id: UUID = Field(alias="signalId")
    stake_amount: PositiveDecimal = Field(alias="stakeAmount")
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")


class SettlePaperBetRequest(ApiRequestModel):
    paper_bet_id: UUID = Field(alias="paperBetId")
    status: PaperBetStatus
    profit_loss: FiniteDecimal = Field(alias="profitLoss")
    reason: NonEmptyText


class MappingDecisionRequest(ApiRequestModel):
    reviewer: NonEmptyText
    reason: NonEmptyText
    candidate_event_id: UUID | None = Field(default=None, alias="candidateEventId")


class CreateAliasRequest(ApiRequestModel):
    provider: NonEmptyText
    alias: NonEmptyText
    canonical_id: UUID = Field(alias="canonicalId")
    entity_type: Literal["team", "competition", "player"] = Field(
        default="team", alias="entityType"
    )
    reviewer: NonEmptyText = "admin-local"
    reason: NonEmptyText = "Alias créé manuellement"
