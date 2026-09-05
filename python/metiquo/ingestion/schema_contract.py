"""Contrat évolutif et registre de capacités du schéma Oracle's Elixir."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from metiquo.ingestion.manifest import ColumnDefinition, SchemaDocument
from metiquo.ingestion.source_errors import SchemaIncompatible


@dataclass(frozen=True, slots=True)
class CapabilityStatus:
    capability: str
    enabled: bool
    missing_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SchemaAssessment:
    schema: SchemaDocument
    missing_core_columns: tuple[str, ...]
    additive_columns: tuple[str, ...]
    missing_optional_columns: tuple[str, ...]
    capabilities: tuple[CapabilityStatus, ...]

    @property
    def blocking(self) -> bool:
        return bool(self.missing_core_columns)

    @property
    def capability_registry(self) -> Mapping[str, bool]:
        return MappingProxyType(
            {capability.capability: capability.enabled for capability in self.capabilities}
        )


@dataclass(frozen=True, slots=True)
class SchemaDiff:
    previous_fingerprint: str
    current_fingerprint: str
    added_columns: tuple[str, ...]
    removed_columns: tuple[str, ...]
    type_changes: tuple[str, ...]
    order_changed: bool

    @property
    def changed(self) -> bool:
        return self.previous_fingerprint != self.current_fingerprint


class EvolvingSchemaContract:
    """Évaluer le brut sans supprimer les colonnes nouvelles ni inventer les absentes."""

    def __init__(
        self,
        *,
        version: str,
        core_required: Sequence[str],
        optional: Sequence[str],
        capabilities: Mapping[str, Sequence[str]],
    ) -> None:
        if not version.strip():
            raise ValueError("version de contrat requise")
        self.version = version
        self.core_required = frozenset(core_required)
        self.optional = frozenset(optional)
        self.capabilities = MappingProxyType(
            {name: frozenset(columns) for name, columns in capabilities.items()}
        )
        if not self.core_required or any(not name.strip() for name in self.core_required):
            raise ValueError("colonnes cœur invalides")
        if any(not name.strip() for name in self.capabilities):
            raise ValueError("nom de capacité invalide")

    def assess(
        self,
        observed_columns: Sequence[str],
        *,
        declared_types: Mapping[str, str] | None = None,
    ) -> SchemaAssessment:
        columns = tuple(column.strip() for column in observed_columns)
        if any(not column for column in columns) or len(set(columns)) != len(columns):
            raise ValueError("colonnes observées vides ou dupliquées")
        observed = set(columns)
        known = self.core_required | self.optional | set().union(*self.capabilities.values())
        types = declared_types or {}
        schema = SchemaDocument(
            tuple(
                ColumnDefinition(position, column, types.get(column, "string"), True)
                for position, column in enumerate(columns)
            )
        )
        missing_core = tuple(sorted(self.core_required - observed))
        statuses = tuple(
            CapabilityStatus(
                capability=name,
                enabled=not (missing := tuple(sorted((required | self.core_required) - observed))),
                missing_columns=missing,
            )
            for name, required in sorted(self.capabilities.items())
        )
        return SchemaAssessment(
            schema=schema,
            missing_core_columns=missing_core,
            additive_columns=tuple(column for column in columns if column not in known),
            missing_optional_columns=tuple(sorted(self.optional - observed)),
            capabilities=statuses,
        )

    @staticmethod
    def preserve_raw_row(columns: Sequence[str], values: Sequence[str]) -> dict[str, str]:
        if len(columns) != len(values):
            raise ValueError("la ligne raw ne correspond pas à son en-tête")
        return dict(zip(columns, values, strict=True))

    @staticmethod
    def require_ingestable(assessment: SchemaAssessment, *, transport: str, source_id: str) -> None:
        if assessment.blocking:
            raise SchemaIncompatible(
                "colonnes cœur Oracle's Elixir manquantes",
                transport=transport,
                source_id=source_id,
                retryable=False,
                context={
                    "rule": "SCHEMA_CORE_MISSING",
                    "missingColumns": ",".join(assessment.missing_core_columns),
                    "schemaFingerprint": assessment.schema.fingerprint,
                },
            )


def diff_schemas(previous: SchemaDocument, current: SchemaDocument) -> SchemaDiff:
    previous_by_name = {column.name: column for column in previous.columns}
    current_by_name = {column.name: column for column in current.columns}
    previous_names = tuple(previous_by_name)
    current_names = tuple(current_by_name)
    common_previous = tuple(name for name in previous_names if name in current_by_name)
    common_current = tuple(name for name in current_names if name in previous_by_name)
    return SchemaDiff(
        previous_fingerprint=previous.fingerprint,
        current_fingerprint=current.fingerprint,
        added_columns=tuple(name for name in current_names if name not in previous_by_name),
        removed_columns=tuple(name for name in previous_names if name not in current_by_name),
        type_changes=tuple(
            name
            for name in common_current
            if current_by_name[name].data_type != previous_by_name[name].data_type
        ),
        order_changed=common_previous != common_current,
    )


ORACLES_ELIXIR_SCHEMA_V1 = EvolvingSchemaContract(
    version="oe-schema-v1",
    core_required=(
        "gameid",
        "date",
        "participantid",
        "side",
        "position",
        "teamname",
        "league",
    ),
    optional=(
        "teamid",
        "playerid",
        "playername",
        "champion",
        "split",
        "playoffs",
        "patch",
    ),
    capabilities={
        "feature.early_game": ("golddiffat15", "xpdiffat15"),
        "feature.side_strength": ("result",),
        "feature.team_form": ("result",),
        "market.match_winner": ("result", "datacompleteness"),
    },
)
