"""Registre versionné et fermé des définitions de features."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from metiquo.features import (
    FeatureDefinitionSpec,
    FeatureRegistry,
    FeatureRegistryConflictError,
    FeatureSetSpec,
    UnregisteredFeatureError,
)
from metiquo.foundation.time import FixedClock, UtcInstant
from tests.integration.test_migrations import alembic_config

_NOW = datetime(2026, 9, 6, 14, 0, tzinfo=UTC)


def _set_spec(*, half_life: int = 30) -> FeatureSetSpec:
    return FeatureSetSpec(
        name="lol.match_winner.pregame",
        set_version="lol-match-winner-v1",
        code_version="feat-registry-v1",
        definitions=(
            FeatureDefinitionSpec(
                name="rating.team_a",
                domain="rating",
                definition_version="elo-pregame-v1",
                parameters={"half_life_days": half_life, "initial": 1500},
                availability="required",
                code_version="rating-v1",
            ),
            FeatureDefinitionSpec(
                name="roster.confidence_a",
                domain="roster",
                definition_version="roster-confidence-v1",
                parameters={"roles": 5},
                availability="capability_gated",
                required_capability="feature.roster",
                code_version="roster-v1",
            ),
            FeatureDefinitionSpec(
                name="context.patch",
                domain="context",
                definition_version="patch-known-v1",
                parameters={"unknown_value": "unknown"},
                availability="optional",
                code_version="context-v1",
            ),
        ),
    )


@pytest.mark.integration
def test_feature_registry_is_versioned_idempotent_and_rejects_ad_hoc_columns(
    postgresql_url: str,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    registry = FeatureRegistry(engine=engine, clock=FixedClock(UtcInstant(_NOW)))

    first = registry.register_set(_set_spec())
    second = registry.register_set(_set_spec())

    assert first == second
    assert first.set_version == "lol-match-winner-v1"
    assert len(first.set_hash) == 64
    assert [definition.name for definition in first.definitions] == [
        "rating.team_a",
        "roster.confidence_a",
        "context.patch",
    ]
    assert {definition.code_version for definition in first.definitions} == {
        "rating-v1",
        "roster-v1",
        "context-v1",
    }
    assert all(len(definition.definition_hash) == 64 for definition in first.definitions)
    assert registry.get_set(first.name, first.set_version) == first
    assert registry.get_definition("rating.team_a", "elo-pregame-v1") == first.definitions[0]

    vector = registry.build_vector(
        feature_set_name=first.name,
        feature_set_version=first.set_version,
        values={
            "rating.team_a": Decimal("1512.5"),
            "roster.confidence_a": None,
            "context.patch": "unknown",
        },
    )
    assert vector.feature_set_id == first.feature_set_id
    assert vector.definition_versions == {
        "rating.team_a": "elo-pregame-v1",
        "roster.confidence_a": "roster-confidence-v1",
        "context.patch": "patch-known-v1",
    }

    with pytest.raises(UnregisteredFeatureError, match="features absentes"):
        registry.build_vector(
            feature_set_name=first.name,
            feature_set_version=first.set_version,
            values={"rating.team_a": 1500},
        )
    with pytest.raises(UnregisteredFeatureError, match="non enregistrées"):
        registry.build_vector(
            feature_set_name=first.name,
            feature_set_version=first.set_version,
            values={
                "rating.team_a": 1500,
                "roster.confidence_a": None,
                "context.patch": "unknown",
                "future.result": 1,
            },
        )
    with pytest.raises(UnregisteredFeatureError, match="feature requise absente"):
        registry.build_vector(
            feature_set_name=first.name,
            feature_set_version=first.set_version,
            values={
                "rating.team_a": None,
                "roster.confidence_a": None,
                "context.patch": "unknown",
            },
        )
    with pytest.raises(FeatureRegistryConflictError, match="déjà enregistrée"):
        registry.register_set(_set_spec(half_life=60))

    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM features.feature_sets WHERE id = :set_id"),
                {"set_id": first.feature_set_id},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM features.feature_definitions d "
                    "JOIN features.feature_set_members m ON m.feature_definition_id = d.id "
                    "WHERE m.feature_set_id = :set_id"
                ),
                {"set_id": first.feature_set_id},
            ).scalar_one()
            == 3
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM features.feature_set_members "
                    "WHERE feature_set_id = :set_id"
                ),
                {"set_id": first.feature_set_id},
            ).scalar_one()
            == 3
        )
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(text("UPDATE features.feature_sets SET code_version = 'rewritten'"))
    engine.dispose()


def test_feature_specs_require_explicit_versions_availability_and_unique_names() -> None:
    with pytest.raises(ValueError, match="nom de feature non normalisé"):
        FeatureDefinitionSpec(
            name="Ad hoc column",
            domain="rating",
            definition_version="v1",
            parameters={},
            availability="required",
            code_version="code-v1",
        )
    with pytest.raises(ValueError, match="exige sa capacité"):
        FeatureDefinitionSpec(
            name="roster.confidence",
            domain="roster",
            definition_version="v1",
            parameters={},
            availability="capability_gated",
            code_version="code-v1",
        )
    definition = FeatureDefinitionSpec(
        name="rating.team_a",
        domain="rating",
        definition_version="v1",
        parameters={},
        availability="required",
        code_version="code-v1",
    )
    with pytest.raises(ValueError, match="deux fois"):
        FeatureSetSpec(
            name="duplicate",
            set_version="v1",
            code_version="code-v1",
            definitions=(definition, definition),
        )
