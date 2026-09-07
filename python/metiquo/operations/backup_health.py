"""Projection des dernières preuves de sauvegarde, sans ouvrir les fichiers privés."""

from datetime import datetime, timedelta

from sqlalchemy import Connection, select

from metiquo.config import Settings
from metiquo.contracts.system import BackupOperationalHealth
from metiquo.db.ops_models import BackupRunRecord
from metiquo.operations.backup import repository_fingerprint


def backup_health(
    connection: Connection, settings: Settings, now: datetime
) -> BackupOperationalHealth:
    if not settings.backup_enabled:
        return BackupOperationalHealth(status="not_configured")
    repository = BackupRunRecord.repository_fingerprint == repository_fingerprint(settings)
    successful_run = connection.execute(
        select(BackupRunRecord.finished_at, BackupRunRecord.started_at)
        .where(
            repository,
            BackupRunRecord.status == "succeeded",
            BackupRunRecord.retained.is_(True),
        )
        .order_by(BackupRunRecord.finished_at.desc(), BackupRunRecord.started_at.desc())
        .limit(1)
    ).one_or_none()
    success = successful_run.finished_at if successful_run else None
    failure = connection.execute(
        select(BackupRunRecord.finished_at, BackupRunRecord.started_at, BackupRunRecord.error_code)
        .where(
            repository,
            BackupRunRecord.status == "failed",
        )
        .order_by(
            BackupRunRecord.finished_at.desc(),
            BackupRunRecord.started_at.desc(),
            BackupRunRecord.id.desc(),
        )
        .limit(1)
    ).one_or_none()
    interrupted = connection.scalar(
        select(BackupRunRecord.id)
        .where(
            repository,
            BackupRunRecord.status == "running",
            BackupRunRecord.started_at < now - timedelta(seconds=settings.backup_timeout_seconds),
        )
        .limit(1)
    )
    failed_at = failure.finished_at if failure else None
    if (success is not None and success > now) or (failed_at is not None and failed_at > now):
        return BackupOperationalHealth(status="failed", error_code="BACKUP_TIMESTAMP_INVALID")
    if interrupted is not None:
        return BackupOperationalHealth(
            status="failed",
            last_success_at=success,
            last_failure_at=failed_at,
            error_code="BACKUP_INTERRUPTED",
        )
    recovered_interruption = (
        failure is not None
        and successful_run is not None
        and failure.error_code == "BACKUP_INTERRUPTED"
        and failure.started_at < successful_run.started_at
        and failed_at == success
    )
    if (
        failed_at is not None
        and (success is None or failed_at >= success)
        and not recovered_interruption
    ):
        return BackupOperationalHealth(
            status="failed",
            last_success_at=success,
            last_failure_at=failed_at,
            error_code=failure.error_code if failure else None,
        )
    return BackupOperationalHealth(
        status="missing"
        if success is None
        else "stale"
        if (now - success).total_seconds() > settings.backup_freshness_sla_seconds
        else "fresh",
        last_success_at=success,
        last_failure_at=failed_at,
    )
