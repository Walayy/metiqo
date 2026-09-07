"""Rapport financier matérialisé depuis le ledger et ses cotes observées."""

import json
from datetime import timedelta
from decimal import Decimal
from importlib import import_module

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from metiquo.db.paper_models import FinancialReportRecord
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.paper.reporting import PostgresFinancialReportingService
from tests.integration.test_paper_clv import observe_quote
from tests.integration.test_paper_creation import _service
from tests.integration.test_paper_ledger import bet_values
from tests.integration.test_paper_settlement_job import arrive_result, settlement_service
from tests.integration.test_postgres_canonical_api import _settings
from tests.integration.test_value_pipeline import _Context
from tests.integration.test_value_pipeline import context as context


@pytest.mark.integration
@pytest.mark.parametrize("context", [False, True], indirect=True)
def test_report_uses_observed_loss_and_keeps_immutable_evidence(
    context: _Context,
    postgresql_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = bet_values(context)
    bet = _service(context).create(
        "entry", values["signal_id"], Decimal(10), "EUR", actor="operator"
    )
    start = context.event.starts_at
    closing_id = observe_quote(
        context, bet, start - timedelta(seconds=30), start - timedelta(seconds=29), odds="10"
    )
    arrival = start + timedelta(hours=1)
    arrive_result(context, arrival, red_won=False)
    settlement_service(context, arrival + timedelta(minutes=6)).settle(bet.paper_bet_id)
    reporter = PostgresFinancialReportingService(
        context.engine, clock=FixedClock(UtcInstant(arrival + timedelta(minutes=10)))
    )
    report = reporter.build(currency="EUR")
    estimates = report.document["estimates"]
    assert isinstance(estimates, dict)
    assert estimates["profit_loss"]["value"] == "-10"
    assert estimates["yield"]["value"] == "-1"
    assert estimates["clv"]["value"] == "-0.2"
    assert estimates["yield_ci_low"]["value"] is None
    assert report.document["bets"] == 1
    assert str(closing_id) in str(report.input_evidence)
    assert reporter.build(currency="EUR").report_id == report.report_id
    assert reporter.latest(currency="EUR") == report
    with context.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(FinancialReportRecord)) == 1
    for command in (
        "UPDATE signals.financial_reports SET currency = 'USD'",
        "DELETE FROM signals.financial_reports",
    ):
        with pytest.raises(DBAPIError, match="append-only"), context.engine.begin() as connection:
            connection.execute(text(command))
    empty = reporter.build(currency="USD")
    assert empty.document["bets"] == 0
    empty_metrics = empty.document["estimates"]
    assert isinstance(empty_metrics, dict) and empty_metrics["yield"]["value"] is None
    cli = import_module("metiquo.cli.main")
    monkeypatch.setattr(cli, "load_settings", lambda: _settings(postgresql_url, "real"))
    assert cli.main(["paper-report", "--currency", "EUR", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["reportId"] == str(report.report_id)
