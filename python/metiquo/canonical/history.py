"""Historique append-only et roundtrip de provenance des entités canoniques."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.core_models import (
    CanonicalEntityRevision,
    CanonicalEntitySource,
    Competition,
    Game,
    GamePlayerStat,
    GameTeamStat,
    GameTitle,
    Patch,
    Player,
    RosterObservation,
    Series,
    Team,
)
from metiquo.db.raw_models import CanonicalRow

_PROVENANCE_COLUMNS = frozenset(
    {
        "source_raw_row_id",
        "source_snapshot_id",
        "source_run_id",
        "source_natural_key",
        "source_row_hash",
        "source_row_revision",
        "transformation_version",
        "processed_at",
    }
)


@dataclass(frozen=True, slots=True)
class CanonicalHistoryStatistics:
    """Nombre d'états ajoutés et de preuves raw copiées."""

    revisions_created: int
    source_links_created: int


@dataclass(frozen=True, slots=True)
class _EntitySpec:
    entity_type: str
    table: Table
    source_strategy: str = "representative"


_ENTITY_SPECS = (
    _EntitySpec("game_title", cast(Table, GameTitle.__table__)),
    _EntitySpec("competition", cast(Table, Competition.__table__)),
    _EntitySpec("team", cast(Table, Team.__table__)),
    _EntitySpec("player", cast(Table, Player.__table__)),
    _EntitySpec("patch", cast(Table, Patch.__table__)),
    _EntitySpec("game", cast(Table, Game.__table__), "game"),
    _EntitySpec("series", cast(Table, Series.__table__), "series"),
    _EntitySpec("game_team_stat", cast(Table, GameTeamStat.__table__)),
    _EntitySpec("game_player_stat", cast(Table, GamePlayerStat.__table__)),
    _EntitySpec("roster_observation", cast(Table, RosterObservation.__table__)),
)


class CanonicalHistoryRecorder:
    """Copier un nouvel état seulement si contenu ou provenance a changé."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    def record(
        self,
        *,
        provider: str,
        dataset: str,
        entity_types: Iterable[str] | None = None,
    ) -> CanonicalHistoryStatistics:
        selected = set(entity_types) if entity_types is not None else None
        revisions_created = 0
        source_links_created = 0
        with self._engine.begin() as connection:
            for spec in _ENTITY_SPECS:
                if selected is not None and spec.entity_type not in selected:
                    continue
                for entity in self._entities(connection, spec, provider, dataset):
                    sources = self._sources(connection, spec, entity, provider, dataset)
                    if not sources:
                        continue
                    created = self._record_entity(connection, spec, entity, sources)
                    if created:
                        revisions_created += 1
                        source_links_created += len(sources)
        return CanonicalHistoryStatistics(revisions_created, source_links_created)

    @staticmethod
    def _entities(
        connection: Connection,
        spec: _EntitySpec,
        provider: str,
        dataset: str,
    ) -> Sequence[RowMapping]:
        raw = cast(Table, CanonicalRow.__table__)
        return (
            connection.execute(
                select(spec.table)
                .join(raw, raw.c.id == spec.table.c.source_raw_row_id)
                .where(raw.c.provider == provider, raw.c.dataset == dataset)
                .order_by(spec.table.c.id)
            )
            .mappings()
            .all()
        )

    def _sources(
        self,
        connection: Connection,
        spec: _EntitySpec,
        entity: RowMapping,
        provider: str,
        dataset: str,
    ) -> Sequence[RowMapping]:
        raw = cast(Table, CanonicalRow.__table__)
        predicate = raw.c.id == entity["source_raw_row_id"]
        if spec.source_strategy == "game":
            predicate = raw.c.payload["gameid"].astext == entity["source_game_id"]
        elif spec.source_strategy == "series":
            games = cast(Table, Game.__table__)
            game_ids = tuple(
                connection.execute(
                    select(games.c.source_game_id)
                    .where(games.c.series_id == entity["id"])
                    .order_by(games.c.source_game_id)
                ).scalars()
            )
            if game_ids:
                predicate = raw.c.payload["gameid"].astext.in_(game_ids)
        return (
            connection.execute(
                select(
                    raw.c.id,
                    raw.c.natural_key,
                    raw.c.row_hash,
                    raw.c.revision,
                    raw.c.payload,
                    raw.c.source_snapshot_id,
                    raw.c.source_run_id,
                )
                .where(raw.c.provider == provider, raw.c.dataset == dataset, predicate)
                .order_by(raw.c.id)
            )
            .mappings()
            .all()
        )

    @staticmethod
    def _record_entity(
        connection: Connection,
        spec: _EntitySpec,
        entity: RowMapping,
        sources: Sequence[RowMapping],
    ) -> bool:
        entity_id = cast(UUID, entity["id"])
        payload = {
            key: _json_value(value)
            for key, value in entity.items()
            if key not in _PROVENANCE_COLUMNS
        }
        quality_status = str(entity.get("quality_status") or "validated")
        transformation_version = str(entity["transformation_version"])
        fingerprint = _fingerprint(payload, sources, transformation_version, quality_status)
        history = cast(Table, CanonicalEntityRevision.__table__)
        previous = (
            connection.execute(
                select(history.c.id, history.c.revision, history.c.payload_hash)
                .where(
                    history.c.entity_type == spec.entity_type,
                    history.c.entity_id == entity_id,
                )
                .order_by(history.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if previous is not None and previous["payload_hash"] == fingerprint:
            return False

        revision = 1 if previous is None else int(previous["revision"]) + 1
        previous_id = None if previous is None else cast(UUID, previous["id"])
        revision_id = uuid5(
            NAMESPACE_URL,
            f"metiquo:canonical-history:{spec.entity_type}:{entity_id}:{revision}:{fingerprint}",
        )
        representative = sources[0]
        connection.execute(
            insert(history).values(
                id=revision_id,
                entity_type=spec.entity_type,
                entity_id=entity_id,
                revision=revision,
                previous_revision_id=previous_id,
                payload=payload,
                payload_hash=fingerprint,
                transformation_version=transformation_version,
                processed_at=entity["processed_at"],
                correction=any(int(source["revision"]) > 1 for source in sources),
                quality_status=quality_status,
                source_snapshot_id=representative["source_snapshot_id"],
                source_run_id=representative["source_run_id"],
            )
        )
        source_table = cast(Table, CanonicalEntitySource.__table__)
        connection.execute(
            insert(source_table),
            [
                {
                    "entity_revision_id": revision_id,
                    "source_raw_row_id": source["id"],
                    "source_snapshot_id": source["source_snapshot_id"],
                    "source_run_id": source["source_run_id"],
                    "source_natural_key": source["natural_key"],
                    "source_row_hash": source["row_hash"],
                    "source_row_revision": source["revision"],
                    "source_payload": source["payload"],
                }
                for source in sources
            ],
        )
        return True


def _fingerprint(
    payload: Mapping[str, object],
    sources: Sequence[RowMapping],
    transformation_version: str,
    quality_status: str,
) -> str:
    document = {
        "payload": payload,
        "quality_status": quality_status,
        "sources": [
            {
                "id": str(source["id"]),
                "natural_key": source["natural_key"],
                "revision": source["revision"],
                "row_hash": source["row_hash"],
                "snapshot_id": str(source["source_snapshot_id"]),
                "run_id": str(source["source_run_id"]),
            }
            for source in sources
        ],
        "transformation_version": transformation_version,
    }
    serialized = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _json_value(value: object) -> Any:
    if isinstance(value, (UUID, datetime, date, Decimal)):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
