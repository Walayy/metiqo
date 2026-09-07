"""Santé et agrégats mesurés dans PostgreSQL, sans appel aux fournisseurs externes."""

from datetime import timedelta

from sqlalchemy import Engine, select, text

from metiquo.config import Settings
from metiquo.contracts.enums import FreshnessStatus
from metiquo.contracts.system import (
    ApiProcessMetrics,
    BackupOperationalHealth,
    ModelOperationalHealth,
    OperationalMetrics,
    OperationalStatus,
    SourceOperationalHealth,
)
from metiquo.db.raw_models import SourceCatalog
from metiquo.foundation.time import Clock
from metiquo.ingestion.freshness import (
    FreshnessPolicy,
    FreshnessService,
    PostgresFreshnessRepository,
)


class OperationalStatusService:
    def __init__(self, engine: Engine, settings: Settings, clock: Clock) -> None:
        self.engine, self.settings, self.clock = engine, settings, clock

    def snapshot(self, api: ApiProcessMetrics) -> OperationalStatus:
        now = self.clock.now().value
        with self.engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            catalog_id = connection.scalar(
                select(SourceCatalog.id)
                .where(
                    SourceCatalog.provider == "oracles_elixir",
                    SourceCatalog.dataset == "league_of_legends_match_data",
                    SourceCatalog.season_year == self.settings.oe_current_year,
                )
                .order_by(
                    (SourceCatalog.status == "active").desc(), SourceCatalog.updated_at.desc()
                )
                .limit(1)
            )
            source = SourceOperationalHealth(
                status=FreshnessStatus.FAILED, reason_code="SOURCE_CATALOG_MISSING"
            )
            readable = False
            if catalog_id is not None:
                try:
                    decision = FreshnessService(
                        repository=PostgresFreshnessRepository(connection),
                        sla=timedelta(seconds=self.settings.oe_freshness_sla_seconds),
                        clock=self.clock,
                    ).evaluate(catalog_id, policy=FreshnessPolicy(allow_stale=True))
                except ValueError:
                    source = SourceOperationalHealth(
                        status=FreshnessStatus.FAILED, reason_code="SOURCE_TIMESTAMP_INVALID"
                    )
                else:
                    source = SourceOperationalHealth(
                        status=decision.status,
                        snapshot_id=decision.snapshot_id,
                        as_of=decision.as_of,
                        age_seconds=decision.age_seconds,
                        reason_code=decision.reason_code,
                    )
                    readable = decision.usable
            champion = (
                connection.execute(
                    text(
                        "SELECT id, registered_at, training_cutoff_max FROM ml.model_versions "
                        "WHERE status = 'champion' AND game = 'lol' AND market = 'game_winner' "
                        "AND segment = 'global' ORDER BY registered_at DESC LIMIT 1"
                    )
                )
                .mappings()
                .one_or_none()
            )
            model = ModelOperationalHealth(status="missing")
            if champion is not None:
                age = (now - champion["registered_at"]).total_seconds()
                data_age = (now - champion["training_cutoff_max"]).total_seconds()
                model = ModelOperationalHealth(
                    status="invalid"
                    if min(age, data_age) < 0
                    else "stale"
                    if max(age, data_age) > self.settings.model_freshness_sla_seconds
                    else "fresh",
                    model_version_id=champion["id"],
                    trained_at=champion["registered_at"],
                    training_cutoff=champion["training_cutoff_max"],
                    age_seconds=int(age) if age >= 0 else None,
                )
            jobs = dict(
                connection.execute(text("SELECT status, count(*) FROM ops.jobs GROUP BY status"))
                .tuples()
                .all()
            )
            for status in ("queued", "running", "succeeded", "failed", "cancelled", "dead"):
                jobs.setdefault(status, 0)
            duration = connection.execute(
                text(
                    "SELECT count(*) AS n, "
                    "avg(extract(epoch FROM finished_at - started_at)) AS mean "
                    "FROM ops.jobs WHERE finished_at >= started_at"
                )
            ).one()
            processed = connection.scalar(
                text(
                    "SELECT coalesce(sum((counters->>'total')::bigint), 0) "
                    "FROM raw.ingestion_runs WHERE run_kind = 'load' AND status = 'succeeded' "
                    "AND jsonb_typeof(counters->'total') = 'number'"
                )
            )
            anomalies = connection.execute(
                text(
                    "SELECT count(*) AS n, "
                    "count(*) FILTER (WHERE severity = 'blocking') AS blocking "
                    "FROM raw.quality_issues"
                )
            ).one()
            signals = dict(
                connection.execute(
                    text("SELECT grade, count(*) FROM signals.signals GROUP BY grade")
                )
                .tuples()
                .all()
            )
            for grade in ("VALUE", "NO_EDGE", "BLOCKED"):
                signals.setdefault(grade, 0)
            backlog = connection.scalar(
                text("SELECT count(*) FROM odds.mapping_reviews WHERE status = 'pending'")
            )
        return OperationalStatus(
            reads_available=readable,
            source=source,
            model=model,
            mapping_backlog=int(backlog or 0),
            job_counts=jobs,
            backups=BackupOperationalHealth(status="not_configured"),
            metrics=OperationalMetrics(
                mean_job_duration_seconds=float(duration.mean)
                if duration.mean is not None
                else None,
                measured_job_count=int(duration.n),
                job_failures=int(jobs["failed"] + jobs["dead"]),
                processed_rows=int(processed or 0),
                anomalies=int(anomalies.n),
                blocking_anomalies=int(anomalies.blocking),
                signals=signals,
                api=api,
            ),
        )
