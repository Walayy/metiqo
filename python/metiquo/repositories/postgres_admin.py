"""Projections PostgreSQL de santé Oracle's Elixir pour l'API réelle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import Connection, Engine, Table, case, func, select

from metiquo.contracts import DataQualityIssue, IngestionRunSummary, JobSummary, ProviderHealth
from metiquo.contracts.enums import DataMode, FreshnessStatus, ProviderStatus
from metiquo.db.odds_models import OddsProviderHealth, OddsProviderRecord, OddsSnapshotRecord
from metiquo.db.raw_models import (
    BackfillJob,
    IngestionRun,
    QualityIssue,
    QuarantineItem,
    Snapshot,
    SourceCatalog,
)
from metiquo.foundation.time import Clock, SystemClock

_PROVIDER = "oracles_elixir"
_DATASET = "league_of_legends_match_data"


@dataclass(frozen=True, slots=True)
class PostgresAdminRepository:
    """Lire des DTO publics sans exposer de payload source ni de secret."""

    engine: Engine
    clock: Clock = field(default_factory=SystemClock)
    odds_max_age_seconds: int = 90
    odds_provider_max_age_seconds: Mapping[str, int] = field(default_factory=dict)

    def list_data_sources(self) -> tuple[ProviderHealth, ...]:
        """Réunir la source historique et chaque fournisseur de cotes observé."""

        return (self._oracle_data_source(), *self._odds_data_sources())

    def _oracle_data_source(self) -> ProviderHealth:
        catalogs = cast(Table, SourceCatalog.__table__)
        snapshots = cast(Table, Snapshot.__table__)
        runs = cast(Table, IngestionRun.__table__)
        quarantine = cast(Table, QuarantineItem.__table__)
        with self.engine.connect() as connection:
            catalog_rows = connection.execute(
                select(catalogs.c.status).where(
                    catalogs.c.provider == _PROVIDER,
                    catalogs.c.dataset == _DATASET,
                )
            ).all()
            last_success = connection.execute(
                select(func.max(snapshots.c.validated_at))
                .join(catalogs, snapshots.c.source_catalog_id == catalogs.c.id)
                .where(
                    catalogs.c.provider == _PROVIDER,
                    catalogs.c.dataset == _DATASET,
                    snapshots.c.status == "validated",
                )
            ).scalar_one()
            last_failure = connection.execute(
                select(func.max(runs.c.finished_at))
                .join(catalogs, runs.c.source_catalog_id == catalogs.c.id)
                .where(
                    catalogs.c.provider == _PROVIDER,
                    catalogs.c.dataset == _DATASET,
                    runs.c.status == "failed",
                )
            ).scalar_one()
            failure_count = connection.execute(
                select(func.count(runs.c.id))
                .join(catalogs, runs.c.source_catalog_id == catalogs.c.id)
                .where(
                    catalogs.c.provider == _PROVIDER,
                    catalogs.c.dataset == _DATASET,
                    runs.c.status == "failed",
                )
            ).scalar_one()
            last_quarantine = connection.execute(
                select(func.max(quarantine.c.quarantined_at))
                .join(snapshots, quarantine.c.snapshot_id == snapshots.c.id)
                .join(catalogs, snapshots.c.source_catalog_id == catalogs.c.id)
                .where(
                    catalogs.c.provider == _PROVIDER,
                    catalogs.c.dataset == _DATASET,
                )
            ).scalar_one()
        checked_at = self.clock.now().value
        if last_success is not None and last_success > checked_at:
            checked_at = last_success
        if not catalog_rows:
            status = ProviderStatus.UNAVAILABLE
            detail = "Aucune source Oracle's Elixir n'est cataloguée"
        elif last_success is None:
            status = ProviderStatus.UNAVAILABLE
            detail = "Aucun snapshot Oracle's Elixir validé"
        elif (
            any(str(row.status) != "active" for row in catalog_rows)
            or _not_older(last_failure, last_success)
            or _not_older(last_quarantine, last_success)
        ):
            status = ProviderStatus.DEGRADED
            detail = "Dernier snapshot validé conservé malgré un incident plus récent"
        else:
            status = ProviderStatus.OPERATIONAL
            detail = f"{len(catalog_rows)} source(s) annuelle(s) suivie(s)"
        age_seconds = _age_seconds(checked_at, last_success)
        return ProviderHealth(
            provider_code=_PROVIDER,
            status=status,
            checked_at=checked_at,
            last_success_at=last_success,
            last_capture_at=last_success,
            age_seconds=age_seconds,
            failure_count=int(failure_count),
            freshness=_status_freshness(status, last_success is not None),
            detail=detail,
        )

    def _odds_data_sources(self) -> tuple[ProviderHealth, ...]:
        providers = cast(Table, OddsProviderRecord.__table__)
        health = cast(Table, OddsProviderHealth.__table__)
        snapshots = cast(Table, OddsSnapshotRecord.__table__)
        now = self.clock.now().value
        values: list[ProviderHealth] = []
        with self.engine.connect() as connection:
            provider_rows = connection.execute(
                select(providers).order_by(providers.c.code)
            ).mappings()
            for provider in provider_rows:
                provider_id = cast(UUID, provider["id"])
                latest_health = (
                    connection.execute(
                        select(health)
                        .where(health.c.provider_id == provider_id)
                        .order_by(
                            health.c.checked_at.desc(),
                            case(
                                (
                                    health.c.status.in_(("degraded", "unavailable")),
                                    1,
                                ),
                                else_=0,
                            ).desc(),
                            health.c.id.desc(),
                        )
                        .limit(1)
                    )
                    .mappings()
                    .one_or_none()
                )
                last_capture = cast(
                    datetime | None,
                    connection.execute(
                        select(func.max(snapshots.c.captured_at)).where(
                            snapshots.c.provider_id == provider_id
                        )
                    ).scalar_one(),
                )
                failures = int(
                    connection.execute(
                        select(func.count(health.c.id)).where(
                            health.c.provider_id == provider_id,
                            health.c.status.in_(("degraded", "unavailable")),
                        )
                    ).scalar_one()
                )
                checked_at = max(
                    value
                    for value in (
                        now,
                        last_capture,
                        latest_health["checked_at"] if latest_health is not None else None,
                    )
                    if isinstance(value, datetime)
                )
                if not bool(provider["enabled"]):
                    status = ProviderStatus.DISABLED
                elif latest_health is not None:
                    status = ProviderStatus(str(latest_health["status"]))
                elif last_capture is not None:
                    status = ProviderStatus.OPERATIONAL
                else:
                    status = ProviderStatus.UNAVAILABLE
                last_success = (
                    cast(datetime | None, latest_health["last_success_at"])
                    if latest_health is not None
                    else last_capture
                )
                age_seconds = _age_seconds(checked_at, last_capture)
                max_age = self.odds_provider_max_age_seconds.get(
                    str(provider["code"]), self.odds_max_age_seconds
                )
                freshness = _odds_freshness(status, age_seconds, max_age)
                detail = (
                    str(latest_health["detail"])
                    if latest_health is not None and latest_health["detail"]
                    else None
                )
                if freshness is FreshnessStatus.STALE:
                    detail = f"Dernière capture hors SLA ({max_age} s)"
                values.append(
                    ProviderHealth(
                        provider_code=str(provider["code"]),
                        status=status,
                        checked_at=checked_at,
                        last_success_at=last_success,
                        last_capture_at=last_capture,
                        age_seconds=age_seconds,
                        failure_count=failures,
                        freshness=freshness,
                        detail=detail,
                    )
                )
        return tuple(values)

    def get_data_source(self, provider_code: str) -> ProviderHealth | None:
        return next(
            (item for item in self.list_data_sources() if item.provider_code == provider_code),
            None,
        )

    def list_ingestion_runs(self) -> tuple[IngestionRunSummary, ...]:
        runs = cast(Table, IngestionRun.__table__)
        catalogs = cast(Table, SourceCatalog.__table__)
        snapshots = cast(Table, Snapshot.__table__)
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(
                        runs,
                        catalogs.c.season_year,
                        catalogs.c.current_snapshot_id,
                        snapshots.c.sha256,
                        snapshots.c.manifest,
                    )
                    .join(catalogs, runs.c.source_catalog_id == catalogs.c.id)
                    .outerjoin(snapshots, runs.c.snapshot_id == snapshots.c.id)
                    .where(
                        catalogs.c.provider == _PROVIDER,
                        catalogs.c.dataset == _DATASET,
                        runs.c.status.in_(("succeeded", "failed")),
                    )
                    .order_by(runs.c.started_at.desc())
                )
                .mappings()
                .all()
            )
            fingerprints = _schema_change_map(
                connection=connection, catalogs=catalogs, snapshots=snapshots
            )
        return tuple(self._run_summary(row, fingerprints) for row in rows)

    def get_ingestion_run(self, run_id: UUID) -> IngestionRunSummary | None:
        return next(
            (item for item in self.list_ingestion_runs() if item.run_id == run_id),
            None,
        )

    def list_quality_issues(self) -> tuple[DataQualityIssue, ...]:
        issues = cast(Table, QualityIssue.__table__)
        runs = cast(Table, IngestionRun.__table__)
        catalogs = cast(Table, SourceCatalog.__table__)
        snapshots = cast(Table, Snapshot.__table__)
        quarantine = cast(Table, QuarantineItem.__table__)
        with self.engine.connect() as connection:
            issue_rows = (
                connection.execute(
                    select(
                        issues, catalogs.c.season_year, snapshots.c.status.label("snapshot_status")
                    )
                    .join(runs, issues.c.run_id == runs.c.id)
                    .join(catalogs, runs.c.source_catalog_id == catalogs.c.id)
                    .outerjoin(snapshots, issues.c.snapshot_id == snapshots.c.id)
                    .where(
                        catalogs.c.provider == _PROVIDER,
                        catalogs.c.dataset == _DATASET,
                    )
                    .order_by(issues.c.created_at.desc())
                )
                .mappings()
                .all()
            )
            quarantine_rows = (
                connection.execute(
                    select(quarantine, catalogs.c.season_year)
                    .join(snapshots, quarantine.c.snapshot_id == snapshots.c.id)
                    .join(catalogs, snapshots.c.source_catalog_id == catalogs.c.id)
                    .where(
                        catalogs.c.provider == _PROVIDER,
                        catalogs.c.dataset == _DATASET,
                    )
                    .order_by(quarantine.c.quarantined_at.desc())
                )
                .mappings()
                .all()
            )
        values = [
            DataQualityIssue(
                issue_id=row["id"],
                source=f"{_PROVIDER}/{row['season_year']}",
                code=str(row["code"]),
                severity="blocking" if row["severity"] == "blocking" else "warning",
                status=("quarantined" if row["snapshot_status"] == "quarantined" else "open"),
                detail=str(row["message"]),
                observed_at=row["created_at"],
                data_mode=DataMode.REAL,
            )
            for row in issue_rows
        ]
        values.extend(
            DataQualityIssue(
                issue_id=row["id"],
                source=f"{_PROVIDER}/{row['season_year']}",
                code=str(row["reason_code"]),
                severity="blocking",
                status="quarantined",
                detail="Snapshot isolé ; le dernier snapshot validé reste publié",
                observed_at=row["quarantined_at"],
                data_mode=DataMode.REAL,
            )
            for row in quarantine_rows
        )
        return tuple(sorted(values, key=lambda item: item.observed_at, reverse=True))

    def list_jobs(self) -> tuple[JobSummary, ...]:
        jobs = cast(Table, BackfillJob.__table__)
        with self.engine.connect() as connection:
            rows = connection.execute(select(jobs).order_by(jobs.c.updated_at.desc())).mappings()
            return tuple(
                JobSummary(
                    job_id=row["id"],
                    name=f"oe-backfill-{row['from_year']}-{row['to_year']}",
                    status=cast(
                        Literal["idle", "succeeded", "failed", "running"],
                        str(row["status"]),
                    ),
                    last_run_at=row["finished_at"] or row["updated_at"],
                    data_mode=DataMode.REAL,
                )
                for row in rows
            )

    @staticmethod
    def _run_summary(
        row: object,
        fingerprints: dict[UUID, bool],
    ) -> IngestionRunSummary:
        values = cast(dict[str, object], row)
        manifest = (
            cast(dict[str, object], values["manifest"])
            if isinstance(values.get("manifest"), dict)
            else {}
        )
        counters = (
            cast(dict[str, object], values["counters"])
            if isinstance(values.get("counters"), dict)
            else {}
        )
        snapshot_id = cast(UUID | None, values.get("snapshot_id"))
        completed_at = values.get("finished_at")
        if not isinstance(completed_at, datetime):
            raise RuntimeError("un run terminé doit posséder finished_at")
        return IngestionRunSummary(
            run_id=cast(UUID, values["id"]),
            source=f"{_PROVIDER}/{values['season_year']}",
            status=cast(Literal["succeeded", "failed"], values["status"]),
            started_at=cast(datetime, values["started_at"]),
            completed_at=completed_at,
            row_count=_int_value(counters.get("total"), manifest.get("rowCount")),
            data_mode=DataMode.REAL,
            last_valid_snapshot_id=cast(UUID | None, values.get("current_snapshot_id")),
            snapshot_sha256=(str(values["sha256"]) if values.get("sha256") else None),
            season_year=int(cast(int, values["season_year"])),
            min_event_date=_manifest_datetime(manifest.get("minEventDate")),
            max_event_date=_manifest_datetime(manifest.get("maxEventDate")),
            schema_fingerprint=(
                str(manifest["schemaFingerprint"])
                if manifest.get("schemaFingerprint") is not None
                else None
            ),
            schema_changed=fingerprints.get(snapshot_id) if snapshot_id is not None else None,
            run_kind=str(values["run_kind"]),
            transport=(str(values["transport"]) if values.get("transport") else None),
            error_code=(str(values["error_code"]) if values.get("error_code") else None),
        )


def _schema_change_map(
    *, connection: Connection, catalogs: Table, snapshots: Table
) -> dict[UUID, bool]:
    rows = connection.execute(
        select(snapshots.c.id, snapshots.c.source_catalog_id, snapshots.c.manifest)
        .join(catalogs, snapshots.c.source_catalog_id == catalogs.c.id)
        .where(
            catalogs.c.provider == _PROVIDER,
            catalogs.c.dataset == _DATASET,
            snapshots.c.status == "validated",
        )
        .order_by(snapshots.c.source_catalog_id, snapshots.c.validated_at)
    ).mappings()
    previous: dict[UUID, str | None] = {}
    result: dict[UUID, bool] = {}
    for row in rows:
        catalog_id = cast(UUID, row["source_catalog_id"])
        manifest = cast(dict[str, object], row["manifest"])
        fingerprint = (
            str(manifest["schemaFingerprint"])
            if manifest.get("schemaFingerprint") is not None
            else None
        )
        result[cast(UUID, row["id"])] = (
            catalog_id in previous and previous[catalog_id] != fingerprint
        )
        previous[catalog_id] = fingerprint
    return result


def _not_older(candidate: datetime | None, baseline: datetime | None) -> bool:
    return candidate is not None and (baseline is None or candidate >= baseline)


def _age_seconds(checked_at: datetime, captured_at: datetime | None) -> int | None:
    if captured_at is None:
        return None
    return max(0, int((checked_at - captured_at).total_seconds()))


def _status_freshness(status: ProviderStatus, has_capture: bool) -> FreshnessStatus:
    if status is ProviderStatus.OPERATIONAL:
        return FreshnessStatus.FRESH
    if status is ProviderStatus.DEGRADED and has_capture:
        return FreshnessStatus.DEGRADED
    return FreshnessStatus.FAILED


def _odds_freshness(
    status: ProviderStatus,
    age_seconds: int | None,
    max_age_seconds: int,
) -> FreshnessStatus:
    if age_seconds is None:
        return FreshnessStatus.FAILED
    if status in {ProviderStatus.DEGRADED, ProviderStatus.UNAVAILABLE}:
        return FreshnessStatus.DEGRADED
    if status is ProviderStatus.DISABLED:
        return FreshnessStatus.FAILED
    if age_seconds > max_age_seconds:
        return FreshnessStatus.STALE
    return FreshnessStatus.FRESH


def _manifest_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _int_value(primary: object, fallback: object) -> int:
    if isinstance(primary, int):
        return primary
    return int(fallback) if isinstance(fallback, int) else 0
