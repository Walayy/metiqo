"""Projections PostgreSQL de santé Oracle's Elixir pour l'API réelle."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import Connection, Engine, Table, and_, case, func, literal, select, true, union_all
from sqlalchemy.sql import Select

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
from metiquo.repositories.pagination import ReadPage, page_rows

_PROVIDER = "oracles_elixir"
_DATASET = "league_of_legends_match_data"


@dataclass(frozen=True, slots=True)
class PostgresAdminRepository:
    """Lire des DTO publics sans exposer de payload source ni de secret."""

    engine: Engine
    clock: Clock = field(default_factory=SystemClock)
    odds_max_age_seconds: int = 90
    odds_provider_max_age_seconds: Mapping[str, int] = field(default_factory=dict)
    oe_freshness_sla_seconds: int = 10800
    oe_current_year: int | None = None

    def list_data_sources(self) -> tuple[ProviderHealth, ...]:
        """Réunir la source historique et chaque fournisseur de cotes observé."""

        return (self._oracle_data_source(), *self._odds_data_sources())

    def _oracle_data_source(self) -> ProviderHealth:
        catalogs = cast(Table, SourceCatalog.__table__)
        snapshots = cast(Table, Snapshot.__table__)
        runs = cast(Table, IngestionRun.__table__)
        quarantine = cast(Table, QuarantineItem.__table__)
        year_filter = (
            catalogs.c.season_year == self.oe_current_year
            if self.oe_current_year is not None
            else true()
        )
        with self.engine.connect() as connection:
            catalog_rows = connection.execute(
                select(catalogs.c.status).where(
                    catalogs.c.provider == _PROVIDER,
                    catalogs.c.dataset == _DATASET,
                    year_filter,
                )
            ).all()
            last_success = connection.execute(
                select(func.max(snapshots.c.validated_at))
                .join(catalogs, snapshots.c.source_catalog_id == catalogs.c.id)
                .where(
                    catalogs.c.provider == _PROVIDER,
                    catalogs.c.dataset == _DATASET,
                    snapshots.c.status == "validated",
                    snapshots.c.id == catalogs.c.current_snapshot_id,
                    year_filter,
                )
            ).scalar_one()
            confirmed_at = connection.scalar(
                select(func.max(runs.c.finished_at))
                .join(catalogs, runs.c.source_catalog_id == catalogs.c.id)
                .where(
                    catalogs.c.provider == _PROVIDER,
                    catalogs.c.dataset == _DATASET,
                    year_filter,
                    runs.c.snapshot_id == catalogs.c.current_snapshot_id,
                    runs.c.status == "succeeded",
                    runs.c.counters["contentVerified"].astext == "true",
                )
            )
            if last_success is not None and confirmed_at is not None:
                last_success = max(last_success, confirmed_at)
            last_failure = connection.execute(
                select(func.max(runs.c.finished_at))
                .join(catalogs, runs.c.source_catalog_id == catalogs.c.id)
                .where(
                    catalogs.c.provider == _PROVIDER,
                    catalogs.c.dataset == _DATASET,
                    runs.c.status == "failed",
                    year_filter,
                )
            ).scalar_one()
            failure_count = connection.execute(
                select(func.count(runs.c.id))
                .join(catalogs, runs.c.source_catalog_id == catalogs.c.id)
                .where(
                    catalogs.c.provider == _PROVIDER,
                    catalogs.c.dataset == _DATASET,
                    runs.c.status == "failed",
                    year_filter,
                )
            ).scalar_one()
            last_quarantine = connection.execute(
                select(func.max(quarantine.c.quarantined_at))
                .join(snapshots, quarantine.c.snapshot_id == snapshots.c.id)
                .join(catalogs, snapshots.c.source_catalog_id == catalogs.c.id)
                .where(
                    catalogs.c.provider == _PROVIDER,
                    catalogs.c.dataset == _DATASET,
                    year_filter,
                )
            ).scalar_one()
        checked_at = self.clock.now().value
        future_proof = last_success is not None and last_success > checked_at
        if not catalog_rows:
            status = ProviderStatus.UNAVAILABLE
            detail = "Aucune source Oracle's Elixir n'est cataloguée"
        elif last_success is None:
            status = ProviderStatus.UNAVAILABLE
            detail = "Aucun snapshot Oracle's Elixir validé"
        elif future_proof:
            status = ProviderStatus.DEGRADED
            detail = "Horodatage de confirmation incohérent : date future"
            last_success = None
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
        freshness = _status_freshness(status, last_success is not None)
        if status is ProviderStatus.OPERATIONAL and (
            age_seconds is not None and age_seconds > self.oe_freshness_sla_seconds
        ):
            status, freshness = ProviderStatus.DEGRADED, FreshnessStatus.STALE
            detail = (
                f"Dernière confirmation de contenu hors SLA ({self.oe_freshness_sla_seconds} s)"
            )
        return ProviderHealth(
            provider_code=_PROVIDER,
            status=status,
            checked_at=checked_at,
            last_success_at=last_success,
            last_capture_at=last_success,
            age_seconds=age_seconds,
            failure_count=int(failure_count),
            freshness=freshness,
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
            health_rows = connection.execute(
                select(health)
                .distinct(health.c.provider_id)
                .order_by(
                    health.c.provider_id,
                    health.c.checked_at.desc(),
                    case((health.c.status.in_(("degraded", "unavailable")), 1), else_=0).desc(),
                    health.c.id.desc(),
                )
            ).mappings()
            latest_by_provider = {row["provider_id"]: row for row in health_rows}
            captures = dict(
                connection.execute(
                    select(snapshots.c.provider_id, func.max(snapshots.c.captured_at)).group_by(
                        snapshots.c.provider_id
                    )
                )
                .tuples()
                .all()
            )
            counts = dict(
                connection.execute(
                    select(health.c.provider_id, func.count(health.c.id))
                    .where(health.c.status.in_(("degraded", "unavailable")))
                    .group_by(health.c.provider_id)
                )
                .tuples()
                .all()
            )
            for provider in provider_rows:
                provider_id = cast(UUID, provider["id"])
                latest_health = latest_by_provider.get(provider_id)
                last_capture = captures.get(provider_id)
                failures = int(counts.get(provider_id, 0))
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

    @staticmethod
    def _run_statement() -> Select[tuple[Any, ...]]:
        runs = cast(Table, IngestionRun.__table__)
        catalogs = cast(Table, SourceCatalog.__table__)
        snapshots = cast(Table, Snapshot.__table__)
        return (
            select(
                runs,
                catalogs.c.season_year,
                catalogs.c.current_snapshot_id,
                snapshots.c.sha256,
                snapshots.c.manifest,
            )
            .join(catalogs, runs.c.source_catalog_id == catalogs.c.id)
            .outerjoin(
                snapshots,
                runs.c.snapshot_id == snapshots.c.id,
            )
            .where(
                catalogs.c.provider == _PROVIDER,
                catalogs.c.dataset == _DATASET,
                runs.c.status.in_(("succeeded", "failed")),
            )
            .order_by(runs.c.started_at.desc(), runs.c.id.desc())
        )

    def list_ingestion_runs(self) -> tuple[IngestionRunSummary, ...]:
        with self.engine.connect() as connection:
            rows = tuple(connection.execute(self._run_statement()).mappings())
            fingerprints = _schema_change_map(connection, tuple(row["snapshot_id"] for row in rows))
        return tuple(self._run_summary(row, fingerprints) for row in rows)

    def ingestion_runs_page(
        self, *, offset: int = 0, limit: int = 20, status: str | None = None
    ) -> ReadPage[IngestionRunSummary]:
        statement = self._run_statement()
        if status is not None:
            statement = statement.where(IngestionRun.status == status)
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            page = page_rows(connection, statement, offset=offset, limit=limit)
            fingerprints = _schema_change_map(
                connection, tuple(row["snapshot_id"] for row in page.items)
            )
        return ReadPage(
            tuple(self._run_summary(row, fingerprints) for row in page.items), page.total
        )

    def get_ingestion_run(self, run_id: UUID) -> IngestionRunSummary | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(self._run_statement().where(IngestionRun.id == run_id))
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            fingerprints = _schema_change_map(connection, (row["snapshot_id"],))
        return self._run_summary(row, fingerprints)

    @staticmethod
    def _quality_statement() -> Select[tuple[Any, ...]]:
        issues, runs = cast(Table, QualityIssue.__table__), cast(Table, IngestionRun.__table__)
        catalogs, snapshots = cast(Table, SourceCatalog.__table__), cast(Table, Snapshot.__table__)
        quarantine = cast(Table, QuarantineItem.__table__)
        source = func.concat(_PROVIDER + "/", catalogs.c.season_year)
        scope = and_(catalogs.c.provider == _PROVIDER, catalogs.c.dataset == _DATASET)
        severity = case((issues.c.severity == "blocking", "blocking"), else_="warning")
        status = case((snapshots.c.status == "quarantined", "quarantined"), else_="open")
        entries = union_all(
            select(
                issues.c.id,
                issues.c.created_at.label("observed_at"),
                severity.label("severity"),
                status.label("status"),
                func.jsonb_build_object(
                    "issueId",
                    issues.c.id,
                    "source",
                    source,
                    "code",
                    issues.c.code,
                    "severity",
                    severity,
                    "status",
                    status,
                    "detail",
                    issues.c.message,
                    "observedAt",
                    issues.c.created_at,
                    "dataMode",
                    "real",
                ).label("document"),
            )
            .join(runs, issues.c.run_id == runs.c.id)
            .join(catalogs, runs.c.source_catalog_id == catalogs.c.id)
            .outerjoin(snapshots, issues.c.snapshot_id == snapshots.c.id)
            .where(scope),
            select(
                quarantine.c.id,
                quarantine.c.quarantined_at.label("observed_at"),
                literal("blocking").label("severity"),
                literal("quarantined").label("status"),
                func.jsonb_build_object(
                    "issueId",
                    quarantine.c.id,
                    "source",
                    source,
                    "code",
                    quarantine.c.reason_code,
                    "severity",
                    "blocking",
                    "status",
                    "quarantined",
                    "detail",
                    "Snapshot isolé ; le dernier snapshot validé reste publié",
                    "observedAt",
                    quarantine.c.quarantined_at,
                    "dataMode",
                    "real",
                ).label("document"),
            )
            .join(snapshots, quarantine.c.snapshot_id == snapshots.c.id)
            .join(catalogs, snapshots.c.source_catalog_id == catalogs.c.id)
            .where(scope),
        ).subquery("quality_entries")
        return select(entries).order_by(entries.c.observed_at.desc(), entries.c.id.desc())

    def list_quality_issues(self) -> tuple[DataQualityIssue, ...]:
        with self.engine.connect() as connection:
            rows = connection.execute(self._quality_statement()).mappings()
            return tuple(
                DataQualityIssue.model_validate_json(json.dumps(row["document"])) for row in rows
            )

    def quality_issues_page(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        severity: str | None = None,
        status: str | None = None,
    ) -> ReadPage[DataQualityIssue]:
        statement = self._quality_statement()
        if severity is not None:
            statement = statement.where(statement.selected_columns.severity == severity)
        if status is not None:
            statement = statement.where(statement.selected_columns.status == status)
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            page = page_rows(connection, statement, offset=offset, limit=limit)
        return ReadPage(
            tuple(
                DataQualityIssue.model_validate_json(json.dumps(row["document"]))
                for row in page.items
            ),
            page.total,
        )

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
    connection: Connection, snapshot_ids: tuple[UUID | None, ...]
) -> dict[UUID, bool]:
    if not snapshot_ids:
        return {}
    snapshots = cast(Table, Snapshot.__table__)
    fingerprint = snapshots.c.manifest["schemaFingerprint"].astext
    history = (
        select(
            snapshots.c.id,
            fingerprint.label("fingerprint"),
            func.lag(snapshots.c.id)
            .over(
                partition_by=snapshots.c.source_catalog_id,
                order_by=(snapshots.c.validated_at, snapshots.c.id),
            )
            .label("previous_id"),
            func.lag(fingerprint)
            .over(
                partition_by=snapshots.c.source_catalog_id,
                order_by=(snapshots.c.validated_at, snapshots.c.id),
            )
            .label("previous_fingerprint"),
        )
        .where(snapshots.c.status == "validated")
        .subquery("schema_history")
    )
    rows = connection.execute(
        select(
            history.c.id,
            and_(
                history.c.previous_id.is_not(None),
                history.c.fingerprint.is_distinct_from(history.c.previous_fingerprint),
            ),
        ).where(history.c.id.in_(snapshot_ids))
    )
    return {identity: bool(changed) for identity, changed in rows}


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
