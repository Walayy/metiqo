"""Registre PostgreSQL des colonnes de features autorisées."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.feature_models import FeatureDefinition, FeatureSet, FeatureSetMember
from metiquo.foundation.time import Clock, SystemClock

type FeatureAvailability = Literal["required", "optional", "capability_gated"]
type FeatureValue = bool | int | float | Decimal | str | None

_FEATURE_NAME = re.compile(r"^[a-z][a-z0-9]*(?:[._][a-z0-9]+)*$")


class FeatureRegistryConflictError(ValueError):
    """Une même version logique a été présentée avec un contenu différent."""


class UnregisteredFeatureError(ValueError):
    """Un vecteur ne respecte pas exactement son feature set enregistré."""


@dataclass(frozen=True, slots=True)
class FeatureDefinitionSpec:
    """Spécification déclarative d'une feature et de sa disponibilité."""

    name: str
    domain: str
    definition_version: str
    parameters: Mapping[str, object]
    availability: FeatureAvailability
    code_version: str
    required_capability: str | None = None

    def __post_init__(self) -> None:
        if _FEATURE_NAME.fullmatch(self.name) is None:
            raise ValueError(f"nom de feature non normalisé: {self.name!r}")
        for label, value in (
            ("domaine", self.domain),
            ("version de définition", self.definition_version),
            ("version de code", self.code_version),
        ):
            if not value.strip():
                raise ValueError(f"{label} requis")
        if any(not isinstance(key, str) or not key.strip() for key in self.parameters):
            raise ValueError("les paramètres exigent des clés texte non vides")
        _canonical_json(dict(self.parameters))
        if self.availability == "capability_gated":
            if self.required_capability is None or not self.required_capability.strip():
                raise ValueError("une feature capability_gated exige sa capacité")
        elif self.required_capability is not None:
            raise ValueError("une capacité n'est admise que pour capability_gated")


@dataclass(frozen=True, slots=True)
class FeatureSetSpec:
    """Version ordonnée d'un ensemble fermé de définitions."""

    name: str
    set_version: str
    code_version: str
    definitions: tuple[FeatureDefinitionSpec, ...]

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.set_version.strip() or not self.code_version.strip():
            raise ValueError("nom, version de set et version de code requis")
        if not self.definitions:
            raise ValueError("un feature set doit contenir au moins une définition")
        names = tuple(definition.name for definition in self.definitions)
        if len(names) != len(set(names)):
            raise ValueError("un feature set ne peut pas contenir deux fois le même nom")


@dataclass(frozen=True, slots=True)
class RegisteredFeatureDefinition:
    definition_id: UUID
    name: str
    domain: str
    definition_version: str
    parameters: Mapping[str, object]
    availability: FeatureAvailability
    required_capability: str | None
    code_version: str
    definition_hash: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RegisteredFeatureSet:
    feature_set_id: UUID
    name: str
    set_version: str
    code_version: str
    set_hash: str
    definitions: tuple[RegisteredFeatureDefinition, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RegisteredFeatureVector:
    """Vecteur fermé portant la version du set et de chaque colonne."""

    feature_set_id: UUID
    feature_set_version: str
    values: Mapping[str, FeatureValue]
    definition_versions: Mapping[str, str]


class FeatureRegistry:
    """Enregistrer idempotemment les seules colonnes utilisables en production."""

    def __init__(self, *, engine: Engine, clock: Clock | None = None) -> None:
        self._engine = engine
        self._clock = clock or SystemClock()

    def register_set(self, specification: FeatureSetSpec) -> RegisteredFeatureSet:
        created_at = self._clock.now().value
        with self._engine.begin() as connection:
            definitions = tuple(
                self._register_definition(connection, item, created_at)
                for item in specification.definitions
            )
            expected_hash = _content_hash(
                {
                    "code_version": specification.code_version,
                    "definitions": [item.definition_hash for item in definitions],
                    "name": specification.name,
                    "set_version": specification.set_version,
                }
            )
            sets = cast(Table, FeatureSet.__table__)
            existing = (
                connection.execute(
                    select(sets).where(
                        sets.c.name == specification.name,
                        sets.c.set_version == specification.set_version,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if str(existing["set_hash"]) != expected_hash:
                    key = f"{specification.name}@{specification.set_version}"
                    raise FeatureRegistryConflictError(f"feature set {key} déjà enregistré")
                return self._registered_set(connection, existing)

            set_id = uuid5(
                NAMESPACE_URL,
                f"metiquo:feature-set:{specification.name}:{specification.set_version}",
            )
            connection.execute(
                insert(sets).values(
                    id=set_id,
                    name=specification.name,
                    set_version=specification.set_version,
                    code_version=specification.code_version,
                    set_hash=expected_hash,
                    created_at=created_at,
                )
            )
            members = cast(Table, FeatureSetMember.__table__)
            connection.execute(
                insert(members),
                [
                    {
                        "feature_set_id": set_id,
                        "feature_definition_id": definition.definition_id,
                        "position": position,
                    }
                    for position, definition in enumerate(definitions)
                ],
            )
            row = connection.execute(select(sets).where(sets.c.id == set_id)).mappings().one()
            return self._registered_set(connection, row)

    def get_definition(
        self, name: str, definition_version: str
    ) -> RegisteredFeatureDefinition | None:
        definitions = cast(Table, FeatureDefinition.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(definitions).where(
                        definitions.c.name == name,
                        definitions.c.definition_version == definition_version,
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _registered_definition(row) if row is not None else None

    def get_set(self, name: str, set_version: str) -> RegisteredFeatureSet | None:
        sets = cast(Table, FeatureSet.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(sets).where(
                        sets.c.name == name,
                        sets.c.set_version == set_version,
                    )
                )
                .mappings()
                .one_or_none()
            )
            return self._registered_set(connection, row) if row is not None else None

    def build_vector(
        self,
        *,
        feature_set_name: str,
        feature_set_version: str,
        values: Mapping[str, FeatureValue],
    ) -> RegisteredFeatureVector:
        registered = self.get_set(feature_set_name, feature_set_version)
        if registered is None:
            raise UnregisteredFeatureError(
                f"feature set non enregistré: {feature_set_name}@{feature_set_version}"
            )
        expected = {definition.name for definition in registered.definitions}
        observed = set(values)
        if missing := sorted(expected - observed):
            raise UnregisteredFeatureError(f"features absentes: {', '.join(missing)}")
        if unexpected := sorted(observed - expected):
            raise UnregisteredFeatureError(f"features non enregistrées: {', '.join(unexpected)}")
        for definition in registered.definitions:
            value = values[definition.name]
            _validate_feature_value(definition.name, value)
            if definition.availability == "required" and value is None:
                raise UnregisteredFeatureError(f"feature requise absente: {definition.name}")
        return RegisteredFeatureVector(
            feature_set_id=registered.feature_set_id,
            feature_set_version=registered.set_version,
            values=MappingProxyType(dict(values)),
            definition_versions=MappingProxyType(
                {
                    definition.name: definition.definition_version
                    for definition in registered.definitions
                }
            ),
        )

    @staticmethod
    def _register_definition(
        connection: Connection,
        specification: FeatureDefinitionSpec,
        created_at: datetime,
    ) -> RegisteredFeatureDefinition:
        definitions = cast(Table, FeatureDefinition.__table__)
        expected_hash = _content_hash(
            {
                "availability": specification.availability,
                "code_version": specification.code_version,
                "definition_version": specification.definition_version,
                "domain": specification.domain,
                "name": specification.name,
                "parameters": dict(specification.parameters),
                "required_capability": specification.required_capability,
            }
        )
        existing = (
            connection.execute(
                select(definitions).where(
                    definitions.c.name == specification.name,
                    definitions.c.definition_version == specification.definition_version,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            if str(existing["definition_hash"]) != expected_hash:
                key = f"{specification.name}@{specification.definition_version}"
                raise FeatureRegistryConflictError(f"feature {key} déjà enregistrée")
            return _registered_definition(existing)

        definition_id = uuid5(
            NAMESPACE_URL,
            f"metiquo:feature-definition:{specification.name}:{specification.definition_version}",
        )
        connection.execute(
            insert(definitions).values(
                id=definition_id,
                name=specification.name,
                domain=specification.domain,
                definition_version=specification.definition_version,
                parameters=dict(specification.parameters),
                availability=specification.availability,
                required_capability=specification.required_capability,
                code_version=specification.code_version,
                definition_hash=expected_hash,
                created_at=created_at,
            )
        )
        row = (
            connection.execute(select(definitions).where(definitions.c.id == definition_id))
            .mappings()
            .one()
        )
        return _registered_definition(row)

    @staticmethod
    def _registered_set(connection: Connection, row: RowMapping) -> RegisteredFeatureSet:
        definitions = cast(Table, FeatureDefinition.__table__)
        members = cast(Table, FeatureSetMember.__table__)
        definition_rows = connection.execute(
            select(definitions)
            .join(members, members.c.feature_definition_id == definitions.c.id)
            .where(members.c.feature_set_id == row["id"])
            .order_by(members.c.position)
        ).mappings()
        return RegisteredFeatureSet(
            feature_set_id=cast(UUID, row["id"]),
            name=str(row["name"]),
            set_version=str(row["set_version"]),
            code_version=str(row["code_version"]),
            set_hash=str(row["set_hash"]),
            definitions=tuple(_registered_definition(item) for item in definition_rows),
            created_at=cast(datetime, row["created_at"]),
        )


def _registered_definition(row: RowMapping) -> RegisteredFeatureDefinition:
    return RegisteredFeatureDefinition(
        definition_id=cast(UUID, row["id"]),
        name=str(row["name"]),
        domain=str(row["domain"]),
        definition_version=str(row["definition_version"]),
        parameters=MappingProxyType(dict(cast(Mapping[str, object], row["parameters"]))),
        availability=cast(FeatureAvailability, row["availability"]),
        required_capability=(
            str(row["required_capability"]) if row["required_capability"] is not None else None
        ),
        code_version=str(row["code_version"]),
        definition_hash=str(row["definition_hash"]),
        created_at=cast(datetime, row["created_at"]),
    )


def _canonical_json(payload: object) -> str:
    try:
        return json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("les paramètres de feature doivent être du JSON déterministe") from error


def _content_hash(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _validate_feature_value(name: str, value: FeatureValue) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise UnregisteredFeatureError(f"feature non finie: {name}")
    if isinstance(value, Decimal) and not value.is_finite():
        raise UnregisteredFeatureError(f"feature non finie: {name}")
    if isinstance(value, str) and not value:
        raise UnregisteredFeatureError(f"feature texte vide: {name}")
