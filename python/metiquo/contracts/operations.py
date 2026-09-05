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
    snapshot_sha256: str | None = Field(
        default=None,
        alias="snapshotSha256",
        pattern=r"^[0-9a-f]{64}$",
    )
    season_year: int | None = Field(default=None, alias="seasonYear", ge=2014, le=2200)
    min_event_date: UtcDateTime | None = Field(default=None, alias="minEventDate")
    max_event_date: UtcDateTime | None = Field(default=None, alias="maxEventDate")
    schema_fingerprint: str | None = Field(
        default=None,
        alias="schemaFingerprint",
        pattern=r"^[0-9a-f]{64}$",
    )
    schema_changed: bool | None = Field(default=None, alias="schemaChanged")
    run_kind: str | None = Field(default=None, alias="runKind")
    transport: str | None = None
    error_code: str | None = Field(default=None, alias="errorCode")

    @model_validator(mode="after")
    def completion_follows_start(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("Une ingestion ne peut pas finir avant son début")
        if (
            self.min_event_date is not None
            and self.max_event_date is not None
            and self.max_event_date < self.min_event_date
        ):
            raise ValueError("La fin de couverture ne peut pas précéder son début")
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


class AuditEntry(ContractModel):
    """Trace immutable d'une mutation applicative mock."""

    audit_id: UUID = Field(alias="auditId")
    action: NonEmptyText
    resource_id: NonEmptyText | None = Field(default=None, alias="resourceId")
    idempotency_fingerprint: str = Field(alias="idempotencyFingerprint", pattern=r"^[0-9a-f]{64}$")
    occurred_at: UtcDateTime = Field(alias="occurredAt")
    data_mode: DataMode = Field(alias="dataMode")


class AliasRecord(ContractModel):
    """Alias provider résolu vers une entité canonique."""

    alias_id: UUID = Field(alias="aliasId")
    provider: NonEmptyText
    alias: NonEmptyText
    canonical_id: UUID = Field(alias="canonicalId")
    created_at: UtcDateTime = Field(alias="createdAt")
    data_mode: DataMode = Field(alias="dataMode")
