"""Construction et persistance des datasets d'entraînement game winner."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from types import MappingProxyType
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.core_models import CanonicalEntityRevision, Game, GameTeamStat
from metiquo.db.feature_models import FeatureSnapshot
from metiquo.db.ml_models import TrainingDataset, TrainingDatasetExample
from metiquo.db.raw_models import Snapshot as OeSnapshot
from metiquo.db.raw_models import SourceCatalog
from metiquo.features import FULL_FEATURE_SET_NAME, FULL_FEATURE_SET_VERSION, FeatureRegistry
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime

GAME_WINNER_MARKET = "game_winner"
GAME_WINNER_LABEL = "oe.game_team_stats.result:team_a_win@v1"
GAME_WINNER_DATASET_VERSION = "game-winner-dataset-v1"
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_FORBIDDEN_FEATURE_TOKENS = frozenset({"bookmaker", "market_odds", "odds"})
_QUALITY_FILTER = MappingProxyType(
    {
        "binary_result": True,
        "complete": True,
        "feature_leakage_checks": "all_passed",
        "forfeit": False,
        "label_snapshot_status": "validated",
        "remake": False,
        "usable_for_training": True,
        "version": "game-winner-quality-v1",
    }
)


class EmptyTrainingDatasetError(ValueError):
    """Aucune game ne satisfait les preuves minimales du dataset."""


@dataclass(frozen=True, slots=True)
class GameWinnerDatasetRequest:
    """Périmètre temporel et canonique explicite d'un dataset."""

    period_start: datetime
    period_end: datetime
    competition_ids: frozenset[UUID] = frozenset()
    feature_set_name: str = FULL_FEATURE_SET_NAME
    feature_set_version: str = FULL_FEATURE_SET_VERSION

    def __post_init__(self) -> None:
        start = normalize_utc_datetime(self.period_start)
        end = normalize_utc_datetime(self.period_end)
        if end <= start:
            raise ValueError("la fin de période doit suivre son début")
        if not self.feature_set_name.strip() or not self.feature_set_version.strip():
            raise ValueError("le feature set et sa version sont requis")
        object.__setattr__(self, "period_start", start)
        object.__setattr__(self, "period_end", end)


@dataclass(frozen=True, slots=True)
class StoredTrainingExample:
    position: int
    event_id: UUID
    feature_snapshot_id: UUID
    team_a_id: UUID
    team_b_id: UUID
    competition_id: UUID | None
    cutoff_at: datetime
    label_team_a_win: bool
    label_source_revision_id: UUID
    label_source_snapshot_id: UUID


@dataclass(frozen=True, slots=True)
class StoredTrainingDataset:
    dataset_id: UUID
    market: str
    provider: str
    dataset: str
    dataset_version: str
    feature_set_id: UUID
    feature_set_version: str
    feature_set_hash: str
    label_definition: str
    quality_filter: Mapping[str, object]
    period_start: datetime
    period_end: datetime
    cutoff_min: datetime
    cutoff_max: datetime
    competition_ids: tuple[UUID, ...]
    oe_snapshot_ids: tuple[UUID, ...]
    exclusions: tuple[Mapping[str, str], ...]
    example_count: int
    exclusion_count: int
    examples_fingerprint: str
    dataset_hash: str
    code_commit: str
    created_at: datetime
    examples: tuple[StoredTrainingExample, ...]


@dataclass(frozen=True, slots=True)
class _ExampleSpec:
    event_id: UUID
    feature_snapshot_id: UUID
    feature_snapshot_hash: str
    vector_hash: str
    team_a_id: UUID
    team_b_id: UUID
    competition_id: UUID | None
    cutoff_at: datetime
    label_team_a_win: bool
    label_source_revision_id: UUID
    label_source_snapshot_id: UUID
    oe_snapshot_ids: tuple[UUID, ...]

    def document(self, position: int) -> dict[str, object]:
        return {
            "competition_id": str(self.competition_id) if self.competition_id else None,
            "cutoff_at": self.cutoff_at.isoformat(),
            "event_id": str(self.event_id),
            "feature_snapshot_hash": self.feature_snapshot_hash,
            "feature_snapshot_id": str(self.feature_snapshot_id),
            "label_source_revision_id": str(self.label_source_revision_id),
            "label_source_snapshot_id": str(self.label_source_snapshot_id),
            "label_team_a_win": self.label_team_a_win,
            "oe_snapshot_ids": [str(value) for value in self.oe_snapshot_ids],
            "position": position,
            "team_a_id": str(self.team_a_id),
            "team_b_id": str(self.team_b_id),
            "vector_hash": self.vector_hash,
        }


@dataclass(frozen=True, slots=True)
class _StatEvidence:
    stat_id: UUID
    team_id: UUID
    result: bool | None
    source_snapshot_id: UUID


class GameWinnerDatasetBuilder:
    """Versionner les labels OE et les feature snapshots exacts utilisés au train."""

    def __init__(
        self,
        *,
        engine: Engine,
        code_commit: str,
        provider: str = "oracles_elixir",
        dataset: str = "league_of_legends_match_data",
        clock: Clock | None = None,
    ) -> None:
        if _COMMIT.fullmatch(code_commit) is None:
            raise ValueError("code_commit doit être un hash git hexadécimal")
        if not provider.strip() or not dataset.strip():
            raise ValueError("provider et dataset sont requis")
        self._engine = engine
        self._code_commit = code_commit
        self._provider = provider
        self._dataset = dataset
        self._clock = clock or SystemClock()

    def build(self, request: GameWinnerDatasetRequest) -> StoredTrainingDataset:
        feature_set = FeatureRegistry(engine=self._engine).get_set(
            request.feature_set_name,
            request.feature_set_version,
        )
        if feature_set is None:
            key = f"{request.feature_set_name}@{request.feature_set_version}"
            raise ValueError(f"feature set introuvable: {key}")
        forbidden = sorted(
            definition.name
            for definition in feature_set.definitions
            if definition.domain.casefold() in _FORBIDDEN_FEATURE_TOKENS
            or any(token in definition.name.casefold() for token in _FORBIDDEN_FEATURE_TOKENS)
        )
        if forbidden:
            raise ValueError(f"features de cote interdites dans le modèle indépendant: {forbidden}")

        examples, exclusions = self._examples(request, feature_set.feature_set_id)
        if not examples:
            raise EmptyTrainingDatasetError("aucun exemple game_winner éligible")
        example_documents = [
            example.document(position) for position, example in enumerate(examples)
        ]
        examples_fingerprint = _content_hash(example_documents)
        oe_snapshot_ids = tuple(
            sorted({value for example in examples for value in example.oe_snapshot_ids}, key=str)
        )
        competition_ids = tuple(
            sorted(
                {
                    example.competition_id
                    for example in examples
                    if example.competition_id is not None
                },
                key=str,
            )
        )
        exclusion_documents = [dict(item) for item in exclusions]
        manifest = {
            "code_commit": self._code_commit,
            "competition_ids": [str(value) for value in competition_ids],
            "dataset": self._dataset,
            "dataset_version": GAME_WINNER_DATASET_VERSION,
            "examples": example_documents,
            "examples_fingerprint": examples_fingerprint,
            "exclusions": exclusion_documents,
            "feature_set": {
                "hash": feature_set.set_hash,
                "id": str(feature_set.feature_set_id),
                "name": feature_set.name,
                "version": feature_set.set_version,
            },
            "label_definition": GAME_WINNER_LABEL,
            "market": GAME_WINNER_MARKET,
            "oe_snapshot_ids": [str(value) for value in oe_snapshot_ids],
            "period_end": request.period_end.isoformat(),
            "period_start": request.period_start.isoformat(),
            "provider": self._provider,
            "quality_filter": dict(_QUALITY_FILTER),
            "requested_competition_ids": [
                str(value) for value in sorted(request.competition_ids, key=str)
            ],
        }
        dataset_hash = _content_hash(manifest)
        dataset_id = uuid5(NAMESPACE_URL, f"metiquo:training-dataset:{dataset_hash}")
        return self._persist(
            dataset_id=dataset_id,
            dataset_hash=dataset_hash,
            feature_set_id=feature_set.feature_set_id,
            feature_set_version=feature_set.set_version,
            feature_set_hash=feature_set.set_hash,
            request=request,
            examples=examples,
            exclusions=exclusions,
            examples_fingerprint=examples_fingerprint,
            oe_snapshot_ids=oe_snapshot_ids,
            competition_ids=competition_ids,
        )

    def get(self, dataset_id: UUID) -> StoredTrainingDataset | None:
        datasets = cast(Table, TrainingDataset.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(datasets).where(datasets.c.id == dataset_id))
                .mappings()
                .one_or_none()
            )
            return None if row is None else _stored_dataset(connection, row)

    def _examples(
        self,
        request: GameWinnerDatasetRequest,
        feature_set_id: UUID,
    ) -> tuple[tuple[_ExampleSpec, ...], tuple[Mapping[str, str], ...]]:
        games = cast(Table, Game.__table__)
        team_stats = cast(Table, GameTeamStat.__table__)
        feature_snapshots = cast(Table, FeatureSnapshot.__table__)
        revisions = cast(Table, CanonicalEntityRevision.__table__)
        snapshots = cast(Table, OeSnapshot.__table__)
        catalogs = cast(Table, SourceCatalog.__table__)
        with self._engine.connect() as connection:
            game_rows = (
                connection.execute(
                    select(games, snapshots.c.status.label("game_snapshot_status"))
                    .join(snapshots, snapshots.c.id == games.c.source_snapshot_id)
                    .join(catalogs, catalogs.c.id == snapshots.c.source_catalog_id)
                    .where(
                        catalogs.c.provider == self._provider,
                        catalogs.c.dataset == self._dataset,
                    )
                )
                .mappings()
                .all()
            )
            selected_games = tuple(row for row in game_rows if _within_request(row, request))
            game_ids = tuple(cast(UUID, row["id"]) for row in selected_games)
            snapshot_rows = (
                connection.execute(
                    select(feature_snapshots)
                    .where(
                        feature_snapshots.c.feature_set_id == feature_set_id,
                        feature_snapshots.c.event_id.in_(game_ids),
                    )
                    .order_by(
                        feature_snapshots.c.event_id,
                        feature_snapshots.c.generation.desc(),
                        feature_snapshots.c.created_at.desc(),
                    )
                )
                .mappings()
                .all()
                if game_ids
                else ()
            )
            stat_rows = (
                connection.execute(
                    select(
                        team_stats.c.id,
                        team_stats.c.game_id,
                        team_stats.c.team_id,
                        team_stats.c.result,
                        team_stats.c.source_snapshot_id,
                    ).where(team_stats.c.game_id.in_(game_ids))
                ).all()
                if game_ids
                else ()
            )
            stat_ids = tuple(cast(UUID, row.id) for row in stat_rows)
            revision_rows = (
                connection.execute(
                    select(
                        revisions.c.entity_id,
                        revisions.c.id,
                        revisions.c.revision,
                        revisions.c.source_snapshot_id,
                    )
                    .where(
                        revisions.c.entity_type == "game_team_stat",
                        revisions.c.entity_id.in_(stat_ids),
                    )
                    .order_by(revisions.c.entity_id, revisions.c.revision.desc())
                ).all()
                if stat_ids
                else ()
            )
            all_source_snapshot_ids = {
                UUID(value)
                for row in snapshot_rows
                for value in cast(Sequence[str], row["source_snapshot_ids"])
            }
            all_source_snapshot_ids.update(cast(UUID, row.source_snapshot_id) for row in stat_rows)
            source_status_rows = (
                connection.execute(
                    select(
                        snapshots.c.id,
                        snapshots.c.status,
                        catalogs.c.provider,
                        catalogs.c.dataset,
                    )
                    .join(catalogs, catalogs.c.id == snapshots.c.source_catalog_id)
                    .where(snapshots.c.id.in_(tuple(all_source_snapshot_ids)))
                ).all()
                if all_source_snapshot_ids
                else ()
            )

        latest_snapshots: dict[UUID, RowMapping] = {}
        for row in snapshot_rows:
            latest_snapshots.setdefault(cast(UUID, row["event_id"]), row)
        stats_by_game: dict[UUID, list[_StatEvidence]] = {}
        for stat_id, game_id, team_id, result, source_snapshot_id in stat_rows:
            stats_by_game.setdefault(cast(UUID, game_id), []).append(
                _StatEvidence(
                    stat_id=cast(UUID, stat_id),
                    team_id=cast(UUID, team_id),
                    result=cast(bool | None, result),
                    source_snapshot_id=cast(UUID, source_snapshot_id),
                )
            )
        latest_revisions: dict[UUID, tuple[UUID, UUID]] = {}
        for stat_id, revision_id, _revision, source_snapshot_id in revision_rows:
            latest_revisions.setdefault(
                cast(UUID, stat_id),
                (cast(UUID, revision_id), cast(UUID, source_snapshot_id)),
            )
        source_provenance = {
            cast(UUID, snapshot_id): (str(status), str(provider), str(dataset))
            for snapshot_id, status, provider, dataset in source_status_rows
        }

        examples: list[_ExampleSpec] = []
        exclusions: list[Mapping[str, str]] = []
        for game_row in sorted(selected_games, key=_game_sort_key):
            event_id = cast(UUID, game_row["id"])
            reason, example = _eligible_example(
                game_row=game_row,
                feature_snapshot=latest_snapshots.get(event_id),
                stats=stats_by_game.get(event_id, []),
                latest_revisions=latest_revisions,
                source_provenance=source_provenance,
                provider=self._provider,
                dataset=self._dataset,
            )
            if reason is not None:
                exclusions.append(MappingProxyType({"event_id": str(event_id), "reason": reason}))
            elif example is not None:
                examples.append(example)
        return tuple(examples), tuple(exclusions)

    def _persist(
        self,
        *,
        dataset_id: UUID,
        dataset_hash: str,
        feature_set_id: UUID,
        feature_set_version: str,
        feature_set_hash: str,
        request: GameWinnerDatasetRequest,
        examples: Sequence[_ExampleSpec],
        exclusions: Sequence[Mapping[str, str]],
        examples_fingerprint: str,
        oe_snapshot_ids: Sequence[UUID],
        competition_ids: Sequence[UUID],
    ) -> StoredTrainingDataset:
        datasets = cast(Table, TrainingDataset.__table__)
        example_rows = cast(Table, TrainingDatasetExample.__table__)
        created_at = self._clock.now().value
        with self._engine.begin() as connection:
            existing = (
                connection.execute(select(datasets).where(datasets.c.dataset_hash == dataset_hash))
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return _stored_dataset(connection, existing)
            connection.execute(
                insert(datasets).values(
                    id=dataset_id,
                    market=GAME_WINNER_MARKET,
                    provider=self._provider,
                    dataset=self._dataset,
                    dataset_version=GAME_WINNER_DATASET_VERSION,
                    feature_set_id=feature_set_id,
                    feature_set_version=feature_set_version,
                    feature_set_hash=feature_set_hash,
                    label_definition=GAME_WINNER_LABEL,
                    quality_filter=dict(_QUALITY_FILTER),
                    period_start=request.period_start,
                    period_end=request.period_end,
                    cutoff_min=min(example.cutoff_at for example in examples),
                    cutoff_max=max(example.cutoff_at for example in examples),
                    competition_ids=[str(value) for value in competition_ids],
                    oe_snapshot_ids=[str(value) for value in oe_snapshot_ids],
                    exclusions=[dict(item) for item in exclusions],
                    example_count=len(examples),
                    exclusion_count=len(exclusions),
                    examples_fingerprint=examples_fingerprint,
                    dataset_hash=dataset_hash,
                    code_commit=self._code_commit,
                    created_at=created_at,
                )
            )
            connection.execute(
                insert(example_rows),
                [
                    {
                        "competition_id": example.competition_id,
                        "cutoff_at": example.cutoff_at,
                        "dataset_id": dataset_id,
                        "event_id": example.event_id,
                        "feature_snapshot_id": example.feature_snapshot_id,
                        "label_source_revision_id": example.label_source_revision_id,
                        "label_source_snapshot_id": example.label_source_snapshot_id,
                        "label_team_a_win": example.label_team_a_win,
                        "position": position,
                        "team_a_id": example.team_a_id,
                        "team_b_id": example.team_b_id,
                    }
                    for position, example in enumerate(examples)
                ],
            )
            row = (
                connection.execute(select(datasets).where(datasets.c.id == dataset_id))
                .mappings()
                .one()
            )
            return _stored_dataset(connection, row)


def _within_request(row: RowMapping, request: GameWinnerDatasetRequest) -> bool:
    event_time = _event_time(row)
    competition_id = cast(UUID | None, row["competition_id"])
    return request.period_start <= event_time < request.period_end and (
        not request.competition_ids or competition_id in request.competition_ids
    )


def _game_sort_key(row: RowMapping) -> tuple[datetime, str]:
    return _event_time(row), str(row["id"])


def _event_time(row: RowMapping) -> datetime:
    start_at = row["start_at"]
    if isinstance(start_at, datetime):
        return normalize_utc_datetime(start_at)
    event_date = cast(date | None, row["event_date"])
    if event_date is None:
        raise ValueError("une game d'entraînement exige une date")
    return datetime.combine(event_date, time.min, tzinfo=UTC)


def _eligible_example(
    *,
    game_row: RowMapping,
    feature_snapshot: RowMapping | None,
    stats: Sequence[_StatEvidence],
    latest_revisions: Mapping[UUID, tuple[UUID, UUID]],
    source_provenance: Mapping[UUID, tuple[str, str, str]],
    provider: str,
    dataset: str,
) -> tuple[str | None, _ExampleSpec | None]:
    if (
        not bool(game_row["usable_for_training"])
        or not bool(game_row["complete"])
        or bool(game_row["remake"])
        or bool(game_row["forfeit"])
        or str(game_row["quality_status"]) != "complete"
    ):
        return "quality_filter", None
    if feature_snapshot is None:
        return "missing_feature_snapshot", None
    if str(game_row["game_snapshot_status"]) != "validated":
        return "canonical_game_snapshot_not_validated", None
    event_id = cast(UUID, game_row["id"])
    event_time = _event_time(game_row)
    cutoff_at = normalize_utc_datetime(cast(datetime, feature_snapshot["cutoff_at"]))
    if cutoff_at > event_time or event_id not in {
        UUID(value) for value in cast(Sequence[str], feature_snapshot["target_game_ids"])
    }:
        return "invalid_feature_cutoff", None
    checks = cast(Mapping[str, bool], feature_snapshot["leakage_checks"])
    if not checks or any(value is not True for value in checks.values()):
        return "feature_leakage_check", None
    source_snapshot_ids = tuple(
        sorted(
            {UUID(value) for value in cast(Sequence[str], feature_snapshot["source_snapshot_ids"])},
            key=str,
        )
    )
    if any(
        source_provenance.get(snapshot_id) != ("validated", provider, dataset)
        for snapshot_id in source_snapshot_ids
    ):
        return "feature_snapshot_source_not_validated", None
    if len(stats) != 2 or {stat.result for stat in stats} != {False, True}:
        return "label_not_binary", None
    team_a_id = cast(UUID, feature_snapshot["team_a_id"])
    team_b_id = cast(UUID, feature_snapshot["team_b_id"])
    stats_by_team = {stat.team_id: stat for stat in stats}
    if set(stats_by_team) != {team_a_id, team_b_id}:
        return "label_teams_mismatch", None
    if any(
        source_provenance.get(stat.source_snapshot_id) != ("validated", provider, dataset)
        for stat in stats
    ):
        return "label_snapshot_not_validated", None
    if any(
        latest_revisions.get(stat.stat_id) is None
        or latest_revisions[stat.stat_id][1] != stat.source_snapshot_id
        for stat in stats
    ):
        return "label_revision_mismatch", None
    label_stat = stats_by_team[team_a_id]
    label = label_stat.result
    if label is None:
        return "label_not_binary", None
    oe_snapshot_ids = tuple(
        sorted(
            {
                *source_snapshot_ids,
                cast(UUID, game_row["source_snapshot_id"]),
                *(stat.source_snapshot_id for stat in stats),
            },
            key=str,
        )
    )
    return None, _ExampleSpec(
        event_id=event_id,
        feature_snapshot_id=cast(UUID, feature_snapshot["id"]),
        feature_snapshot_hash=str(feature_snapshot["snapshot_hash"]),
        vector_hash=str(feature_snapshot["vector_hash"]),
        team_a_id=team_a_id,
        team_b_id=team_b_id,
        competition_id=cast(UUID | None, game_row["competition_id"]),
        cutoff_at=cutoff_at,
        label_team_a_win=label,
        label_source_revision_id=latest_revisions[label_stat.stat_id][0],
        label_source_snapshot_id=label_stat.source_snapshot_id,
        oe_snapshot_ids=oe_snapshot_ids,
    )


def _stored_dataset(connection: Connection, row: RowMapping) -> StoredTrainingDataset:
    examples = cast(Table, TrainingDatasetExample.__table__)
    example_rows = (
        connection.execute(
            select(examples).where(examples.c.dataset_id == row["id"]).order_by(examples.c.position)
        )
        .mappings()
        .all()
    )
    stored_examples = tuple(
        StoredTrainingExample(
            position=int(item["position"]),
            event_id=cast(UUID, item["event_id"]),
            feature_snapshot_id=cast(UUID, item["feature_snapshot_id"]),
            team_a_id=cast(UUID, item["team_a_id"]),
            team_b_id=cast(UUID, item["team_b_id"]),
            competition_id=cast(UUID | None, item["competition_id"]),
            cutoff_at=cast(datetime, item["cutoff_at"]),
            label_team_a_win=bool(item["label_team_a_win"]),
            label_source_revision_id=cast(UUID, item["label_source_revision_id"]),
            label_source_snapshot_id=cast(UUID, item["label_source_snapshot_id"]),
        )
        for item in example_rows
    )
    return StoredTrainingDataset(
        dataset_id=cast(UUID, row["id"]),
        market=str(row["market"]),
        provider=str(row["provider"]),
        dataset=str(row["dataset"]),
        dataset_version=str(row["dataset_version"]),
        feature_set_id=cast(UUID, row["feature_set_id"]),
        feature_set_version=str(row["feature_set_version"]),
        feature_set_hash=str(row["feature_set_hash"]),
        label_definition=str(row["label_definition"]),
        quality_filter=MappingProxyType(dict(cast(Mapping[str, object], row["quality_filter"]))),
        period_start=cast(datetime, row["period_start"]),
        period_end=cast(datetime, row["period_end"]),
        cutoff_min=cast(datetime, row["cutoff_min"]),
        cutoff_max=cast(datetime, row["cutoff_max"]),
        competition_ids=tuple(UUID(value) for value in cast(Sequence[str], row["competition_ids"])),
        oe_snapshot_ids=tuple(UUID(value) for value in cast(Sequence[str], row["oe_snapshot_ids"])),
        exclusions=tuple(
            MappingProxyType(dict(item))
            for item in cast(Sequence[Mapping[str, str]], row["exclusions"])
        ),
        example_count=int(row["example_count"]),
        exclusion_count=int(row["exclusion_count"]),
        examples_fingerprint=str(row["examples_fingerprint"]),
        dataset_hash=str(row["dataset_hash"]),
        code_commit=str(row["code_commit"]),
        created_at=cast(datetime, row["created_at"]),
        examples=stored_examples,
    )


def _content_hash(document: object) -> str:
    payload = json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
