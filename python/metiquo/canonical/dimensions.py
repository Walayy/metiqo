"""Construction idempotente des dimensions canoniques depuis le raw validé."""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, RowMapping, Select, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.core_models import Competition, GameTitle, Patch, Player, Team
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot
from metiquo.foundation.time import Clock, SystemClock

ORACLES_ELIXIR_PROVIDER = "oracles_elixir"
LOL_DATASET = "league_of_legends_match_data"
TRANSFORMATION_VERSION = "canonical-dimensions-v1"
LOL_SLUG = "league-of-legends"
_PLAYER_POSITIONS = frozenset({"top", "jng", "jungle", "mid", "bot", "adc", "sup", "support"})


@dataclass(frozen=True, slots=True)
class CanonicalDimensionStatistics:
    """Volume source admissible et cardinalité de chaque dimension projetée."""

    source_rows: int
    game_titles: int
    competitions: int
    teams: int
    players: int
    patches: int


@dataclass(frozen=True, slots=True)
class _SourceEntity:
    identity: str
    normalized_name: str
    display_name: str | None
    identity_kind: str | None
    provenance: Mapping[str, object]


class CanonicalDimensionBuilder:
    """Projeter uniquement les lignes OE rattachées à un snapshot validé."""

    def __init__(self, *, engine: Engine, clock: Clock | None = None) -> None:
        self._engine = engine
        self._clock = clock or SystemClock()

    def build(
        self,
        *,
        provider: str = ORACLES_ELIXIR_PROVIDER,
        dataset: str = LOL_DATASET,
    ) -> CanonicalDimensionStatistics:
        processed_at = self._clock.now().value
        with self._engine.begin() as connection:
            rows = connection.execute(self._validated_rows(provider, dataset)).mappings().all()
            if not rows:
                return CanonicalDimensionStatistics(0, 0, 0, 0, 0, 0)

            game_title_id = _canonical_id("game-title", LOL_SLUG)
            game_provenance = _provenance(rows[0], processed_at)
            game_title_values = {
                "id": game_title_id,
                "slug": LOL_SLUG,
                "display_name": "League of Legends",
                **game_provenance,
            }
            game_table = cast(Table, GameTitle.__table__)
            game_stmt = insert(game_table).values(game_title_values)
            connection.execute(
                game_stmt.on_conflict_do_update(
                    constraint="uq_game_titles_slug",
                    set_={key: game_stmt.excluded[key] for key in game_provenance},
                )
            )

            competitions: dict[str, _SourceEntity] = {}
            teams: dict[str, _SourceEntity] = {}
            players: dict[str, _SourceEntity] = {}
            patches: dict[str, _SourceEntity] = {}
            for row in rows:
                payload = _payload(row)
                provenance = _provenance(row, processed_at)
                _collect_competition(competitions, payload, provenance)
                _collect_team(teams, payload, provenance)
                _collect_player(players, payload, provenance)
                _collect_patch(patches, payload, provenance)

            self._upsert_entities(connection, Competition, game_title_id, competitions)
            self._upsert_entities(connection, Team, game_title_id, teams)
            self._upsert_entities(connection, Player, game_title_id, players)
            self._upsert_entities(connection, Patch, game_title_id, patches)

        return CanonicalDimensionStatistics(
            source_rows=len(rows),
            game_titles=1,
            competitions=len(competitions),
            teams=len(teams),
            players=len(players),
            patches=len(patches),
        )

    @staticmethod
    def _validated_rows(provider: str, dataset: str) -> Select[tuple[Any, ...]]:
        raw = CanonicalRow.__table__
        snapshots = Snapshot.__table__
        runs = IngestionRun.__table__
        return (
            select(
                raw.c.id,
                raw.c.natural_key,
                raw.c.row_hash,
                raw.c.revision,
                raw.c.payload,
                raw.c.event_date,
                raw.c.source_snapshot_id,
                raw.c.source_run_id,
            )
            .join(
                snapshots,
                (snapshots.c.id == raw.c.source_snapshot_id) & (snapshots.c.status == "validated"),
            )
            .join(
                runs,
                (runs.c.id == raw.c.source_run_id) & (runs.c.status == "succeeded"),
            )
            .where(raw.c.provider == provider, raw.c.dataset == dataset)
            .order_by(raw.c.event_date.asc().nulls_last(), raw.c.natural_key.asc())
        )

    @staticmethod
    def _upsert_entities(
        connection: Connection,
        model: type[Competition] | type[Team] | type[Player] | type[Patch],
        game_title_id: UUID,
        entities: Mapping[str, _SourceEntity],
    ) -> None:
        if not entities:
            return
        table = cast(Table, model.__table__)
        kind = table.name.removesuffix("s")
        identity_column = {
            "competitions": "source_competition_id",
            "teams": "source_team_id",
            "players": "source_player_id",
            "patches": "version",
        }[table.name]
        values: list[dict[str, object]] = []
        for entity in entities.values():
            item: dict[str, object] = {
                "id": _canonical_id(kind, entity.identity),
                "game_title_id": game_title_id,
                identity_column: entity.identity,
                "normalized_name": entity.normalized_name,
                "display_name": entity.display_name,
                **entity.provenance,
            }
            if entity.identity_kind is not None:
                item["source_identity_kind"] = entity.identity_kind
            values.append(item)
        statement = insert(table).values(values)
        mutable_columns = {
            "normalized_name",
            "display_name",
            "source_identity_kind",
            "source_raw_row_id",
            "source_snapshot_id",
            "source_run_id",
            "source_natural_key",
            "source_row_hash",
            "source_row_revision",
            "transformation_version",
            "processed_at",
        } & set(table.c.keys())
        connection.execute(
            statement.on_conflict_do_update(
                constraint=f"uq_{table.name}_game_title_source_identity",
                set_={name: statement.excluded[name] for name in mutable_columns},
            )
        )


def normalize_identity(value: object) -> str:
    """Normaliser sans translittérer ni inventer une identité externe."""

    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    return " ".join(normalized.split()).casefold()


def _display(value: object) -> str | None:
    if value is None:
        return None
    normalized = " ".join(unicodedata.normalize("NFKC", str(value)).split())
    return normalized or None


def _payload(row: RowMapping) -> Mapping[str, object]:
    payload = row["payload"]
    if not isinstance(payload, Mapping):
        return {}
    return cast(Mapping[str, object], payload)


def _provenance(row: RowMapping, processed_at: object) -> dict[str, object]:
    return {
        "source_raw_row_id": row["id"],
        "source_snapshot_id": row["source_snapshot_id"],
        "source_run_id": row["source_run_id"],
        "source_natural_key": row["natural_key"],
        "source_row_hash": row["row_hash"],
        "source_row_revision": row["revision"],
        "transformation_version": TRANSFORMATION_VERSION,
        "processed_at": processed_at,
    }


def _collect_competition(
    target: dict[str, _SourceEntity],
    payload: Mapping[str, object],
    provenance: Mapping[str, object],
) -> None:
    display_name = _display(payload.get("league"))
    identity = normalize_identity(display_name)
    if identity:
        target.setdefault(
            identity,
            _SourceEntity(identity, identity, display_name, None, provenance),
        )


def _collect_team(
    target: dict[str, _SourceEntity],
    payload: Mapping[str, object],
    provenance: Mapping[str, object],
) -> None:
    source_id = _display(payload.get("teamid"))
    identity_kind = "teamid"
    if source_id is None:
        source_id = _display(payload.get("teamname"))
        identity_kind = "teamname"
    identity = normalize_identity(source_id)
    if not identity:
        return
    display_name = _display(payload.get("teamname")) or source_id
    target.setdefault(
        identity,
        _SourceEntity(
            identity,
            normalize_identity(display_name),
            display_name,
            identity_kind,
            provenance,
        ),
    )


def _collect_player(
    target: dict[str, _SourceEntity],
    payload: Mapping[str, object],
    provenance: Mapping[str, object],
) -> None:
    position = normalize_identity(payload.get("position"))
    if position not in _PLAYER_POSITIONS:
        return
    source_id = _display(payload.get("playerid"))
    identity_kind = "playerid"
    if source_id is None:
        source_id = _display(payload.get("playername"))
        identity_kind = "playername"
    identity = normalize_identity(source_id)
    if not identity:
        return
    display_name = _display(payload.get("playername")) or source_id
    target.setdefault(
        identity,
        _SourceEntity(
            identity,
            normalize_identity(display_name),
            display_name,
            identity_kind,
            provenance,
        ),
    )


def _collect_patch(
    target: dict[str, _SourceEntity],
    payload: Mapping[str, object],
    provenance: Mapping[str, object],
) -> None:
    display_name = _display(payload.get("patch"))
    identity = normalize_identity(display_name)
    if identity:
        target.setdefault(
            identity,
            _SourceEntity(identity, identity, display_name, None, provenance),
        )


def _canonical_id(kind: str, identity: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"metiquo:lol:{kind}:{identity}")
