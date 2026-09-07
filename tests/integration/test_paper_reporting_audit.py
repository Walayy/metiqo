"""Le rapport conserve abstentions, entrées non prises et pertes corrigées."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from metiquo.db.paper_models import FinancialReportRecord, PaperBetRecord
from metiquo.foundation.errors import BusinessError
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.paper.creation import entry_dto
from metiquo.paper.reporting import PostgresFinancialReportingService
from metiquo.services.value_pipeline import PostgresValuePipeline
from tests.integration.test_paper_clv import observe_quote
from tests.integration.test_paper_creation import _service
from tests.integration.test_paper_ledger import bet_values
from tests.integration.test_paper_settlement_job import arrive_result, settlement_service
from tests.integration.test_value_pipeline import _SLA, _capture, _Context
from tests.integration.test_value_pipeline import context as context


@pytest.mark.integration
def test_report_preserves_untaken_signals_and_the_full_correction_chain(context: _Context) -> None:
    taken, untaken = bet_values(context), bet_values(context)
    early = PostgresValuePipeline(
        context.engine,
        source_sla=_SLA,
        clock=FixedClock(UtcInstant(context.captured_at + timedelta(seconds=10))),
    ).evaluate(_capture(context, ambiguous=True))
    assert early.signal is None
    bet = _service(context).create(
        "entry", taken["signal_id"], Decimal(10), "EUR", actor="operator"
    )
    start = context.event.starts_at
    closing_id = observe_quote(
        context, bet, start - timedelta(seconds=30), start - timedelta(seconds=29), odds="4"
    )
    arrival = start + timedelta(hours=1)
    arrive_result(context, arrival, red_won=False)
    settlement_service(context, arrival + timedelta(minutes=6)).settle(bet.paper_bet_id)
    before = PostgresFinancialReportingService(
        context.engine, clock=FixedClock(UtcInstant(arrival + timedelta(minutes=7)))
    ).build(currency="EUR")
    audit = before.document["audit"]
    assert isinstance(audit, dict)
    dispositions = {s["signalId"]: s["paperDisposition"] for s in audit["signals"]}
    assert dispositions[str(taken["signal_id"])] == "taken"
    assert dispositions[str(untaken["signal_id"])] == "not_taken"
    assert list(dispositions.values()).count("entry_recheck") == 1
    assert len(audit["earlyAbstentions"]) == 1
    assert audit["earlyAbstentions"][0]["evaluationId"] == str(early.evaluation_id)
    assert audit["entries"][0]["slippageRatio"] == "0"
    assert audit["entries"][0]["slippageMethod"] == "exact-signal-snapshot-v1"
    assert str(closing_id) in str(audit["oddsHistory"])
    assert all(p["tunedThrough"] < p["finalTestStartsAt"] for p in audit["policies"])
    assert audit["policyChanges"][0]["actor"]

    arrive_result(context, arrival + timedelta(minutes=10), red_won=True)
    settlement_service(context, arrival + timedelta(minutes=16)).settle(
        bet.paper_bet_id, key="correction", actor="reviewer", correction_reason="OE correction"
    )
    reporter = PostgresFinancialReportingService(
        context.engine, clock=FixedClock(UtcInstant(arrival + timedelta(minutes=17)))
    )
    after = reporter.build(currency="EUR")
    assert after.report_id != before.report_id
    after_audit = after.document["audit"]
    assert isinstance(after_audit, dict)
    revisions = after_audit["settlementHistory"]
    assert [r["profitLoss"] for r in revisions] == ["-10", "70"]
    assert [r["profitLossAdjustment"] for r in revisions] == ["-10", "80"]
    assert revisions[-1]["actor"] == "reviewer"
    assert revisions[-1]["reason"] == "OE correction"
    assert revisions[-1]["supersedesId"] == revisions[0]["settlementId"]
    estimates = after.document["estimates"]
    assert isinstance(estimates, dict)
    assert estimates["profit_loss"]["value"] == "70"
    assert reporter.build(currency="EUR") == after
    with Session(context.engine) as session:
        old = session.scalar(
            select(FinancialReportRecord).where(FinancialReportRecord.id == before.report_id)
        )
        assert old is not None and old.document == before.document
    for table in ("signals", "value_evaluations", "settlements", "financial_reports"):
        with pytest.raises(DBAPIError, match="append-only"), context.engine.begin() as connection:
            connection.execute(text(f"DELETE FROM signals.{table}"))


@pytest.mark.integration
def test_changed_quote_refuses_old_entry_and_preserves_the_missed_opportunity(
    context: _Context,
) -> None:
    values = bet_values(context)
    proposal = entry_dto(PaperBetRecord(**values))
    changed = observe_quote(
        context,
        proposal,
        context.captured_at + timedelta(seconds=12),
        context.captured_at + timedelta(seconds=13),
        odds="4",
    )
    with pytest.raises(BusinessError, match="plus admissible"):
        _service(context).create(
            "stale-entry", values["signal_id"], Decimal(10), "EUR", actor="operator"
        )
    report = PostgresFinancialReportingService(
        context.engine,
        clock=FixedClock(UtcInstant(context.captured_at + timedelta(seconds=21))),
    ).build(currency="EUR")
    assert report.document["bets"] == 0
    estimates, audit = report.document["estimates"], report.document["audit"]
    assert isinstance(estimates, dict) and isinstance(audit, dict)
    assert estimates["roi"]["value"] is None
    assert audit["counts"] == {"not_taken": 1}
    assert audit["entries"] == []
    assert audit["oddsHistory"][-1]["oddsSnapshotId"] == str(changed)
    assert audit["oddsHistory"][-1]["changeFromPreviousRatio"] == "-0.5"
