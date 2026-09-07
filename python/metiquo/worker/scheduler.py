"""Planification UTC durable dans la file existante, sans rafale de rattrapage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select

from metiquo.config import Settings
from metiquo.db.ops_models import JobRecord
from metiquo.db.raw_models import Snapshot, SourceCatalog
from metiquo.foundation.locks import ResourceBusy, oe_scope, resource_lock
from metiquo.foundation.time import normalize_utc_datetime
from metiquo.worker.queue import PostgresJobQueue


@dataclass(frozen=True, slots=True)
class SchedulePolicy:
    current_year: int
    current_seconds: int = 10800
    closed_months: int = 1
    deep_seconds: int = 86400
    settlement_seconds: int = 300
    report_seconds: int = 300
    currency: str = "EUR"
    alerts_seconds: int = 300

    def __post_init__(self) -> None:
        if not 2014 <= self.current_year <= 2200 or not 1 <= self.closed_months <= 12:
            raise ValueError("Année ou période mensuelle invalide")
        if (
            min(
                self.current_seconds,
                self.deep_seconds,
                self.settlement_seconds,
                self.report_seconds,
                self.alerts_seconds,
            )
            < 60
        ):
            raise ValueError("Une fréquence de planification exige au moins 60 secondes")

    @classmethod
    def from_settings(cls, settings: Settings) -> SchedulePolicy:
        return cls(
            settings.oe_current_year,
            settings.oe_sync_interval_seconds,
            settings.oe_closed_audit_months,
            settings.oe_deep_check_interval_seconds,
            settings.paper_settlement_interval_seconds,
            settings.paper_report_interval_seconds,
            settings.paper_bankroll_currency,
            settings.alert_interval_seconds,
        )


@dataclass(frozen=True, slots=True)
class PlannedJob:
    job_type: str
    scope: str
    payload: dict[str, object]
    scheduled_at: datetime

    @property
    def key(self) -> str:
        return f"schedule:{self.job_type}:{self.scope}:{self.scheduled_at.isoformat()}"


def planned_jobs(
    policy: SchedulePolicy, now: datetime, years: dict[int, bool]
) -> tuple[PlannedJob, ...]:
    now = normalize_utc_datetime(now)
    month_index = (now.year * 12 + now.month - 1) // policy.closed_months * policy.closed_months
    monthly = datetime(month_index // 12, month_index % 12 + 1, 1, tzinfo=UTC)

    def slot(seconds: int) -> datetime:
        return datetime.fromtimestamp(int(now.timestamp()) // seconds * seconds, UTC)

    jobs = [PlannedJob("oe.catalog", "oe:catalog", {}, monthly)]
    for year, changed in sorted(years.items()):
        if year > policy.current_year:
            continue
        scope = oe_scope("oracles_elixir", year)
        payload: dict[str, object] = {"year": year}
        if year == policy.current_year:
            jobs.append(PlannedJob("oe.sync", scope, payload, slot(policy.current_seconds)))
        else:
            jobs.append(PlannedJob("oe.audit", scope, payload, monthly))
        if changed:
            jobs.append(PlannedJob("oe.deep", scope, payload, slot(policy.deep_seconds)))
    jobs.extend(
        (
            PlannedJob("ops.alerts", "ops:alerts", {}, slot(policy.alerts_seconds)),
            PlannedJob("paper.settle", "paper:settlement", {}, slot(policy.settlement_seconds)),
            PlannedJob(
                "paper.report",
                f"paper:{policy.currency}",
                {"currency": policy.currency},
                slot(policy.report_seconds),
            ),
        )
    )
    return tuple(jobs)


class PostgresScheduler:
    def __init__(self, queue: PostgresJobQueue, policy: SchedulePolicy) -> None:
        self.queue, self.policy = queue, policy

    def tick(self) -> None:
        try:
            with resource_lock(self.queue.engine, "scheduler"):
                self._tick_locked()
        except ResourceBusy:
            return

    def _tick_locked(self) -> None:
        with self.queue.engine.connect() as connection:
            rows = connection.execute(
                select(SourceCatalog.season_year, func.count(Snapshot.id))
                .outerjoin(
                    Snapshot,
                    (Snapshot.source_catalog_id == SourceCatalog.id)
                    & (Snapshot.status == "validated"),
                )
                .where(
                    SourceCatalog.provider == "oracles_elixir",
                    SourceCatalog.dataset == "league_of_legends_match_data",
                    SourceCatalog.status == "active",
                )
                .group_by(SourceCatalog.season_year)
            )
            years = {int(year): count > 1 for year, count in rows}
        for item in planned_jobs(self.policy, self.queue.clock.now().value, years):
            with self.queue.engine.connect() as connection:
                busy = connection.scalar(
                    select(JobRecord.id)
                    .where(
                        JobRecord.scope == item.scope, JobRecord.status.in_(("queued", "running"))
                    )
                    .limit(1)
                )
            if busy is None:
                self.queue.enqueue(
                    item.job_type,
                    item.payload,
                    key=item.key,
                    scope=item.scope,
                    actor="scheduler",
                    scheduled_at=item.scheduled_at,
                    max_attempts=4,
                )
