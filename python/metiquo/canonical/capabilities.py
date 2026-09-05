"""Registre fermé par défaut des labels, features et marchés calculables."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, RowMapping, Table, func, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.core_models import CapabilityEvaluation, Game
from metiquo.db.raw_models import CanonicalRow, QualityIssue, Snapshot, SourceCatalog
from metiquo.foundation.time import Clock, SystemClock

type CapabilityKind = Literal["label", "feature", "market"]
type CapabilityStateStatus = Literal["enabled", "disabled", "pending"]


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """Seuils versionnés et colonnes requises pour une capacité."""

    name: str
    kind: CapabilityKind
    required_columns: tuple[str, ...]
    minimum_completeness: Decimal
    minimum_sample_size: int
    threshold_version: str = "lol-capability-thresholds-v1"

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.threshold_version.strip():
            raise ValueError("capacité et version de seuil requises")
        if not Decimal("0") <= self.minimum_completeness <= Decimal("1"):
            raise ValueError("seuil de complétude hors bornes")
        if self.minimum_sample_size < 0:
            raise ValueError("taille d'échantillon négative")
        if any(not column.strip() for column in self.required_columns):
            raise ValueError("colonne requise vide")


@dataclass(frozen=True, slots=True)
class MarketGateEvidence:
    """Preuves externes au snapshot ; une valeur absente reste pending."""

    settlement_rules: bool | None = None
    model_validated: bool | None = None
    calibration_acceptable: bool | None = None
    mapping_stable: bool | None = None
    odds_fresh: bool | None = None


@dataclass(frozen=True, slots=True)
class CapabilityState:
    snapshot_id: UUID
    capability: str
    capability_kind: CapabilityKind
    status: CapabilityStateStatus
    reason_codes: tuple[str, ...]
    threshold_version: str
    evaluation_revision: int
    required_columns: tuple[str, ...]
    observed_columns: tuple[str, ...]
    minimum_completeness: Decimal
    observed_completeness: Decimal
    minimum_sample_size: int
    observed_sample_size: int
    gates: Mapping[str, bool | None]
    evaluated_at: datetime


DEFAULT_CAPABILITY_DEFINITIONS = (
    CapabilityDefinition(
        "label.match_winner",
        "label",
        ("datacompleteness", "result"),
        Decimal("0.9500"),
        100,
    ),
    CapabilityDefinition(
        "feature.early_game",
        "feature",
        ("golddiffat15", "xpdiffat15"),
        Decimal("0.8000"),
        50,
    ),
    CapabilityDefinition(
        "feature.side_strength",
        "feature",
        ("result",),
        Decimal("0.9000"),
        50,
    ),
    CapabilityDefinition(
        "feature.team_form",
        "feature",
        ("result",),
        Decimal("0.9000"),
        50,
    ),
    CapabilityDefinition(
        "market.match_winner",
        "market",
        ("datacompleteness", "result"),
        Decimal("0.9500"),
        100,
    ),
)


class CapabilityRegistry:
    """Évaluer puis historiser les capacités du corpus raw courant d'un snapshot."""

    def __init__(
        self,
        *,
        engine: Engine,
        clock: Clock | None = None,
        definitions: Sequence[CapabilityDefinition] = DEFAULT_CAPABILITY_DEFINITIONS,
    ) -> None:
        if not definitions:
            raise ValueError("au moins une définition de capacité est requise")
        names = [definition.name for definition in definitions]
        if len(names) != len(set(names)):
            raise ValueError("définitions de capacité dupliquées")
        self._engine = engine
        self._clock = clock or SystemClock()
        self._definitions = tuple(definitions)

    def evaluate_current(
        self,
        *,
        provider: str,
        dataset: str,
        market_evidence: Mapping[str, MarketGateEvidence] | None = None,
    ) -> tuple[CapabilityState, ...]:
        catalog = cast(Table, SourceCatalog.__table__)
        with self._engine.connect() as connection:
            snapshot_ids = tuple(
                connection.execute(
                    select(catalog.c.current_snapshot_id)
                    .where(
                        catalog.c.provider == provider,
                        catalog.c.dataset == dataset,
                        catalog.c.current_snapshot_id.is_not(None),
                    )
                    .order_by(catalog.c.season_year)
                ).scalars()
            )
        states: list[CapabilityState] = []
        for snapshot_id in snapshot_ids:
            if isinstance(snapshot_id, UUID):
                states.extend(
                    self.evaluate_snapshot(
                        snapshot_id=snapshot_id,
                        market_evidence=market_evidence,
                    )
                )
        return tuple(states)

    def evaluate_snapshot(
        self,
        *,
        snapshot_id: UUID,
        market_evidence: Mapping[str, MarketGateEvidence] | None = None,
    ) -> tuple[CapabilityState, ...]:
        evaluated_at = self._clock.now().value
        evidence = market_evidence or {}
        with self._engine.begin() as connection:
            source = self._snapshot_source(connection, snapshot_id)
            observed_columns = self._observed_columns(
                connection,
                provider=str(source["provider"]),
                dataset=str(source["dataset"]),
            )
            sample_size, completeness = self._coverage(
                connection,
                provider=str(source["provider"]),
                dataset=str(source["dataset"]),
            )
            disabled_by_quality = self._quality_issues(connection, snapshot_id)
            states: dict[str, CapabilityState] = {}
            for definition in self._definitions:
                state = _evaluate_definition(
                    definition,
                    snapshot_id=snapshot_id,
                    observed_columns=observed_columns,
                    observed_sample_size=sample_size,
                    observed_completeness=completeness,
                    quality_reason_codes=disabled_by_quality.get(definition.name, ()),
                    label_state=states.get("label.match_winner"),
                    market_evidence=evidence.get(definition.name),
                    evaluated_at=evaluated_at,
                )
                revision = self._persist(connection, state)
                states[definition.name] = _with_revision(state, revision)
        current_definitions = {
            (definition.name, definition.threshold_version) for definition in self._definitions
        }
        return tuple(
            state
            for state in self.list_latest(snapshot_id=snapshot_id)
            if (state.capability, state.threshold_version) in current_definitions
        )

    def list_latest(self, *, snapshot_id: UUID | None = None) -> tuple[CapabilityState, ...]:
        table = cast(Table, CapabilityEvaluation.__table__)
        statement = select(table)
        if snapshot_id is not None:
            statement = statement.where(table.c.snapshot_id == snapshot_id)
        statement = statement.distinct(
            table.c.snapshot_id,
            table.c.capability,
            table.c.threshold_version,
        ).order_by(
            table.c.snapshot_id,
            table.c.capability,
            table.c.threshold_version,
            table.c.evaluation_revision.desc(),
        )
        with self._engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return tuple(_state_from_row(row) for row in rows)

    @staticmethod
    def _snapshot_source(connection: Connection, snapshot_id: UUID) -> RowMapping:
        snapshots = cast(Table, Snapshot.__table__)
        catalogs = cast(Table, SourceCatalog.__table__)
        row = (
            connection.execute(
                select(catalogs.c.provider, catalogs.c.dataset, snapshots.c.status)
                .join(catalogs, catalogs.c.id == snapshots.c.source_catalog_id)
                .where(snapshots.c.id == snapshot_id)
            )
            .mappings()
            .one()
        )
        if row["status"] != "validated":
            raise ValueError("seul un snapshot validé peut alimenter le registre")
        return row

    @staticmethod
    def _observed_columns(
        connection: Connection, *, provider: str, dataset: str
    ) -> tuple[str, ...]:
        raw = cast(Table, CanonicalRow.__table__)
        payloads = connection.execute(
            select(raw.c.payload).where(raw.c.provider == provider, raw.c.dataset == dataset)
        ).scalars()
        return tuple(sorted({str(key) for payload in payloads for key in payload}))

    @staticmethod
    def _coverage(connection: Connection, *, provider: str, dataset: str) -> tuple[int, Decimal]:
        raw = cast(Table, CanonicalRow.__table__)
        games = cast(Table, Game.__table__)
        total, usable = connection.execute(
            select(
                func.count(games.c.id),
                func.count(games.c.id).filter(games.c.usable_for_training.is_(True)),
            )
            .join(raw, raw.c.id == games.c.source_raw_row_id)
            .where(raw.c.provider == provider, raw.c.dataset == dataset)
        ).one()
        total_count = int(total)
        usable_count = int(usable)
        if total_count == 0:
            return 0, Decimal("0.0000")
        completeness = (Decimal(usable_count) / Decimal(total_count)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        return usable_count, completeness

    @staticmethod
    def _quality_issues(connection: Connection, snapshot_id: UUID) -> Mapping[str, tuple[str, ...]]:
        table = cast(Table, QualityIssue.__table__)
        rows = connection.execute(
            select(table.c.capability, table.c.code).where(
                table.c.snapshot_id == snapshot_id,
                table.c.capability.is_not(None),
                table.c.severity.in_(("blocking", "capability-only")),
            )
        )
        grouped: dict[str, list[str]] = {}
        for capability, code in rows:
            grouped.setdefault(str(capability), []).append(f"QUALITY_ISSUE:{code}")
        return {key: tuple(sorted(set(values))) for key, values in grouped.items()}

    @staticmethod
    def _persist(connection: Connection, state: CapabilityState) -> int:
        table = cast(Table, CapabilityEvaluation.__table__)
        evidence_hash = _state_hash(state)
        previous = (
            connection.execute(
                select(table.c.id, table.c.evaluation_revision, table.c.evidence_hash)
                .where(
                    table.c.snapshot_id == state.snapshot_id,
                    table.c.capability == state.capability,
                    table.c.threshold_version == state.threshold_version,
                )
                .order_by(table.c.evaluation_revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if previous is not None and previous["evidence_hash"] == evidence_hash:
            return int(previous["evaluation_revision"])
        revision = 1 if previous is None else int(previous["evaluation_revision"]) + 1
        previous_id = None if previous is None else previous["id"]
        evaluation_id = uuid5(
            NAMESPACE_URL,
            f"metiquo:capability:{state.snapshot_id}:{state.capability}:"
            f"{state.threshold_version}:{revision}:{evidence_hash}",
        )
        connection.execute(
            insert(table).values(
                id=evaluation_id,
                snapshot_id=state.snapshot_id,
                capability=state.capability,
                capability_kind=state.capability_kind,
                threshold_version=state.threshold_version,
                evaluation_revision=revision,
                previous_evaluation_id=previous_id,
                status=state.status,
                reason_codes=list(state.reason_codes),
                required_columns=list(state.required_columns),
                observed_columns=list(state.observed_columns),
                minimum_completeness=state.minimum_completeness,
                observed_completeness=state.observed_completeness,
                minimum_sample_size=state.minimum_sample_size,
                observed_sample_size=state.observed_sample_size,
                gates=dict(state.gates),
                evidence_hash=evidence_hash,
                evaluated_at=state.evaluated_at,
            )
        )
        return revision


def _evaluate_definition(
    definition: CapabilityDefinition,
    *,
    snapshot_id: UUID,
    observed_columns: tuple[str, ...],
    observed_sample_size: int,
    observed_completeness: Decimal,
    quality_reason_codes: tuple[str, ...],
    label_state: CapabilityState | None,
    market_evidence: MarketGateEvidence | None,
    evaluated_at: datetime,
) -> CapabilityState:
    missing = tuple(sorted(set(definition.required_columns) - set(observed_columns)))
    data_ready = not missing and observed_completeness >= definition.minimum_completeness
    if quality_reason_codes:
        data_ready = False
    sample_ready = observed_sample_size >= definition.minimum_sample_size
    gates: dict[str, bool | None] = {"data": data_ready, "sample": sample_ready}
    reasons = list(quality_reason_codes)
    if missing:
        reasons.append(f"MISSING_COLUMNS:{','.join(missing)}")
    if observed_completeness < definition.minimum_completeness:
        reasons.append("INSUFFICIENT_COMPLETENESS")
    if not sample_ready:
        reasons.append("INSUFFICIENT_SAMPLE")

    if definition.kind == "market":
        evidence = market_evidence or MarketGateEvidence()
        gates = {
            "label": label_state is not None and label_state.status == "enabled",
            "data": data_ready,
            "rules": evidence.settlement_rules,
            "model": evidence.model_validated,
            "calibration": evidence.calibration_acceptable,
            "mapping": evidence.mapping_stable,
            "odds": evidence.odds_fresh,
            "sample": sample_ready,
        }
        if not gates["label"]:
            reasons.append("LABEL_UNAVAILABLE")
        for gate, value in gates.items():
            if gate in {"label", "data", "sample"}:
                continue
            if value is None:
                reasons.append(f"GATE_{gate.upper()}_PENDING")
            elif value is False:
                reasons.append(f"GATE_{gate.upper()}_FAILED")

    status: CapabilityStateStatus
    if any(value is False for value in gates.values()):
        status = "disabled"
    elif any(value is None for value in gates.values()):
        status = "pending"
    else:
        status = "enabled"
    return CapabilityState(
        snapshot_id=snapshot_id,
        capability=definition.name,
        capability_kind=definition.kind,
        status=status,
        reason_codes=tuple(sorted(set(reasons))),
        threshold_version=definition.threshold_version,
        evaluation_revision=0,
        required_columns=definition.required_columns,
        observed_columns=observed_columns,
        minimum_completeness=definition.minimum_completeness,
        observed_completeness=observed_completeness,
        minimum_sample_size=definition.minimum_sample_size,
        observed_sample_size=observed_sample_size,
        gates=gates,
        evaluated_at=evaluated_at,
    )


def _state_hash(state: CapabilityState) -> str:
    document = {
        "capability": state.capability,
        "gates": dict(state.gates),
        "minimumCompleteness": str(state.minimum_completeness),
        "minimumSampleSize": state.minimum_sample_size,
        "observedColumns": state.observed_columns,
        "observedCompleteness": str(state.observed_completeness),
        "observedSampleSize": state.observed_sample_size,
        "reasons": state.reason_codes,
        "requiredColumns": state.required_columns,
        "status": state.status,
        "thresholdVersion": state.threshold_version,
    }
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _with_revision(state: CapabilityState, revision: int) -> CapabilityState:
    return CapabilityState(
        snapshot_id=state.snapshot_id,
        capability=state.capability,
        capability_kind=state.capability_kind,
        status=state.status,
        reason_codes=state.reason_codes,
        threshold_version=state.threshold_version,
        evaluation_revision=revision,
        required_columns=state.required_columns,
        observed_columns=state.observed_columns,
        minimum_completeness=state.minimum_completeness,
        observed_completeness=state.observed_completeness,
        minimum_sample_size=state.minimum_sample_size,
        observed_sample_size=state.observed_sample_size,
        gates=state.gates,
        evaluated_at=state.evaluated_at,
    )


def _state_from_row(row: RowMapping) -> CapabilityState:
    return CapabilityState(
        snapshot_id=cast(UUID, row["snapshot_id"]),
        capability=str(row["capability"]),
        capability_kind=cast(CapabilityKind, row["capability_kind"]),
        status=cast(CapabilityStateStatus, row["status"]),
        reason_codes=tuple(str(value) for value in row["reason_codes"]),
        threshold_version=str(row["threshold_version"]),
        evaluation_revision=int(row["evaluation_revision"]),
        required_columns=tuple(str(value) for value in row["required_columns"]),
        observed_columns=tuple(str(value) for value in row["observed_columns"]),
        minimum_completeness=cast(Decimal, row["minimum_completeness"]),
        observed_completeness=cast(Decimal, row["observed_completeness"]),
        minimum_sample_size=int(row["minimum_sample_size"]),
        observed_sample_size=int(row["observed_sample_size"]),
        gates=cast(Mapping[str, bool | None], row["gates"]),
        evaluated_at=cast(datetime, row["evaluated_at"]),
    )
