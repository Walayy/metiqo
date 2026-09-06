"""Arrivée OE, délai, replay et reprises du job de règlement PostgreSQL."""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from importlib import import_module
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from metiquo.canonical.games import CanonicalGameBuilder
from metiquo.contracts.enums import PaperBetStatus as Status
from metiquo.db.core_models import Game
from metiquo.db.paper_models import PaperSettlementRecord
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot, SourceCatalog
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.paper.settlement_job import PostgresPaperSettlementService
from tests.integration.test_paper_creation import _service
from tests.integration.test_paper_ledger import bet_values
from tests.integration.test_postgres_canonical_api import _settings
from tests.integration.test_value_pipeline import _SLA, _Context
from tests.integration.test_value_pipeline import context as context


def arrive_result(context: _Context, arrived_at: datetime, *, red_won: bool = True) -> UUID:
    """Fixture de publication raw suivie du vrai builder et de ses révisions core."""
    with Session(context.engine) as session:
        game = session.get(Game, context.event.event_id)
        assert game is not None
        original = session.get(Snapshot, game.source_snapshot_id)
        assert original is not None
        catalog = session.get(SourceCatalog, original.source_catalog_id)
        assert catalog is not None
        dataset = catalog.dataset
        rows = session.scalars(select(CanonicalRow).where(CanonicalRow.dataset == dataset)).all()
        snapshot_id, run_id = uuid4(), uuid4()
        source = {c.name: getattr(original, c.name) for c in Snapshot.__table__.columns} | {
            "id": snapshot_id,
            "sha256": sha256(str(snapshot_id).encode()).hexdigest(),
            "object_key": f"paper-arrival/{snapshot_id}/source.csv",
            "received_at": arrived_at,
            "validated_at": arrived_at,
            "created_at": arrived_at,
        }
        with context.engine.begin() as connection:
            connection.execute(insert(Snapshot).values(**source))
            connection.execute(
                insert(IngestionRun).values(
                    id=run_id,
                    source_catalog_id=catalog.id,
                    snapshot_id=snapshot_id,
                    run_kind="load",
                    status="succeeded",
                    attempt=1,
                    transport="fixture",
                    correlation_id=f"arrival-{run_id}",
                    started_at=arrived_at,
                    finished_at=arrived_at,
                    created_at=arrived_at,
                    counters={},
                )
            )
            for row in rows:
                payload = dict(row.payload)
                if payload["gameid"] == game.source_game_id:
                    payload["result"] = "1" if (payload["side"] == "Red") == red_won else "0"
                connection.execute(
                    update(CanonicalRow)
                    .where(CanonicalRow.id == row.id)
                    .values(
                        payload=payload,
                        row_hash=sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
                        revision=row.revision + 1,
                        source_snapshot_id=snapshot_id,
                        source_run_id=run_id,
                        updated_at=arrived_at,
                    )
                )
            connection.execute(
                update(SourceCatalog)
                .where(SourceCatalog.id == catalog.id)
                .values(current_snapshot_id=snapshot_id)
            )
    CanonicalGameBuilder(engine=context.engine, clock=FixedClock(UtcInstant(arrived_at))).build(
        dataset=dataset
    )
    return snapshot_id


def settlement_service(
    context: _Context, now: datetime, *, sla: timedelta = _SLA
) -> PostgresPaperSettlementService:
    return PostgresPaperSettlementService(
        context.engine,
        source_sla=sla,
        settlement_delay=timedelta(minutes=5),
        clock=FixedClock(UtcInstant(now)),
    )


@pytest.mark.integration
def test_result_arrival_delay_and_audited_correction(context: _Context) -> None:
    values = bet_values(context)
    bet = _service(context).create(
        "entry", values["signal_id"], Decimal(10), "EUR", actor="operator"
    )
    arrival = context.event.starts_at + timedelta(hours=1)
    waiting = settlement_service(context, arrival).settle(bet.paper_bet_id)
    assert waiting.status is Status.PENDING_REVIEW
    assert waiting.profit_loss is None
    source_id = arrive_result(context, arrival)
    assert (
        settlement_service(context, arrival + timedelta(minutes=1)).settle(bet.paper_bet_id).status
        is Status.PENDING_REVIEW
    )
    service = settlement_service(context, arrival + timedelta(minutes=6))
    won = service.settle(bet.paper_bet_id)
    assert won.status is Status.WON and won.profit_loss == 70
    assert service.settle(bet.paper_bet_id) == won
    with context.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(PaperSettlementRecord)) == 3
        assert (
            connection.execute(
                select(PaperSettlementRecord.result_snapshot_id)
                .order_by(PaperSettlementRecord.revision.desc())
                .limit(1)
            ).scalar_one()
            == source_id
        )
    arrive_result(context, arrival + timedelta(minutes=10), red_won=False)
    correction = settlement_service(context, arrival + timedelta(minutes=16))
    assert correction.settle(bet.paper_bet_id) == won
    lost = correction.settle(
        bet.paper_bet_id,
        key="correction-one",
        actor="reviewer",
        correction_reason="OE result correction verified",
    )
    assert lost.status is Status.LOST and lost.profit_loss == -10
    with context.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(PaperSettlementRecord)) == 4


@pytest.mark.integration
def test_stale_source_keeps_result_pending(context: _Context) -> None:
    values = bet_values(context)
    bet = _service(context).create(
        "entry", values["signal_id"], Decimal(10), "EUR", actor="operator"
    )
    arrival = context.event.starts_at + timedelta(hours=1)
    arrive_result(context, arrival)
    result = settlement_service(
        context, arrival + timedelta(hours=2), sla=timedelta(hours=1)
    ).settle(bet.paper_bet_id)
    assert result.status is Status.PENDING_REVIEW
    assert result.settlement_reason == "SOURCE_STALE"


@pytest.mark.integration
@pytest.mark.parametrize("recover", [True, False])
def test_job_transient_retries_are_bounded(
    context: _Context, monkeypatch: pytest.MonkeyPatch, recover: bool
) -> None:
    values = bet_values(context)
    bet = _service(context).create(
        "entry", values["signal_id"], Decimal(10), "EUR", actor="operator"
    )
    arrival = context.event.starts_at + timedelta(hours=1)
    arrive_result(context, arrival)
    service = settlement_service(context, arrival + timedelta(minutes=6))
    original = service.settle
    attempts = 0
    sleeps: list[float] = []

    def transient(paper_bet_id: UUID) -> object:
        nonlocal attempts
        attempts += 1
        if not recover or attempts < 3:
            raise OperationalError(
                "test transient", {}, Exception("disconnected"), connection_invalidated=True
            )
        return original(paper_bet_id)

    monkeypatch.setattr(service, "settle", transient)
    monkeypatch.setattr(service, "sleep", sleeps.append)
    report = service.run_pending(max_attempts=3)
    assert attempts == 3 and len(sleeps) == 2
    assert report.settled == (1 if recover else 0)
    assert report.failed == (() if recover else (bet.paper_bet_id,))


@pytest.mark.integration
def test_settlement_cli_runs_the_pending_batch(
    context: _Context,
    postgresql_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = import_module("metiquo.cli.main")
    module = import_module("metiquo.paper.settlement_job")
    values = bet_values(context)
    _service(context).create("entry", values["signal_id"], Decimal(10), "EUR", actor="operator")
    arrival = context.event.starts_at + timedelta(hours=1)
    arrive_result(context, arrival)
    settings = _settings(postgresql_url, "real").model_copy(
        update={"oe_freshness_sla_seconds": int(_SLA.total_seconds())}
    )
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(
        module, "SystemClock", lambda: FixedClock(UtcInstant(arrival + timedelta(minutes=6)))
    )
    assert cli.main(["paper-settle", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["settled"] == 1
    assert cli.main(["paper-settle", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["processed"] == 0
