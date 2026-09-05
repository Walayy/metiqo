"""Planifier les recalculs de features à partir des révisions source."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, Table, func, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.feature_models import FeatureInvalidation
from metiquo.db.raw_models import IngestionRun, RowRevision
from metiquo.foundation.time import Clock, SystemClock


class InvalidationPlanningError(RuntimeError):
    """La plage affectée ne peut pas être déterminée de façon sûre."""


@dataclass(frozen=True, slots=True)
class RevisionInvalidation:
    id: UUID
    source_run_id: UUID
    source_snapshot_id: UUID
    provider: str
    dataset: str
    affected_from: date
    changed_through: date
    revision_count: int
    reason: str
    created_at: datetime


class RevisionInvalidationService:
    """Émettre un marqueur idempotent sans modifier features ni prédictions existantes."""

    def __init__(self, *, engine: Engine, clock: Clock | None = None) -> None:
        self._engine = engine
        self._clock = clock or SystemClock()
        self._runs = cast(Table, IngestionRun.__table__)
        self._revisions = cast(Table, RowRevision.__table__)
        self._invalidations = cast(Table, FeatureInvalidation.__table__)

    def emit_for_run(self, run_id: UUID) -> RevisionInvalidation | None:
        created_at = self._clock.now().value
        with self._engine.begin() as connection:
            run = (
                connection.execute(
                    select(self._runs).where(self._runs.c.id == run_id).with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if run is None or run["status"] != "succeeded" or run["snapshot_id"] is None:
                raise InvalidationPlanningError("le run doit être terminé avec un snapshot")

            grouped = (
                connection.execute(
                    select(
                        self._revisions.c.snapshot_id,
                        self._revisions.c.provider,
                        self._revisions.c.dataset,
                        func.min(self._revisions.c.event_date).label("affected_from"),
                        func.max(self._revisions.c.event_date).label("changed_through"),
                        func.count().label("revision_count"),
                        func.count(self._revisions.c.event_date).label("dated_count"),
                    )
                    .where(
                        self._revisions.c.run_id == run_id,
                        self._revisions.c.operation == "updated",
                    )
                    .group_by(
                        self._revisions.c.snapshot_id,
                        self._revisions.c.provider,
                        self._revisions.c.dataset,
                    )
                )
                .mappings()
                .all()
            )
            if not grouped:
                return None
            if len(grouped) != 1:
                raise InvalidationPlanningError("un run couvre plusieurs sources incompatibles")
            source = grouped[0]
            revision_count = int(source["revision_count"])
            if int(source["dated_count"]) != revision_count:
                raise InvalidationPlanningError("une révision modifiée ne porte pas de date métier")

            event_id = uuid4()
            connection.execute(
                insert(self._invalidations)
                .values(
                    id=event_id,
                    source_run_id=run_id,
                    source_snapshot_id=source["snapshot_id"],
                    provider=source["provider"],
                    dataset=source["dataset"],
                    affected_from=source["affected_from"],
                    changed_through=source["changed_through"],
                    revision_count=revision_count,
                    reason="RAW_ROW_REVISED",
                    created_at=created_at,
                )
                .on_conflict_do_nothing(index_elements=[self._invalidations.c.source_run_id])
            )
            row = (
                connection.execute(
                    select(self._invalidations).where(self._invalidations.c.source_run_id == run_id)
                )
                .mappings()
                .one()
            )
        return RevisionInvalidation(
            id=row["id"],
            source_run_id=row["source_run_id"],
            source_snapshot_id=row["source_snapshot_id"],
            provider=str(row["provider"]),
            dataset=str(row["dataset"]),
            affected_from=row["affected_from"],
            changed_through=row["changed_through"],
            revision_count=int(row["revision_count"]),
            reason=str(row["reason"]),
            created_at=row["created_at"],
        )
