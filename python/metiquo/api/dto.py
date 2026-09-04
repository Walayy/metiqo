"""DTO HTTP indépendants des modèles de persistance."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from metiquo.config import DataMode
from metiquo.contracts import ContractMetadata
from metiquo.contracts.base import ContractModel, NonEmptyText


class ApiModel(ContractModel):
    """Base stricte des contrats publics."""


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
