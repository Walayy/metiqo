"""Construction reproductible du dataset P3 et de ses feature snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, RowMapping, Table, or_, select

from metiquo.canonical.capabilities import CapabilityRegistry
from metiquo.db.core_models import (
    CanonicalEntityRevision,
    Competition,
    Game,
    GameTeamStat,
    Patch,
)
from metiquo.db.feature_models import FeatureSnapshot
from metiquo.db.raw_models import Snapshot as OeSnapshot
from metiquo.db.raw_models import SourceCatalog
from metiquo.features.champions import (
    ChampionMetaFeatureCalculator,
    champion_meta_feature_definitions,
)
from metiquo.features.context import (
    CompetitionContextFeatureCalculator,
    ContextField,
    TargetCompetitionContext,
    competition_context_feature_definitions,
)
from metiquo.features.economy import EconomyFeatureCalculator, economy_feature_definitions
from metiquo.features.form import RecentFormCalculator, recent_form_feature_definitions
from metiquo.features.priors import (
    HierarchicalPriorEstimator,
    PriorObservation,
    ShrunkFeatureValue,
    prior_feature_definitions,
)
from metiquo.features.rating import EloRatingCalculator, rating_feature_definitions
from metiquo.features.rebuild import (
    FeatureRebuildCandidate,
    FeatureRebuildPlanner,
)
from metiquo.features.registry import (
    FeatureRegistry,
    FeatureSetSpec,
    FeatureValue,
    RegisteredFeatureSet,
)
from metiquo.features.roster import RosterFeatureCalculator, roster_feature_definitions
from metiquo.features.side import SideFeatureCalculator, side_feature_definitions
from metiquo.features.snapshots import (
    FeatureSnapshotSpec,
    FeatureSnapshotStore,
    StoredFeatureSnapshot,
)
from metiquo.features.temporal import AsOfGameBatch, AsOfGameRepository, FeatureCutoff
from metiquo.foundation.time import normalize_utc_datetime

FULL_FEATURE_SET_NAME = "lol.match_winner.pregame"
FULL_FEATURE_SET_VERSION = "p3-reproducible-v1"
FULL_FEATURE_CODE_VERSION = "p3-feature-pipeline-v1"
_PRIOR_METRICS = ("team_a.win_rate", "team_b.win_rate")
_QUANTUM = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class TargetGameCandidate:
    game_id: UUID
    source_game_id: str
    event_time: datetime
    team_a_id: UUID
    team_b_id: UUID
    competition_id: UUID | None
    patch_id: UUID | None
    target_oe_snapshot_id: UUID
    source_revision_id: UUID
    source_processed_at: datetime
    context: TargetCompetitionContext


@dataclass(frozen=True, slots=True)
class FeatureCoverageReport:
    requested_from: date
    effective_from: date
    target_count: int
    snapshot_count: int
    created_count: int
    rebuilt_count: int
    coverage: Decimal
    cutoff_min: datetime | None
    cutoff_max: datetime | None
    missingness: Mapping[str, Decimal]
    snapshot_ids: tuple[UUID, ...]
    example_snapshot_id: UUID | None

    def to_dict(self) -> dict[str, object]:
        return {
            "coverage": str(self.coverage),
            "createdCount": self.created_count,
            "cutoffMax": self.cutoff_max.isoformat() if self.cutoff_max else None,
            "cutoffMin": self.cutoff_min.isoformat() if self.cutoff_min else None,
            "effectiveFrom": self.effective_from.isoformat(),
            "exampleSnapshotId": (
                str(self.example_snapshot_id) if self.example_snapshot_id else None
            ),
            "missingness": {key: str(value) for key, value in self.missingness.items()},
            "rebuiltCount": self.rebuilt_count,
            "requestedFrom": self.requested_from.isoformat(),
            "snapshotCount": self.snapshot_count,
            "snapshotIds": [str(value) for value in self.snapshot_ids],
            "targetCount": self.target_count,
        }


class TargetGameRepository:
    """Énumérer uniquement les games dont le contexte canonique était déjà connu."""

    def __init__(self, *, engine: Engine, provider: str, dataset: str) -> None:
        self._engine = engine
        self._provider = provider
        self._dataset = dataset

    def list_from(self, from_date: date) -> tuple[TargetGameCandidate, ...]:
        games = cast(Table, Game.__table__)
        stats = cast(Table, GameTeamStat.__table__)
        snapshots = cast(Table, OeSnapshot.__table__)
        catalogs = cast(Table, SourceCatalog.__table__)
        competitions = cast(Table, Competition.__table__)
        patches = cast(Table, Patch.__table__)
        revisions = cast(Table, CanonicalEntityRevision.__table__)
        from_instant = datetime.combine(from_date, time.min, tzinfo=UTC)
        with self._engine.connect() as connection:
            game_rows = (
                connection.execute(
                    select(games)
                    .join(snapshots, snapshots.c.id == games.c.source_snapshot_id)
                    .join(catalogs, catalogs.c.id == snapshots.c.source_catalog_id)
                    .where(
                        catalogs.c.provider == self._provider,
                        catalogs.c.dataset == self._dataset,
                        snapshots.c.status == "validated",
                        or_(
                            games.c.start_at >= from_instant,
                            games.c.event_date >= from_date,
                        ),
                    )
                    .order_by(games.c.event_date, games.c.start_at, games.c.id)
                )
                .mappings()
                .all()
            )
            game_ids = tuple(cast(UUID, row["id"]) for row in game_rows)
            team_rows = (
                connection.execute(
                    select(stats.c.game_id, stats.c.team_id).where(stats.c.game_id.in_(game_ids))
                ).all()
                if game_ids
                else ()
            )
            competition_rows = connection.execute(
                select(
                    competitions.c.id,
                    competitions.c.display_name,
                    competitions.c.normalized_name,
                )
            ).all()
            patch_rows = connection.execute(select(patches.c.id, patches.c.version)).all()
            revision_rows = (
                connection.execute(
                    select(
                        revisions.c.entity_id,
                        revisions.c.id,
                        revisions.c.revision,
                    )
                    .where(
                        revisions.c.entity_type == "game",
                        revisions.c.entity_id.in_(game_ids),
                    )
                    .order_by(revisions.c.entity_id, revisions.c.revision.desc())
                ).all()
                if game_ids
                else ()
            )
        teams_by_game: dict[UUID, set[UUID]] = {}
        for game_id, team_id in team_rows:
            teams_by_game.setdefault(cast(UUID, game_id), set()).add(cast(UUID, team_id))
        competition_names = {
            cast(UUID, competition_id): str(display_name or normalized_name)
            for competition_id, display_name, normalized_name in competition_rows
        }
        patch_versions = {cast(UUID, patch_id): str(version) for patch_id, version in patch_rows}
        revision_ids: dict[UUID, UUID] = {}
        for entity_id, revision_id, _revision in revision_rows:
            revision_ids.setdefault(cast(UUID, entity_id), cast(UUID, revision_id))
        targets: list[TargetGameCandidate] = []
        for row in game_rows:
            game_id = cast(UUID, row["id"])
            event_time = _target_event_time(row)
            processed_at = normalize_utc_datetime(cast(datetime, row["processed_at"]))
            revision_id = revision_ids.get(game_id)
            teams = tuple(sorted(teams_by_game.get(game_id, ()), key=str))
            if processed_at > event_time or revision_id is None or len(teams) != 2:
                continue
            competition_id = cast(UUID | None, row["competition_id"])
            patch_id = cast(UUID | None, row["patch_id"])
            league = competition_names.get(competition_id) if competition_id else None
            patch = patch_versions.get(patch_id) if patch_id else None
            context = _target_context(
                row,
                competition_id=competition_id,
                league=league,
                patch=patch,
                revision_id=revision_id,
                known_at=processed_at,
            )
            targets.append(
                TargetGameCandidate(
                    game_id=game_id,
                    source_game_id=str(row["source_game_id"]),
                    event_time=event_time,
                    team_a_id=teams[0],
                    team_b_id=teams[1],
                    competition_id=competition_id,
                    patch_id=patch_id,
                    target_oe_snapshot_id=cast(UUID, row["source_snapshot_id"]),
                    source_revision_id=revision_id,
                    source_processed_at=processed_at,
                    context=context,
                )
            )
        return tuple(sorted(targets, key=lambda item: (item.event_time, item.game_id)))


class FeatureDatasetBuilder:
    """Calculer, enregistrer et reconstruire le feature set P3 fermé."""

    def __init__(
        self,
        *,
        engine: Engine,
        code_commit: str,
        provider: str = "oracles_elixir",
        dataset: str = "league_of_legends_match_data",
    ) -> None:
        self._engine = engine
        self._code_commit = code_commit
        self._provider = provider
        self._dataset = dataset
        self._registry = FeatureRegistry(engine=engine)
        self._store = FeatureSnapshotStore(engine=engine)
        self._targets = TargetGameRepository(
            engine=engine,
            provider=provider,
            dataset=dataset,
        )

    def rebuild_from(self, from_date: date) -> FeatureCoverageReport:
        feature_set = self.ensure_feature_set()
        planner = FeatureRebuildPlanner(engine=self._engine)
        plan = planner.plan(
            from_date=from_date,
            provider=self._provider,
            dataset=self._dataset,
            feature_set_id=feature_set.feature_set_id,
        )
        if not plan.invalidations:
            plan = replace(plan, candidates=())
        targets = self._targets.list_from(plan.effective_from)
        targets_by_id = {target.game_id: target for target in targets}

        def recalculate(candidate: FeatureRebuildCandidate) -> FeatureSnapshotSpec:
            target = targets_by_id.get(candidate.snapshot.event_id)
            if target is None:
                raise ValueError("candidate canonique introuvable pour le rebuild")
            return self._specification(
                target,
                feature_set,
                team_a_id=candidate.snapshot.team_a_id,
                team_b_id=candidate.snapshot.team_b_id,
                supersedes_snapshot_id=candidate.snapshot.snapshot_id,
                invalidation_ids=frozenset(
                    item.invalidation_id for item in candidate.invalidations
                ),
            )

        rebuilt = planner.execute(plan, recalculate=recalculate)
        created: list[StoredFeatureSnapshot] = []
        for target in targets:
            if self._latest_snapshot(target.game_id, feature_set.feature_set_id) is not None:
                continue
            created.append(self._store.create(self._specification(target, feature_set)))
        current = tuple(
            snapshot
            for target in targets
            if (snapshot := self._latest_snapshot(target.game_id, feature_set.feature_set_id))
            is not None
        )
        return _coverage_report(
            requested_from=from_date,
            effective_from=plan.effective_from,
            targets=targets,
            snapshots=current,
            created_count=len(created),
            rebuilt_count=len(rebuilt.replacements),
        )

    def ensure_feature_set(self) -> RegisteredFeatureSet:
        definitions = (
            *rating_feature_definitions(),
            *recent_form_feature_definitions(),
            *side_feature_definitions(),
            *economy_feature_definitions(),
            *roster_feature_definitions(),
            *champion_meta_feature_definitions(),
            *competition_context_feature_definitions(),
            *prior_feature_definitions(_PRIOR_METRICS),
        )
        return self._registry.register_set(
            FeatureSetSpec(
                name=FULL_FEATURE_SET_NAME,
                set_version=FULL_FEATURE_SET_VERSION,
                code_version=FULL_FEATURE_CODE_VERSION,
                definitions=definitions,
            )
        )

    def _specification(
        self,
        target: TargetGameCandidate,
        feature_set: RegisteredFeatureSet,
        *,
        team_a_id: UUID | None = None,
        team_b_id: UUID | None = None,
        supersedes_snapshot_id: UUID | None = None,
        invalidation_ids: frozenset[UUID] = frozenset(),
    ) -> FeatureSnapshotSpec:
        resolved_a = team_a_id or target.team_a_id
        resolved_b = team_b_id or target.team_b_id
        cutoff = FeatureCutoff(target.event_time)
        batch = AsOfGameRepository(self._engine).list_before(
            cutoff=cutoff,
            team_ids=frozenset({resolved_a, resolved_b}),
        )
        capabilities = {
            state.capability: state.status
            for state in CapabilityRegistry(engine=self._engine).list_latest(
                snapshot_id=target.target_oe_snapshot_id
            )
        }
        values: dict[str, FeatureValue] = {}
        rating = EloRatingCalculator().calculate(
            batch,
            team_a_id=resolved_a,
            team_b_id=resolved_b,
            target_competition_id=target.competition_id,
        )
        form = RecentFormCalculator().calculate(
            batch,
            team_a_id=resolved_a,
            team_b_id=resolved_b,
        )
        results = (
            rating,
            form,
            SideFeatureCalculator().calculate(
                batch,
                team_a_id=resolved_a,
                team_b_id=resolved_b,
                target_side_a="unknown",
            ),
            EconomyFeatureCalculator().calculate(
                batch,
                team_a_id=resolved_a,
                team_b_id=resolved_b,
                capabilities=capabilities,
            ),
            RosterFeatureCalculator().calculate(
                batch,
                team_a_id=resolved_a,
                team_b_id=resolved_b,
            ),
            ChampionMetaFeatureCalculator().calculate(
                batch,
                team_a_id=resolved_a,
                team_b_id=resolved_b,
                target_patch_id=target.patch_id,
                target_game_id=target.game_id,
            ),
            CompetitionContextFeatureCalculator().calculate(
                batch,
                team_a_id=resolved_a,
                team_b_id=resolved_b,
                target=target.context,
            ),
        )
        for result in results:
            _merge_values(values, result.values)
        prior_estimator = HierarchicalPriorEstimator()
        prior_model = prior_estimator.fit(_prior_observations(batch), cutoff=cutoff)
        for label, team_id, team_form in (
            ("team_a", resolved_a, form.team_a),
            ("team_b", resolved_b, form.team_b),
        ):
            window = team_form.game_windows[max(team_form.game_windows)]
            shrunk = prior_estimator.shrink(
                prior_model,
                value=window.win_rate,
                sample_size=window.usable_games,
                league=str(target.competition_id) if target.competition_id else None,
                patch=str(target.patch_id) if target.patch_id else None,
                last_observed_at=_last_team_game(batch, team_id),
                prediction_cutoff=cutoff,
            )
            _merge_values(values, _prior_values(label, shrunk))
        vector = self._registry.build_vector(
            feature_set_name=feature_set.name,
            feature_set_version=feature_set.set_version,
            values=values,
        )
        return FeatureSnapshotSpec(
            event_id=target.game_id,
            team_a_id=resolved_a,
            team_b_id=resolved_b,
            target_oe_snapshot_id=target.target_oe_snapshot_id,
            cutoff=cutoff,
            vector=vector,
            source_batch=batch,
            target_game_ids=frozenset({target.game_id}),
            code_commit=self._code_commit,
            leakage_checks={"train_only_transforms": True},
            supersedes_snapshot_id=supersedes_snapshot_id,
            rebuild_invalidation_ids=invalidation_ids,
        )

    def _latest_snapshot(
        self,
        event_id: UUID,
        feature_set_id: UUID,
    ) -> StoredFeatureSnapshot | None:
        table = cast(Table, FeatureSnapshot.__table__)
        with self._engine.connect() as connection:
            snapshot_id = connection.execute(
                select(table.c.id)
                .where(
                    table.c.event_id == event_id,
                    table.c.feature_set_id == feature_set_id,
                )
                .order_by(table.c.generation.desc(), table.c.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        return self._store.get(cast(UUID, snapshot_id)) if snapshot_id is not None else None


def _target_event_time(row: RowMapping) -> datetime:
    start_at = row["start_at"]
    if isinstance(start_at, datetime):
        return normalize_utc_datetime(start_at)
    event_date = cast(date | None, row["event_date"])
    if event_date is None:
        raise ValueError("une game cible exige une date")
    return datetime.combine(event_date, time.min, tzinfo=UTC)


def _target_context(
    row: RowMapping,
    *,
    competition_id: UUID | None,
    league: str | None,
    patch: str | None,
    revision_id: UUID,
    known_at: datetime,
) -> TargetCompetitionContext:
    def known(value: str | int | bool | UUID | None) -> ContextField:
        return (
            ContextField.oe(value, source_revision_id=revision_id, known_at=known_at)
            if value is not None
            else ContextField()
        )

    normalized_league = (league or "").casefold()
    international = (
        True
        if any(token in normalized_league for token in ("world", "international", "msi"))
        else None
    )
    playoffs: bool | None = None
    if any(token in normalized_league for token in ("playoff", "knockout")):
        playoffs = True
    elif "regular" in normalized_league:
        playoffs = False
    return TargetCompetitionContext(
        competition=known(competition_id),
        league=known(league),
        playoffs=known(playoffs),
        international=known(international),
        best_of=known(cast(int | None, row["best_of"])),
        patch=known(patch),
    )


def _prior_observations(batch: AsOfGameBatch) -> tuple[PriorObservation, ...]:
    return tuple(
        PriorObservation(
            observation_id=stat.team_stat_id,
            event_time=game.event_time,
            known_at=stat.source_processed_at,
            league=str(game.competition_id) if game.competition_id else None,
            patch=str(game.patch_id) if game.patch_id else None,
            value=Decimal(int(stat.result)) if stat.result is not None else None,
            sample_size=1,
        )
        for game in batch.games
        if game.usable_for_training
        for stat in game.team_stats
    )


def _last_team_game(batch: AsOfGameBatch, team_id: UUID) -> datetime | None:
    return max(
        (
            game.event_time
            for game in batch.games
            if any(stat.team_id == team_id for stat in game.team_stats)
        ),
        default=None,
    )


def _prior_values(label: str, value: ShrunkFeatureValue) -> Mapping[str, FeatureValue]:
    base = f"prior.{label}.win_rate"
    return MappingProxyType(
        {
            f"{base}.available": value.raw_available,
            f"{base}.cold_start": value.cold_start,
            f"{base}.confidence": value.confidence,
            f"{base}.effective_sample": value.effective_sample_size,
            f"{base}.level": value.prior_level,
            f"{base}.ood": value.ood,
            f"{base}.value": value.value,
        }
    )


def _merge_values(target: dict[str, FeatureValue], source: Mapping[str, FeatureValue]) -> None:
    duplicate = set(target) & set(source)
    if duplicate:
        raise ValueError(f"features calculées deux fois: {sorted(duplicate)}")
    target.update(source)


def _coverage_report(
    *,
    requested_from: date,
    effective_from: date,
    targets: Sequence[TargetGameCandidate],
    snapshots: Sequence[StoredFeatureSnapshot],
    created_count: int,
    rebuilt_count: int,
) -> FeatureCoverageReport:
    snapshot_count = len(snapshots)
    coverage = (
        _quantize(Decimal(snapshot_count) / Decimal(len(targets)))
        if targets
        else Decimal().quantize(_QUANTUM)
    )
    feature_names = sorted({name for snapshot in snapshots for name in snapshot.missingness})
    missingness = (
        {
            name: _quantize(
                Decimal(sum(1 for snapshot in snapshots if snapshot.missingness.get(name, True)))
                / Decimal(snapshot_count)
            )
            for name in feature_names
        }
        if snapshot_count
        else {}
    )
    ordered = tuple(sorted(snapshots, key=lambda item: (item.cutoff_at, item.snapshot_id)))
    return FeatureCoverageReport(
        requested_from=requested_from,
        effective_from=effective_from,
        target_count=len(targets),
        snapshot_count=snapshot_count,
        created_count=created_count,
        rebuilt_count=rebuilt_count,
        coverage=coverage,
        cutoff_min=ordered[0].cutoff_at if ordered else None,
        cutoff_max=ordered[-1].cutoff_at if ordered else None,
        missingness=MappingProxyType(missingness),
        snapshot_ids=tuple(snapshot.snapshot_id for snapshot in ordered),
        example_snapshot_id=ordered[0].snapshot_id if ordered else None,
    )


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
