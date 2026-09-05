"""Évaluer la fraîcheur Oracle's Elixir et appliquer la politique de lecture."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import Engine, Table, select

from metiquo.config import Settings
from metiquo.contracts.enums import FreshnessStatus
from metiquo.db.raw_models import IngestionRun, Snapshot, SourceCatalog
from metiquo.foundation.time import Clock, SystemClock


@dataclass(frozen=True, slots=True)
class PublishedSnapshot:
    id: UUID
    validated_at: datetime


@dataclass(frozen=True, slots=True)
class FreshnessFacts:
    catalog_status: str | None
    current: PublishedSnapshot | None
    quarantined_at: datetime | None = None
    failed_at: datetime | None = None
    failure_code: str | None = None


class FreshnessRepository(Protocol):
    def get_facts(self, source_catalog_id: UUID) -> FreshnessFacts: ...


class PostgresFreshnessRepository:
    """Lire uniquement le pointeur validé et les incidents plus récents."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._catalog = cast(Table, SourceCatalog.__table__)
        self._snapshots = cast(Table, Snapshot.__table__)
        self._runs = cast(Table, IngestionRun.__table__)

    def get_facts(self, source_catalog_id: UUID) -> FreshnessFacts:
        with self._engine.connect() as connection:
            catalog = (
                connection.execute(
                    select(self._catalog.c.status, self._catalog.c.current_snapshot_id).where(
                        self._catalog.c.id == source_catalog_id
                    )
                )
                .mappings()
                .one_or_none()
            )
            if catalog is None:
                return FreshnessFacts(catalog_status=None, current=None)
            current_row = None
            if catalog["current_snapshot_id"] is not None:
                current_row = (
                    connection.execute(
                        select(self._snapshots.c.id, self._snapshots.c.validated_at).where(
                            self._snapshots.c.id == catalog["current_snapshot_id"],
                            self._snapshots.c.source_catalog_id == source_catalog_id,
                            self._snapshots.c.status == "validated",
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
            quarantine = connection.execute(
                select(self._snapshots.c.received_at)
                .where(
                    self._snapshots.c.source_catalog_id == source_catalog_id,
                    self._snapshots.c.status == "quarantined",
                )
                .order_by(self._snapshots.c.received_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            failure = (
                connection.execute(
                    select(self._runs.c.finished_at, self._runs.c.error_code)
                    .where(
                        self._runs.c.source_catalog_id == source_catalog_id,
                        self._runs.c.status == "failed",
                    )
                    .order_by(self._runs.c.finished_at.desc())
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
        current = (
            PublishedSnapshot(id=current_row["id"], validated_at=current_row["validated_at"])
            if current_row is not None
            else None
        )
        return FreshnessFacts(
            catalog_status=str(catalog["status"]),
            current=current,
            quarantined_at=quarantine,
            failed_at=failure["finished_at"] if failure is not None else None,
            failure_code=(
                str(failure["error_code"])
                if failure is not None and failure["error_code"] is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    allow_stale: bool = False
    require_fresh: bool = False

    def __post_init__(self) -> None:
        if self.allow_stale and self.require_fresh:
            raise ValueError("allow_stale et require_fresh sont incompatibles")

    @classmethod
    def from_settings(cls, settings: Settings) -> FreshnessPolicy:
        return cls(
            allow_stale=settings.oe_allow_stale,
            require_fresh=settings.oe_require_fresh,
        )


@dataclass(frozen=True, slots=True)
class SourceFreshnessDecision:
    status: FreshnessStatus
    usable: bool
    as_of: datetime | None
    snapshot_id: UUID | None
    age_seconds: int | None
    sla_seconds: int
    reason_code: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "usable": self.usable,
            "asOf": (
                self.as_of.isoformat().replace("+00:00", "Z") if self.as_of is not None else None
            ),
            "snapshotId": str(self.snapshot_id) if self.snapshot_id is not None else None,
            "ageSeconds": self.age_seconds,
            "slaSeconds": self.sla_seconds,
            "reasonCode": self.reason_code,
        }


class FreshDataRequired(RuntimeError):
    """La politique stricte refuse tout état autre que fresh."""

    exit_code = 3

    def __init__(self, decision: SourceFreshnessDecision) -> None:
        super().__init__(f"snapshot fresh indisponible : {decision.reason_code}")
        self.decision = decision


class FreshnessService:
    """Classifier une source et sélectionner sans ambiguïté son snapshot lisible."""

    def __init__(
        self,
        *,
        repository: FreshnessRepository,
        sla: timedelta,
        clock: Clock | None = None,
    ) -> None:
        if sla <= timedelta(0):
            raise ValueError("le SLA doit être strictement positif")
        self._repository = repository
        self._sla = sla
        self._clock = clock or SystemClock()

    @classmethod
    def from_settings(
        cls,
        *,
        repository: FreshnessRepository,
        settings: Settings,
        clock: Clock | None = None,
    ) -> FreshnessService:
        return cls(
            repository=repository,
            sla=timedelta(seconds=settings.oe_freshness_sla_seconds),
            clock=clock,
        )

    def evaluate(
        self,
        source_catalog_id: UUID,
        *,
        policy: FreshnessPolicy,
    ) -> SourceFreshnessDecision:
        facts = self._repository.get_facts(source_catalog_id)
        status, reason = self._classify(facts)
        current = facts.current
        age_seconds = self._age_seconds(current)
        usable = status is FreshnessStatus.FRESH or (
            policy.allow_stale
            and current is not None
            and status
            in {
                FreshnessStatus.STALE,
                FreshnessStatus.DEGRADED,
                FreshnessStatus.QUARANTINED,
            }
        )
        decision = SourceFreshnessDecision(
            status=status,
            usable=usable,
            as_of=current.validated_at if current is not None else None,
            snapshot_id=current.id if current is not None else None,
            age_seconds=age_seconds,
            sla_seconds=int(self._sla.total_seconds()),
            reason_code=reason,
        )
        if policy.require_fresh and status is not FreshnessStatus.FRESH:
            raise FreshDataRequired(decision)
        return decision

    def _classify(self, facts: FreshnessFacts) -> tuple[FreshnessStatus, str]:
        if facts.catalog_status is None:
            return FreshnessStatus.FAILED, "SOURCE_CATALOG_MISSING"
        current = facts.current
        as_of = current.validated_at if current is not None else None
        if facts.quarantined_at is not None and (as_of is None or facts.quarantined_at >= as_of):
            return FreshnessStatus.QUARANTINED, "NEWER_CONTENT_QUARANTINED"
        if facts.failed_at is not None and (as_of is None or facts.failed_at >= as_of):
            if current is None:
                return FreshnessStatus.FAILED, facts.failure_code or "SOURCE_SYNC_FAILED"
            return FreshnessStatus.DEGRADED, facts.failure_code or "SOURCE_SYNC_FAILED"
        if current is None:
            return FreshnessStatus.FAILED, "NO_VALIDATED_SNAPSHOT"
        if facts.catalog_status != "active":
            return FreshnessStatus.DEGRADED, f"SOURCE_CATALOG_{facts.catalog_status.upper()}"
        age_seconds = self._age_seconds(current)
        assert age_seconds is not None
        if age_seconds > int(self._sla.total_seconds()):
            return FreshnessStatus.STALE, "FRESHNESS_SLA_EXCEEDED"
        return FreshnessStatus.FRESH, "FRESHNESS_WITHIN_SLA"

    def _age_seconds(self, current: PublishedSnapshot | None) -> int | None:
        if current is None:
            return None
        age = self._clock.now().value - current.validated_at
        if age < timedelta(0):
            raise ValueError("validated_at ne peut pas être dans le futur")
        return int(age.total_seconds())
