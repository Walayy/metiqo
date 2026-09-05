"""États fermés par défaut du registre de capacités par snapshot."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, Table, create_engine, func, insert, select, update

from metiquo.canonical.capabilities import (
    CapabilityDefinition,
    CapabilityRegistry,
    CapabilityState,
    MarketGateEvidence,
)
from metiquo.db.core_models import CapabilityEvaluation
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot, SourceCatalog
from metiquo.foundation.time import FixedClock, UtcInstant

_ROOT = Path(__file__).resolve().parents[2]
_NOW = datetime(2026, 9, 6, 12, 30, tzinfo=UTC)
_DEFINITIONS = (
    CapabilityDefinition(
        "label.match_winner",
        "label",
        ("datacompleteness", "result"),
        Decimal("0"),
        0,
        "test-thresholds-v1",
    ),
    CapabilityDefinition(
        "feature.early_game",
        "feature",
        ("golddiffat15",),
        Decimal("0"),
        0,
        "test-thresholds-v1",
    ),
    CapabilityDefinition(
        "market.match_winner",
        "market",
        ("datacompleteness", "result"),
        Decimal("0"),
        0,
        "test-thresholds-v1",
    ),
)


def _alembic_config(url: str) -> Config:
    config = Config(_ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


@pytest.mark.integration
def test_market_requires_every_gate_and_keeps_versioned_evaluations(
    postgresql_url: str,
) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    dataset = f"cnl_006_{uuid4().hex}"
    snapshot_id = _seed_snapshot(engine, dataset)
    registry = CapabilityRegistry(
        engine=engine,
        clock=FixedClock(UtcInstant(_NOW)),
        definitions=_DEFINITIONS,
    )

    pending = _by_name(registry.evaluate_snapshot(snapshot_id=snapshot_id))
    assert pending["label.match_winner"].status == "enabled"
    assert pending["feature.early_game"].status == "disabled"
    assert pending["feature.early_game"].reason_codes == ("MISSING_COLUMNS:golddiffat15",)
    market = pending["market.match_winner"]
    assert market.status == "pending"
    assert set(market.gates) == {
        "label",
        "data",
        "rules",
        "model",
        "calibration",
        "mapping",
        "odds",
        "sample",
    }
    assert market.gates["model"] is None
    assert market.gates["odds"] is None

    # L'évaluation identique reste idempotente.
    registry.evaluate_snapshot(snapshot_id=snapshot_id)
    assert _evaluation_count(engine, snapshot_id) == 3

    enabled_evidence = MarketGateEvidence(
        settlement_rules=True,
        model_validated=True,
        calibration_acceptable=True,
        mapping_stable=True,
        odds_fresh=True,
    )
    enabled = _by_name(
        registry.evaluate_snapshot(
            snapshot_id=snapshot_id,
            market_evidence={"market.match_winner": enabled_evidence},
        )
    )["market.match_winner"]
    assert enabled.status == "enabled"
    assert enabled.evaluation_revision == 2
    assert all(value is True for value in enabled.gates.values())

    for rejected_evidence in (
        MarketGateEvidence(False, True, True, True, True),
        MarketGateEvidence(True, False, True, True, True),
        MarketGateEvidence(True, True, False, True, True),
        MarketGateEvidence(True, True, True, False, True),
        MarketGateEvidence(True, True, True, True, False),
    ):
        rejected = _by_name(
            registry.evaluate_snapshot(
                snapshot_id=snapshot_id,
                market_evidence={"market.match_winner": rejected_evidence},
            )
        )["market.match_winner"]
        assert rejected.status == "disabled"
        assert any(reason.endswith("_FAILED") for reason in rejected.reason_codes)

    strict_registry = CapabilityRegistry(
        engine=engine,
        clock=FixedClock(UtcInstant(_NOW)),
        definitions=(
            CapabilityDefinition(
                "label.match_winner",
                "label",
                ("datacompleteness", "result"),
                Decimal("0.9500"),
                1,
                "test-thresholds-strict-v2",
            ),
            CapabilityDefinition(
                "market.match_winner",
                "market",
                ("datacompleteness", "result"),
                Decimal("0.9500"),
                1,
                "test-thresholds-strict-v2",
            ),
        ),
    )
    strict_market = _by_name(
        strict_registry.evaluate_snapshot(
            snapshot_id=snapshot_id,
            market_evidence={"market.match_winner": enabled_evidence},
        )
    )["market.match_winner"]
    assert strict_market.status == "disabled"
    assert strict_market.gates["label"] is False
    assert strict_market.gates["data"] is False
    assert strict_market.gates["sample"] is False
    assert {"INSUFFICIENT_COMPLETENESS", "INSUFFICIENT_SAMPLE", "LABEL_UNAVAILABLE"}.issubset(
        strict_market.reason_codes
    )
    engine.dispose()


def _seed_snapshot(engine: Engine, dataset: str) -> UUID:
    catalog_id = uuid4()
    snapshot_id = uuid4()
    run_id = uuid4()
    catalog = cast(Table, SourceCatalog.__table__)
    snapshots = cast(Table, Snapshot.__table__)
    runs = cast(Table, IngestionRun.__table__)
    raw = cast(Table, CanonicalRow.__table__)
    payload = {
        "gameid": "CAP-1",
        "date": "2026-08-01",
        "participantid": "100",
        "side": "Blue",
        "position": "team",
        "teamname": "Blue",
        "league": "Capability League",
        "datacompleteness": "complete",
        "result": "1",
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with engine.begin() as connection:
        connection.execute(
            insert(catalog).values(
                id=catalog_id,
                created_at=_NOW,
                updated_at=_NOW,
                provider="oracles_elixir",
                dataset=dataset,
                season_year=2192,
                landing_page="https://oracleselixir.com/tools/downloads",
                drive_file_id=f"drive-{dataset}",
                source_name="2192_LoL_esports_match_data.csv.gz",
                source_modified_at=_NOW,
                source_size=100,
                origin="discovered",
                status="active",
                discovered_at=_NOW,
                last_confirmed_at=_NOW,
                mutable=False,
            )
        )
        connection.execute(
            insert(snapshots).values(
                id=snapshot_id,
                source_catalog_id=catalog_id,
                year=2192,
                source_file_id=f"drive-{dataset}",
                status="validated",
                sha256=hashlib.sha256(f"snapshot-{snapshot_id}".encode()).hexdigest(),
                byte_size=100,
                content_type="text/csv",
                object_key=f"capability/{snapshot_id}/source.csv",
                received_at=_NOW,
                validated_at=_NOW,
                manifest={},
                created_at=_NOW,
            )
        )
        connection.execute(
            insert(runs).values(
                id=run_id,
                source_catalog_id=catalog_id,
                snapshot_id=snapshot_id,
                run_kind="load",
                status="succeeded",
                attempt=1,
                transport="fixture",
                correlation_id=f"cnl-006-{run_id}",
                started_at=_NOW,
                finished_at=_NOW,
                counters={},
                created_at=_NOW,
            )
        )
        connection.execute(
            insert(raw).values(
                id=uuid4(),
                provider="oracles_elixir",
                dataset=dataset,
                natural_key='["CAP-1","100"]',
                row_hash=hashlib.sha256(serialized.encode()).hexdigest(),
                payload=payload,
                source_snapshot_id=snapshot_id,
                source_run_id=run_id,
                revision=1,
                created_at=_NOW,
                updated_at=_NOW,
            )
        )
        connection.execute(
            update(catalog)
            .where(catalog.c.id == catalog_id)
            .values(current_snapshot_id=snapshot_id)
        )
    return snapshot_id


def _by_name(states: tuple[CapabilityState, ...]) -> dict[str, CapabilityState]:
    return {state.capability: state for state in states}


def _evaluation_count(engine: Engine, snapshot_id: UUID) -> int:
    with engine.connect() as connection:
        return int(
            connection.scalar(
                select(func.count())
                .select_from(CapabilityEvaluation)
                .where(CapabilityEvaluation.snapshot_id == snapshot_id)
            )
            or 0
        )
