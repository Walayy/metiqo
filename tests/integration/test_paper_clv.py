"""Le proxy de clôture exclut les prix post-start et les imports rétroactifs."""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from metiquo.contracts import PaperBet
from metiquo.contracts.enums import GameTitle
from metiquo.db.odds_models import OddsProviderRecord, OddsSnapshotRecord
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.paper.closing_line import PostgresClosingLineRepository
from metiquo.providers import ManualImportOddsProvider
from metiquo.services.odds_capture import OddsCaptureService, OddsCaptureSource
from tests.integration.test_paper_creation import _service
from tests.integration.test_paper_ledger import bet_values
from tests.integration.test_signal_persistence import _manual_row
from tests.integration.test_value_pipeline import _Context
from tests.integration.test_value_pipeline import context as context


def observe_quote(
    context: _Context,
    bet: PaperBet,
    captured_at: datetime,
    recorded_at: datetime,
    *,
    odds: str = "4.00",
    suspended: bool = False,
) -> UUID:
    with Session(context.engine) as session:
        entry = session.get(OddsSnapshotRecord, bet.odds_snapshot_id)
        assert entry is not None
        provider_row = session.get(OddsProviderRecord, entry.provider_id)
        assert provider_row is not None
        code = provider_row.code
    clock = FixedClock(UtcInstant(recorded_at))
    provider = ManualImportOddsProvider(code, clock=clock)
    row = _manual_row(code, context.event, captured_at, odds)
    row.update(
        provider_selection_id="signal-team-b",
        selection="TEAM_B",
        selection_label=context.event.team_b,
        market_status="suspended" if suspended else "open",
        provenance_reference=f"manual:clv:{captured_at.isoformat()}",
    )
    document = provider.import_document(json.dumps([row]).encode(), document_format="json")
    event = provider.list_events(
        context.event.starts_at - timedelta(hours=1),
        context.event.starts_at + timedelta(hours=1),
        GameTitle.LEAGUE_OF_LEGENDS,
    )[0]
    report = OddsCaptureService(context.engine, clock).capture_event(
        provider,
        event,
        OddsCaptureSource("manual_import", "P6 explicit test fixture", document.import_key),
    )
    return report.inserted_snapshot_ids[0]


@pytest.mark.integration
def test_clv_uses_only_known_prestart_quotes(context: _Context) -> None:
    values = bet_values(context)
    bet = _service(context).create(
        "entry", values["signal_id"], Decimal(10), "EUR", actor="operator"
    )
    start = context.event.starts_at
    closing = observe_quote(
        context, bet, start - timedelta(seconds=30), start - timedelta(seconds=29)
    )
    observe_quote(
        context,
        bet,
        start - timedelta(seconds=10),
        start - timedelta(seconds=9),
        odds="3",
        suspended=True,
    )
    observe_quote(
        context, bet, start + timedelta(seconds=1), start + timedelta(seconds=2), odds="2"
    )
    observe_quote(
        context, bet, start - timedelta(seconds=5), start + timedelta(seconds=20), odds="3"
    )
    repository = PostgresClosingLineRepository(
        context.engine, clock=FixedClock(UtcInstant(start + timedelta(hours=1)))
    )
    result = repository.get(bet.paper_bet_id)
    assert result.available is True and result.is_proxy is True
    assert result.closing_odds_snapshot_id == closing
    assert result.closing_odds == 4 and result.clv == 1
    assert result == repository.get(bet.paper_bet_id)
    assert result.entry_odds == 8


@pytest.mark.integration
def test_missing_recent_closing_quote_never_becomes_a_fabricated_clv(context: _Context) -> None:
    values = bet_values(context)
    bet = _service(context).create(
        "entry", values["signal_id"], Decimal(10), "EUR", actor="operator"
    )
    start = context.event.starts_at
    before = PostgresClosingLineRepository(
        context.engine, clock=FixedClock(UtcInstant(start - timedelta(seconds=1)))
    ).get(bet.paper_bet_id)
    assert before.available is False and before.reason == "EVENT_NOT_STARTED"
    result = PostgresClosingLineRepository(
        context.engine, clock=FixedClock(UtcInstant(start + timedelta(hours=1)))
    ).get(bet.paper_bet_id)
    assert result.available is False and result.clv is None
    assert result.reason == "CLOSING_TOO_OLD"
