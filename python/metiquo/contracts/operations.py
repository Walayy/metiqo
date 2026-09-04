"""Contrats synthétiques pour les lectures d'exploitation."""

from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from metiquo.contracts.base import ContractModel, NonEmptyText, UtcDateTime
from metiquo.contracts.enums import DataMode


class IngestionRunSummary(ContractModel):
    """Exécution observable d'une synchronisation de données."""

    run_id: UUID = Field(alias="runId")
    source: NonEmptyText
    status: Literal["succeeded", "failed"]
    started_at: UtcDateTime = Field(alias="startedAt")
    completed_at: UtcDateTime = Field(alias="completedAt")
    row_count: int = Field(alias="rowCount", ge=0)
    data_mode: DataMode = Field(alias="dataMode")
    last_valid_snapshot_id: UUID | None = Field(default=None, alias="lastValidSnapshotId")

    @model_validator(mode="after")
    def completion_follows_start(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("Une ingestion ne peut pas finir avant son début")
        return self


class DataQualityIssue(ContractModel):
    """Anomalie métier lisible sans exposer le payload source."""

    issue_id: UUID = Field(alias="issueId")
    source: NonEmptyText
    code: NonEmptyText
    severity: Literal["warning", "blocking"]
    status: Literal["open", "quarantined"]
    detail: NonEmptyText
    observed_at: UtcDateTime = Field(alias="observedAt")
    data_mode: DataMode = Field(alias="dataMode")


class JobSummary(ContractModel):
    """État public minimal d'un job orchestré."""

    job_id: UUID = Field(alias="jobId")
    name: NonEmptyText
    status: Literal["idle", "succeeded", "failed", "running"]
    last_run_at: UtcDateTime | None = Field(default=None, alias="lastRunAt")
    data_mode: DataMode = Field(alias="dataMode")
