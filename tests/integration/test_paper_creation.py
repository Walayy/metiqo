"""Création fictive : admissibilité courante, idempotence et concurrence bankroll."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from importlib import import_module
from uuid import UUID

import pytest
from sqlalchemy import func, select, text

from metiquo.contracts.enums import DataMode, PaperBetStatus
from metiquo.db.paper_models import PaperBetRecord
from metiquo.db.pricing_models import ValueEvaluationRecord
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.paper.creation import PaperBankrollPolicy, PostgresPaperService
from tests.integration.test_paper_ledger import bet_values
from tests.integration.test_postgres_canonical_api import _settings
from tests.integration.test_value_pipeline import _SLA, _Context
from tests.integration.test_value_pipeline import context as context


def _service(context: _Context, *, delay: int = 20, limit: str = "100") -> PostgresPaperService:
    return PostgresPaperService(
        context.engine,
        bankroll=PaperBankrollPolicy("paper-fixture-v1", "EUR", Decimal(100), Decimal(limit)),
        source_sla=_SLA,
        clock=FixedClock(UtcInstant(context.captured_at + timedelta(seconds=delay))),
    )


@pytest.mark.integration
def test_paper_creation_replays_and_rejects_conflicting_keys(context: _Context) -> None:
    values = bet_values(context)
    service = _service(context)
    bet = service.create("entry-one", values["signal_id"], Decimal(10), "EUR", actor="operator")
    assert bet.status is PaperBetStatus.OPEN
    assert bet.entry_odds == 8
    assert bet.odds_snapshot_id == values["odds_snapshot_id"]
    assert bet == _service(context, delay=7200).create(
        "entry-one", values["signal_id"], Decimal("10.00"), "EUR", actor="operator"
    )
    for key, amount in (("entry-one", Decimal(11)), ("another-key", Decimal(10))):
        with pytest.raises(BusinessError) as error:
            service.create(key, values["signal_id"], amount, "EUR", actor="operator")
        assert error.value.code is ErrorCode.CONFLICT
    with context.engine.connect() as connection:
        stored = connection.execute(select(PaperBetRecord.__table__)).mappings().one()
        assert stored["decision_evidence"]["mode"] == "paper"
        assert stored["decision_evidence"]["entryEvaluationId"]
        assert stored["decision_evidence"]["availableBefore"] == "100"


@pytest.mark.integration
@pytest.mark.parametrize("changed", ["stale", "retired", "currency", "funds"])
def test_paper_creation_refuses_unsafe_entry_atomically(context: _Context, changed: str) -> None:
    values = bet_values(context)
    service = _service(context, delay=200 if changed == "stale" else 20)
    if changed == "retired":
        with context.engine.begin() as connection:
            connection.execute(text("UPDATE ml.model_versions SET status = 'retired'"))
    with context.engine.connect() as connection:
        evaluations_before = connection.scalar(
            select(func.count()).select_from(ValueEvaluationRecord)
        )
    with pytest.raises(BusinessError):
        service.create(
            "refused",
            values["signal_id"],
            Decimal(101) if changed == "funds" else Decimal(10),
            "USD" if changed == "currency" else "EUR",
            actor="operator",
        )
    with context.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(PaperBetRecord)) == 0
        assert (
            connection.scalar(select(func.count()).select_from(ValueEvaluationRecord))
            == evaluations_before
        )


@pytest.mark.integration
def test_concurrent_entries_cannot_overdraw_fictitious_bankroll(context: _Context) -> None:
    first, second = bet_values(context), bet_values(context)
    service = _service(context, limit="10")

    def enter(signal_id: UUID) -> bool:
        try:
            service.create(str(signal_id), signal_id, Decimal(8), "EUR", actor="operator")
            return True
        except BusinessError as error:
            assert error.code is ErrorCode.INVALID_STATE
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(enter, (first["signal_id"], second["signal_id"]))) == [False, True]
    with context.engine.connect() as connection:
        assert connection.scalar(select(func.sum(PaperBetRecord.stake_amount))) == 8


@pytest.mark.integration
def test_paper_cli_uses_real_ledger_and_returns_business_refusals(
    context: _Context,
    postgresql_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import metiquo.paper.creation as creation

    cli = import_module("metiquo.cli.main")
    values = bet_values(context)
    settings = _settings(postgresql_url, DataMode.REAL).model_copy(
        update={"oe_freshness_sla_seconds": int(_SLA.total_seconds())}
    )
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(
        creation,
        "SystemClock",
        lambda: FixedClock(UtcInstant(context.captured_at + timedelta(seconds=20))),
    )
    arguments = [
        "paper-create",
        "--signal",
        str(values["signal_id"]),
        "--stake",
        "10",
        "--currency",
        "EUR",
        "--idempotency-key",
        "cli-entry",
        "--actor",
        "operator",
        "--json",
    ]
    assert cli.main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["paperBet"]["status"] == "open"
    assert result["paperBet"]["signalId"] == str(values["signal_id"])
    arguments[4] = "11"
    assert cli.main(arguments) == 2
    assert "CONFLICT" in capsys.readouterr().err
