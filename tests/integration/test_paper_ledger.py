"""Contraintes physiques du ledger, sans passer par un service applicatif."""

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from metiquo.db.feature_models import FeatureSnapshot
from metiquo.db.odds_models import MarketMappingAttempt, OddsSnapshotRecord
from metiquo.db.paper_models import PaperBetRecord, PaperSettlementRecord
from metiquo.db.raw_models import Snapshot
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.services.value_pipeline import PostgresValuePipeline
from tests.integration.test_value_pipeline import _SLA, _capture, _Context
from tests.integration.test_value_pipeline import context as context


def bet_values(context: _Context) -> dict[str, Any]:
    request = _capture(context)
    now = context.captured_at + timedelta(seconds=10)
    evaluated = PostgresValuePipeline(
        context.engine, source_sla=_SLA, clock=FixedClock(UtcInstant(now))
    ).evaluate(request)
    assert evaluated.signal is not None
    with Session(context.engine) as session:
        mapping = session.get(MarketMappingAttempt, request.market_mapping_attempt_id)
        assert mapping is not None
        return {
            "id": uuid4(),
            "signal_id": evaluated.signal.signal_id,
            "value_evaluation_id": evaluated.evaluation_id,
            "prediction_id": context.prediction.prediction_id,
            "odds_snapshot_id": request.odds_snapshot_id,
            "model_version_id": context.prediction.model_version_id,
            "policy_version": request.policy_version,
            "settlement_rules_version": mapping.rules_reference,
            "entry_odds": Decimal(8),
            "stake_amount": Decimal(10),
            "currency": "EUR",
            "placed_at": now + timedelta(seconds=1),
            "actor": "paper-fixture",
            "decision_evidence": {"mode": "paper", "fixture": True},
            "idempotency_fingerprint": "1" * 64,
            "request_fingerprint": "2" * 64,
        }


@pytest.mark.integration
def test_paper_decision_requires_exact_timestamped_evidence(context: _Context) -> None:
    values = bet_values(context)
    with Session(context.engine) as session:
        snapshot = session.get(OddsSnapshotRecord, values["odds_snapshot_id"])
        assert snapshot is not None
        unreliable = {
            column.name: getattr(snapshot, column.name)
            for column in OddsSnapshotRecord.__table__.columns
        }
    unreliable.update(
        id=uuid4(),
        captured_at=None,
        timestamp_reliable=False,
        informational_only=True,
        observation_fingerprint="a" * 64,
    )
    with context.engine.begin() as connection:
        connection.execute(insert(OddsSnapshotRecord).values(**unreliable))
    for changed, error in (
        ({"entry_odds": Decimal(12)}, "does not match"),
        ({"odds_snapshot_id": unreliable["id"]}, "timestamped"),
        ({"placed_at": context.event.starts_at}, "precede event"),
        ({"stake_amount": Decimal("NaN")}, "stake"),
    ):
        with pytest.raises(DBAPIError, match=error), context.engine.begin() as connection:
            connection.execute(insert(PaperBetRecord).values(**(values | changed)))
    with context.engine.begin() as connection:
        connection.execute(insert(PaperBetRecord).values(**values))
    for mutation in (
        "UPDATE signals.paper_bets SET stake_amount = 1",
        "DELETE FROM signals.paper_bets",
        "UPDATE signals.signals SET grade = 'BLOCKED'",
    ):
        with pytest.raises(DBAPIError, match="append-only"), context.engine.begin() as connection:
            connection.execute(text(mutation))
    with context.engine.connect() as connection:
        persisted = connection.execute(select(PaperBetRecord.__table__)).mappings().one()
        assert persisted["stake_amount"] == 10
        assert persisted["odds_snapshot_id"] == values["odds_snapshot_id"]


@pytest.mark.integration
def test_settlement_revisions_preserve_losses_and_require_known_source(context: _Context) -> None:
    values = bet_values(context)
    with context.engine.begin() as connection:
        connection.execute(insert(PaperBetRecord).values(**values))
    with Session(context.engine) as session:
        feature = session.get(FeatureSnapshot, context.prediction.feature_snapshot_id)
        assert feature is not None
        snapshot_id = feature.target_oe_snapshot_id
        source = session.get(Snapshot, snapshot_id)
        assert source is not None
        rejected_source = {
            column.name: getattr(source, column.name) for column in Snapshot.__table__.columns
        } | {
            "id": uuid4(),
            "status": "quarantined",
            "validated_at": None,
            "sha256": "b" * 64,
            "object_key": "paper-fixture/quarantined",
            "failure_reason": "Rejected fixture",
        }
    with context.engine.begin() as connection:
        connection.execute(insert(Snapshot).values(**rejected_source))
    pending: dict[str, Any] = {
        "id": uuid4(),
        "paper_bet_id": values["id"],
        "revision": 1,
        "supersedes_id": None,
        "status": "pending_review",
        "profit_loss": None,
        "result_snapshot_id": None,
        "settlement_rules_version": values["settlement_rules_version"],
        "occurred_at": context.event.starts_at + timedelta(hours=2),
        "actor": "settlement-fixture",
        "reason": "Awaiting validated OE result",
        "evidence": {"fixture": True},
        "idempotency_fingerprint": "3" * 64,
        "request_fingerprint": "4" * 64,
    }
    with context.engine.begin() as connection:
        connection.execute(insert(PaperSettlementRecord).values(**pending))
    loss = pending | {
        "id": uuid4(),
        "revision": 2,
        "supersedes_id": pending["id"],
        "status": "lost",
        "profit_loss": Decimal(-10),
        "result_snapshot_id": snapshot_id,
        "reason": "Validated result",
        "idempotency_fingerprint": "5" * 64,
    }
    for changes in (
        {"profit_loss": Decimal(70)},
        {"revision": 3},
        {"supersedes_id": None},
        {"result_snapshot_id": None},
        {"result_snapshot_id": rejected_source["id"]},
    ):
        with pytest.raises(DBAPIError), context.engine.begin() as connection:
            connection.execute(insert(PaperSettlementRecord).values(**(loss | changes)))
    with context.engine.begin() as connection:
        connection.execute(insert(PaperSettlementRecord).values(**loss))
        connection.execute(
            insert(PaperSettlementRecord).values(
                **(
                    loss
                    | {
                        "id": uuid4(),
                        "revision": 3,
                        "supersedes_id": loss["id"],
                        "status": "won",
                        "profit_loss": Decimal(70),
                        "reason": "Explicit audited fixture correction",
                        "actor": "reviewer",
                        "idempotency_fingerprint": "6" * 64,
                    }
                )
            )
        )
    for mutation in (
        "UPDATE signals.settlements SET profit_loss = 100",
        "DELETE FROM signals.settlements",
    ):
        with pytest.raises(DBAPIError, match="append-only"), context.engine.begin() as connection:
            connection.execute(text(mutation))
    with context.engine.connect() as connection:
        rows = connection.execute(
            select(PaperSettlementRecord.status, PaperSettlementRecord.profit_loss).order_by(
                PaperSettlementRecord.revision
            )
        ).all()
        assert [(row[0], row[1]) for row in rows] == [
            ("pending_review", None),
            ("lost", Decimal(-10)),
            ("won", Decimal(70)),
        ]
