"""Planification et exécution ciblée des rebuilds de feature snapshots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, Table, select

from metiquo.db.feature_models import FeatureInvalidation, FeatureSnapshot
from metiquo.db.raw_models import Snapshot as OeSnapshot
from metiquo.db.raw_models import SourceCatalog
from metiquo.features.snapshots import (
    FeatureSnapshotSpec,
    FeatureSnapshotStore,
    StoredFeatureSnapshot,
)


@dataclass(frozen=True, slots=True)
class PlannedInvalidation:
    invalidation_id: UUID
    source_run_id: UUID
    source_snapshot_id: UUID
    affected_from: date
    changed_through: date
    revision_count: int


@dataclass(frozen=True, slots=True)
class FeatureRebuildCandidate:
    snapshot: StoredFeatureSnapshot
    invalidations: tuple[PlannedInvalidation, ...]


@dataclass(frozen=True, slots=True)
class FeatureRebuildPlan:
    requested_from: date
    effective_from: date
    provider: str
    dataset: str
    invalidations: tuple[PlannedInvalidation, ...]
    candidates: tuple[FeatureRebuildCandidate, ...]


@dataclass(frozen=True, slots=True)
class FeatureSnapshotReplacement:
    previous_snapshot_id: UUID
    new_snapshot_id: UUID
    generation: int
    invalidation_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class FeatureRebuildResult:
    plan: FeatureRebuildPlan
    replacements: tuple[FeatureSnapshotReplacement, ...]


type SnapshotRecalculator = Callable[[FeatureRebuildCandidate], FeatureSnapshotSpec]


class FeatureRebuildPlanner:
    """Choisir la plage minimale et seulement la dernière génération de chaque candidate."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def plan(
        self,
        *,
        from_date: date,
        provider: str,
        dataset: str,
    ) -> FeatureRebuildPlan:
        invalidations = self._invalidations(
            from_date=from_date,
            provider=provider,
            dataset=dataset,
        )
        effective_from = min(
            (item.affected_from for item in invalidations),
            default=from_date,
        )
        latest = self._latest_snapshots(
            from_date=effective_from,
            provider=provider,
            dataset=dataset,
        )
        candidates: list[FeatureRebuildCandidate] = []
        for snapshot in latest:
            pending = tuple(
                item
                for item in invalidations
                if item.invalidation_id not in snapshot.rebuild_invalidation_ids
                and snapshot.cutoff_at.date() >= item.affected_from
            )
            if invalidations and not pending:
                continue
            candidates.append(FeatureRebuildCandidate(snapshot, pending))
        return FeatureRebuildPlan(
            requested_from=from_date,
            effective_from=effective_from,
            provider=provider,
            dataset=dataset,
            invalidations=invalidations,
            candidates=tuple(candidates),
        )

    def execute(
        self,
        plan: FeatureRebuildPlan,
        *,
        recalculate: SnapshotRecalculator,
    ) -> FeatureRebuildResult:
        store = FeatureSnapshotStore(engine=self._engine)
        replacements: list[FeatureSnapshotReplacement] = []
        for candidate in plan.candidates:
            specification = recalculate(candidate)
            expected_invalidations = frozenset(
                item.invalidation_id for item in candidate.invalidations
            )
            if specification.supersedes_snapshot_id != candidate.snapshot.snapshot_id:
                raise ValueError("le recalcul doit superséder exactement son snapshot candidat")
            if not expected_invalidations <= specification.rebuild_invalidation_ids:
                raise ValueError("le recalcul doit enregistrer toutes ses invalidations")
            created = store.create(specification)
            replacements.append(
                FeatureSnapshotReplacement(
                    previous_snapshot_id=candidate.snapshot.snapshot_id,
                    new_snapshot_id=created.snapshot_id,
                    generation=created.generation,
                    invalidation_ids=tuple(sorted(expected_invalidations, key=str)),
                )
            )
        return FeatureRebuildResult(plan, tuple(replacements))

    def _invalidations(
        self,
        *,
        from_date: date,
        provider: str,
        dataset: str,
    ) -> tuple[PlannedInvalidation, ...]:
        table = cast(Table, FeatureInvalidation.__table__)
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(table)
                    .where(
                        table.c.provider == provider,
                        table.c.dataset == dataset,
                        table.c.changed_through >= from_date,
                    )
                    .order_by(table.c.affected_from, table.c.id)
                )
                .mappings()
                .all()
            )
        return tuple(
            PlannedInvalidation(
                invalidation_id=cast(UUID, row["id"]),
                source_run_id=cast(UUID, row["source_run_id"]),
                source_snapshot_id=cast(UUID, row["source_snapshot_id"]),
                affected_from=cast(date, row["affected_from"]),
                changed_through=cast(date, row["changed_through"]),
                revision_count=int(row["revision_count"]),
            )
            for row in rows
        )

    def _latest_snapshots(
        self,
        *,
        from_date: date,
        provider: str,
        dataset: str,
    ) -> tuple[StoredFeatureSnapshot, ...]:
        features = cast(Table, FeatureSnapshot.__table__)
        snapshots = cast(Table, OeSnapshot.__table__)
        catalog = cast(Table, SourceCatalog.__table__)
        from_instant = datetime.combine(from_date, time.min, tzinfo=UTC)
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(features.c.id)
                .join(snapshots, snapshots.c.id == features.c.target_oe_snapshot_id)
                .join(catalog, catalog.c.id == snapshots.c.source_catalog_id)
                .where(
                    features.c.cutoff_at >= from_instant,
                    catalog.c.provider == provider,
                    catalog.c.dataset == dataset,
                )
                .order_by(
                    features.c.cutoff_at,
                    features.c.event_id,
                    features.c.generation.desc(),
                    features.c.created_at.desc(),
                )
            ).scalars()
            ids = tuple(cast(UUID, value) for value in rows)
        store = FeatureSnapshotStore(engine=self._engine)
        latest: dict[tuple[object, ...], StoredFeatureSnapshot] = {}
        for snapshot_id in ids:
            snapshot = store.get(snapshot_id)
            if snapshot is None:
                continue
            key = (
                snapshot.event_id,
                snapshot.team_a_id,
                snapshot.team_b_id,
                snapshot.cutoff_at,
                snapshot.feature_set_id,
            )
            latest.setdefault(key, snapshot)
        return tuple(
            sorted(
                latest.values(),
                key=lambda item: (item.cutoff_at, item.event_id, item.snapshot_id),
            )
        )
