"""DTO HTTP indépendants des modèles de persistance."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from metiquo.config import DataMode
from metiquo.contracts.base import ContractModel


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
