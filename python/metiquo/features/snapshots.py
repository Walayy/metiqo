"""Persistance append-only de vecteurs de features entièrement retraçables."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.feature_models import FeatureSnapshot
from metiquo.db.raw_models import Snapshot as OeSnapshot
from metiquo.features.registry import FeatureValue, RegisteredFeatureVector
from metiquo.features.temporal import AsOfGameBatch, CutoffViolationError, FeatureCutoff
from metiquo.foundation.time import Clock, SystemClock

_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_REQUIRED_CALLER_CHECKS = frozenset({"train_only_transforms"})


@dataclass(frozen=True, slots=True)
class FeatureSnapshotSpec:
    event_id: UUID
    team_a_id: UUID
    team_b_id: UUID
    target_oe_snapshot_id: UUID
    cutoff: FeatureCutoff
    vector: RegisteredFeatureVector
    source_batch: AsOfGameBatch
    target_game_ids: frozenset[UUID]
    code_commit: str
    leakage_checks: Mapping[str, bool]
    supersedes_snapshot_id: UUID | None = None
    rebuild_invalidation_ids: frozenset[UUID] = frozenset()


@dataclass(frozen=True, slots=True)
class StoredFeatureSnapshot:
    snapshot_id: UUID
    feature_set_id: UUID
    event_id: UUID
    team_a_id: UUID
    team_b_id: UUID
    target_oe_snapshot_id: UUID
    cutoff_at: datetime
    max_input_time: datetime | None
    max_knowledge_time: datetime | None
    definition_versions: Mapping[str, str]
    values: Mapping[str, object]
    missingness: Mapping[str, bool]
    source_game_ids: tuple[UUID, ...]
    target_game_ids: tuple[UUID, ...]
    source_revision_ids: tuple[UUID, ...]
    source_snapshot_ids: tuple[UUID, ...]
    source_games_fingerprint: str
    code_commit: str
    leakage_checks: Mapping[str, bool]
    rebuild_invalidation_ids: tuple[UUID, ...]
    vector_hash: str
    snapshot_hash: str
    supersedes_snapshot_id: UUID | None
    generation: int
    created_at: datetime


class FeatureSnapshotStore:
    """Créer un snapshot déterministe ou relire l'identique sans mutation."""

    def __init__(self, *, engine: Engine, clock: Clock | None = None) -> None:
        self._engine = engine
        self._clock = clock or SystemClock()

    def create(self, specification: FeatureSnapshotSpec) -> StoredFeatureSnapshot:
        document = _snapshot_document(specification)
        snapshot_hash = _content_hash(document)
        snapshot_id = uuid5(NAMESPACE_URL, f"metiquo:feature-snapshot:{snapshot_hash}")
        created_at = self._clock.now().value
        table = cast(Table, FeatureSnapshot.__table__)
        with self._engine.begin() as connection:
            target_status = connection.execute(
                select(OeSnapshot.status).where(
                    OeSnapshot.id == specification.target_oe_snapshot_id
                )
            ).scalar_one_or_none()
            if target_status != "validated":
                raise ValueError("le snapshot OE cible doit exister et être validé")
            existing = (
                connection.execute(select(table).where(table.c.snapshot_hash == snapshot_hash))
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return _stored(existing)
            generation = 1
            if specification.supersedes_snapshot_id is not None:
                parent = (
                    connection.execute(
                        select(table).where(table.c.id == specification.supersedes_snapshot_id)
                    )
                    .mappings()
                    .one_or_none()
                )
                if parent is None:
                    raise ValueError("feature snapshot parent introuvable")
                _validate_parent(parent, specification)
                generation = int(parent["generation"]) + 1
            statement = insert(table).values(
                id=snapshot_id,
                feature_set_id=specification.vector.feature_set_id,
                event_id=specification.event_id,
                team_a_id=specification.team_a_id,
                team_b_id=specification.team_b_id,
                target_oe_snapshot_id=specification.target_oe_snapshot_id,
                cutoff_at=specification.cutoff.at,
                max_input_time=specification.source_batch.audit.max_input_time,
                max_knowledge_time=specification.source_batch.audit.max_knowledge_time,
                definition_versions=document["definition_versions"],
                values=document["values"],
                missingness=document["missingness"],
                source_game_ids=document["source_game_ids"],
                target_game_ids=document["target_game_ids"],
                source_revision_ids=document["source_revision_ids"],
                source_snapshot_ids=document["source_snapshot_ids"],
                source_games_fingerprint=document["source_games_fingerprint"],
                code_commit=specification.code_commit,
                leakage_checks=document["leakage_checks"],
                rebuild_invalidation_ids=document["rebuild_invalidation_ids"],
                vector_hash=document["vector_hash"],
                snapshot_hash=snapshot_hash,
                supersedes_snapshot_id=specification.supersedes_snapshot_id,
                generation=generation,
                created_at=created_at,
            )
            connection.execute(statement)
            row = (
                connection.execute(select(table).where(table.c.id == snapshot_id)).mappings().one()
            )
        return _stored(row)

    def get(self, snapshot_id: UUID) -> StoredFeatureSnapshot | None:
        table = cast(Table, FeatureSnapshot.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(table).where(table.c.id == snapshot_id))
                .mappings()
                .one_or_none()
            )
        return None if row is None else _stored(row)


def _snapshot_document(specification: FeatureSnapshotSpec) -> dict[str, object]:
    if specification.team_a_id == specification.team_b_id:
        raise ValueError("les équipes du snapshot doivent être distinctes")
    if not _COMMIT.fullmatch(specification.code_commit):
        raise ValueError("code_commit doit être un hash git hexadécimal")
    if not specification.target_game_ids:
        raise ValueError("au moins une game cible exclue doit être déclarée")
    batch = specification.source_batch
    if batch.audit.cutoff_at != specification.cutoff.at:
        raise CutoffViolationError("le cutoff du lot ne correspond pas au snapshot")
    source_game_ids = tuple(sorted((game.game_id for game in batch.games), key=str))
    target_excluded = specification.target_game_ids.isdisjoint(source_game_ids)
    derived_checks = {
        "knowledge_time_cutoff": (
            batch.audit.max_knowledge_time is None
            or batch.audit.max_knowledge_time <= specification.cutoff.at
        ),
        "source_time_strict_cutoff": (
            batch.audit.max_input_time is None
            or batch.audit.max_input_time < specification.cutoff.at
        ),
        "target_game_excluded": target_excluded,
    }
    missing_checks = _REQUIRED_CALLER_CHECKS - specification.leakage_checks.keys()
    if missing_checks:
        raise ValueError(f"contrôles de leakage absents: {sorted(missing_checks)}")
    checks = {**specification.leakage_checks, **derived_checks}
    if any(not isinstance(value, bool) for value in checks.values()):
        raise TypeError("les contrôles de leakage doivent être booléens")
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise CutoffViolationError(f"contrôles de leakage en échec: {failed}")
    values = {
        name: _json_value(value) for name, value in sorted(specification.vector.values.items())
    }
    definitions = dict(sorted(specification.vector.definition_versions.items()))
    if set(values) != set(definitions):
        raise ValueError("valeurs et versions de définitions divergent")
    missingness = {name: value is None for name, value in values.items()}
    source_revisions = tuple(sorted(batch.source_revision_ids, key=str))
    source_snapshots = tuple(
        sorted({*batch.source_snapshot_ids, specification.target_oe_snapshot_id}, key=str)
    )
    games_document = [
        {
            "event_time": game.event_time.isoformat(),
            "game_id": str(game.game_id),
            "revision_id": str(game.source_revision_id),
        }
        for game in sorted(batch.games, key=lambda game: (game.event_time, game.game_id))
    ]
    games_fingerprint = _content_hash(games_document)
    vector_document = {
        "definition_versions": definitions,
        "feature_set_id": str(specification.vector.feature_set_id),
        "feature_set_version": specification.vector.feature_set_version,
        "missingness": missingness,
        "values": values,
    }
    vector_hash = _content_hash(vector_document)
    return {
        "code_commit": specification.code_commit,
        "cutoff_at": specification.cutoff.at.isoformat(),
        "definition_versions": definitions,
        "event_id": str(specification.event_id),
        "feature_set_id": str(specification.vector.feature_set_id),
        "feature_set_version": specification.vector.feature_set_version,
        "leakage_checks": dict(sorted(checks.items())),
        "max_input_time": (
            batch.audit.max_input_time.isoformat()
            if batch.audit.max_input_time is not None
            else None
        ),
        "max_knowledge_time": (
            batch.audit.max_knowledge_time.isoformat()
            if batch.audit.max_knowledge_time is not None
            else None
        ),
        "missingness": missingness,
        "rebuild_invalidation_ids": [
            str(value) for value in sorted(specification.rebuild_invalidation_ids, key=str)
        ],
        "source_game_ids": [str(value) for value in source_game_ids],
        "source_games_fingerprint": games_fingerprint,
        "source_revision_ids": [str(value) for value in source_revisions],
        "source_snapshot_ids": [str(value) for value in source_snapshots],
        "supersedes_snapshot_id": (
            str(specification.supersedes_snapshot_id)
            if specification.supersedes_snapshot_id is not None
            else None
        ),
        "target_oe_snapshot_id": str(specification.target_oe_snapshot_id),
        "target_game_ids": [str(value) for value in sorted(specification.target_game_ids, key=str)],
        "team_a_id": str(specification.team_a_id),
        "team_b_id": str(specification.team_b_id),
        "values": values,
        "vector_hash": vector_hash,
    }


def _validate_parent(parent: RowMapping, specification: FeatureSnapshotSpec) -> None:
    expected = {
        "cutoff_at": specification.cutoff.at,
        "event_id": specification.event_id,
        "feature_set_id": specification.vector.feature_set_id,
        "team_a_id": specification.team_a_id,
        "team_b_id": specification.team_b_id,
    }
    if any(parent[name] != value for name, value in expected.items()):
        raise ValueError("un rebuild ne peut superséder qu'un snapshot de la même candidate")


def _stored(row: RowMapping) -> StoredFeatureSnapshot:
    return StoredFeatureSnapshot(
        snapshot_id=cast(UUID, row["id"]),
        feature_set_id=cast(UUID, row["feature_set_id"]),
        event_id=cast(UUID, row["event_id"]),
        team_a_id=cast(UUID, row["team_a_id"]),
        team_b_id=cast(UUID, row["team_b_id"]),
        target_oe_snapshot_id=cast(UUID, row["target_oe_snapshot_id"]),
        cutoff_at=cast(datetime, row["cutoff_at"]),
        max_input_time=cast(datetime | None, row["max_input_time"]),
        max_knowledge_time=cast(datetime | None, row["max_knowledge_time"]),
        definition_versions=MappingProxyType(
            dict(cast(Mapping[str, str], row["definition_versions"]))
        ),
        values=MappingProxyType(dict(cast(Mapping[str, object], row["values"]))),
        missingness=MappingProxyType(dict(cast(Mapping[str, bool], row["missingness"]))),
        source_game_ids=tuple(UUID(value) for value in cast(list[str], row["source_game_ids"])),
        target_game_ids=tuple(UUID(value) for value in cast(list[str], row["target_game_ids"])),
        source_revision_ids=tuple(
            UUID(value) for value in cast(list[str], row["source_revision_ids"])
        ),
        source_snapshot_ids=tuple(
            UUID(value) for value in cast(list[str], row["source_snapshot_ids"])
        ),
        source_games_fingerprint=str(row["source_games_fingerprint"]),
        code_commit=str(row["code_commit"]),
        leakage_checks=MappingProxyType(dict(cast(Mapping[str, bool], row["leakage_checks"]))),
        rebuild_invalidation_ids=tuple(
            UUID(value) for value in cast(list[str], row["rebuild_invalidation_ids"])
        ),
        vector_hash=str(row["vector_hash"]),
        snapshot_hash=str(row["snapshot_hash"]),
        supersedes_snapshot_id=cast(UUID | None, row["supersedes_snapshot_id"]),
        generation=int(row["generation"]),
        created_at=cast(datetime, row["created_at"]),
    )


def _json_value(value: FeatureValue) -> object:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _content_hash(document: object) -> str:
    serialized = json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()
