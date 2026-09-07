"""Santé opérationnelle mesurée, indépendante de la disponibilité en lecture."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from metiquo.contracts.base import ContractModel, UtcDateTime
from metiquo.contracts.enums import FreshnessStatus


class SourceOperationalHealth(ContractModel):
    status: FreshnessStatus
    snapshot_id: UUID | None = Field(default=None, alias="snapshotId")
    as_of: UtcDateTime | None = Field(default=None, alias="asOf")
    age_seconds: int | None = Field(default=None, alias="ageSeconds", ge=0)
    reason_code: str = Field(alias="reasonCode")


class ModelOperationalHealth(ContractModel):
    status: Literal["fresh", "stale", "missing", "invalid"]
    model_version_id: UUID | None = Field(default=None, alias="modelVersionId")
    trained_at: UtcDateTime | None = Field(default=None, alias="trainedAt")
    training_cutoff: UtcDateTime | None = Field(default=None, alias="trainingCutoff")
    age_seconds: int | None = Field(default=None, alias="ageSeconds", ge=0)


class BackupOperationalHealth(ContractModel):
    status: Literal["not_configured", "missing", "fresh", "stale", "failed"]
    last_success_at: UtcDateTime | None = Field(default=None, alias="lastSuccessAt")
    last_failure_at: UtcDateTime | None = Field(default=None, alias="lastFailureAt")


class ApiProcessMetrics(ContractModel):
    scope: Literal["current_api_process"] = "current_api_process"
    request_count: int = Field(alias="requestCount", ge=0)
    failure_count: int = Field(alias="failureCount", ge=0)
    mean_latency_ms: float | None = Field(default=None, alias="meanLatencyMs", ge=0)


class OperationalMetrics(ContractModel):
    database_scope: Literal["retained_history"] = Field(
        default="retained_history", alias="databaseScope"
    )
    mean_job_duration_seconds: float | None = Field(
        default=None, alias="meanJobDurationSeconds", ge=0
    )
    measured_job_count: int = Field(alias="measuredJobCount", ge=0)
    job_failures: int = Field(alias="jobFailures", ge=0)
    processed_rows: int = Field(alias="processedRows", ge=0)
    anomalies: int = Field(ge=0)
    blocking_anomalies: int = Field(alias="blockingAnomalies", ge=0)
    signals: dict[str, int]
    api: ApiProcessMetrics


class OperationalStatus(ContractModel):
    reads_available: bool = Field(alias="readsAvailable")
    source: SourceOperationalHealth
    model: ModelOperationalHealth
    mapping_backlog: int = Field(alias="mappingBacklog", ge=0)
    job_counts: dict[str, int] = Field(alias="jobCounts")
    backups: BackupOperationalHealth
    metrics: OperationalMetrics
