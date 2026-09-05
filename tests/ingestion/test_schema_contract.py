"""Évolution additive, retraits et capacités ciblées du schéma Oracle's Elixir."""

import csv
from pathlib import Path

import pytest

from metiquo.ingestion.schema_contract import (
    ORACLES_ELIXIR_SCHEMA_V1,
    diff_schemas,
)
from metiquo.ingestion.source_errors import SchemaIncompatible

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "oracles_elixir"


def _fixture(name: str) -> tuple[list[str], list[str]]:
    with (FIXTURES / name).open(newline="") as stream:
        rows = list(csv.reader(stream))
    return rows[0], rows[1]


def test_additive_column_is_preserved_without_breaking_ingestion() -> None:
    header, values = _fixture("schema_additive.csv")

    assessment = ORACLES_ELIXIR_SCHEMA_V1.assess(header)
    raw_row = ORACLES_ELIXIR_SCHEMA_V1.preserve_raw_row(header, values)

    assert assessment.blocking is False
    assert assessment.additive_columns == ("vendor_metric",)
    assert assessment.capability_registry["market.match_winner"] is True
    assert raw_row["vendor_metric"] == "42"
    assert "vendor_metric" in {column.name for column in assessment.schema.columns}


def test_missing_core_column_blocks_ingestion_with_diagnostic() -> None:
    header, _ = _fixture("schema_missing_core.csv")
    assessment = ORACLES_ELIXIR_SCHEMA_V1.assess(header)

    assert assessment.blocking is True
    assert assessment.missing_core_columns == ("gameid",)
    assert all(not capability.enabled for capability in assessment.capabilities)
    with pytest.raises(SchemaIncompatible) as captured:
        ORACLES_ELIXIR_SCHEMA_V1.require_ingestable(
            assessment,
            transport="local-fixture",
            source_id="schema-missing-core",
        )
    assert captured.value.context["rule"] == "SCHEMA_CORE_MISSING"
    assert captured.value.context["missingColumns"] == "gameid"


def test_missing_market_column_disables_only_dependent_capability() -> None:
    header, _ = _fixture("schema_additive.csv")
    without_completeness = [column for column in header if column != "datacompleteness"]

    assessment = ORACLES_ELIXIR_SCHEMA_V1.assess(without_completeness)

    registry = assessment.capability_registry
    assert assessment.blocking is False
    assert registry["market.match_winner"] is False
    assert registry["feature.team_form"] is True
    match_winner = next(
        capability
        for capability in assessment.capabilities
        if capability.capability == "market.match_winner"
    )
    assert match_winner.missing_columns == ("datacompleteness",)


def test_schema_diff_reports_add_remove_type_and_order() -> None:
    header, _ = _fixture("schema_additive.csv")
    previous = ORACLES_ELIXIR_SCHEMA_V1.assess(
        header[:-1], declared_types={"result": "integer"}
    ).schema
    current_header = [
        header[1],
        header[0],
        *(column for column in header[2:-1] if column != "league"),
        "vendor_metric",
    ]
    current = ORACLES_ELIXIR_SCHEMA_V1.assess(
        current_header,
        declared_types={"result": "float", "vendor_metric": "integer"},
    ).schema

    difference = diff_schemas(previous, current)

    assert difference.changed is True
    assert difference.added_columns == ("vendor_metric",)
    assert difference.removed_columns == ("league",)
    assert difference.type_changes == ("result",)
    assert difference.order_changed is True


def test_schema_fingerprint_includes_additive_raw_columns() -> None:
    header, _ = _fixture("schema_additive.csv")
    with_additive = ORACLES_ELIXIR_SCHEMA_V1.assess(header).schema
    without_additive = ORACLES_ELIXIR_SCHEMA_V1.assess(header[:-1]).schema

    assert with_additive.fingerprint != without_additive.fingerprint
