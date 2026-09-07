"""API réelle : même DTO paper, entrée contrôlée et résultat dérivé d'OE."""

import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from httpx2 import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from metiquo.api.app import create_app
from metiquo.contracts import PaperBet
from metiquo.db.ops_models import AuditEventRecord
from metiquo.db.paper_models import PaperSettlementRecord
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.paper.reporting import PostgresFinancialReportingService
from tests.integration.test_paper_clv import observe_quote
from tests.integration.test_paper_ledger import bet_values
from tests.integration.test_paper_settlement_job import arrive_result
from tests.integration.test_postgres_canonical_api import _ReadyProbe, _request, _settings
from tests.integration.test_value_pipeline import _Context
from tests.integration.test_value_pipeline import context as context


@pytest.mark.integration
def test_real_paper_api_create_review_loss_and_cached_metrics(
    context: _Context, postgresql_url: str
) -> None:
    values = bet_values(context)
    now = context.captured_at + timedelta(seconds=20)
    settings = _settings(postgresql_url, "real").model_copy(
        update={"oe_freshness_sla_seconds": 14 * 86400}
    )
    # Même horloge injectable pour l'entrée, puis l'arrivée réelle de la fixture OE.
    app = create_app(
        settings=settings, readiness_probe=_ReadyProbe(), clock=FixedClock(UtcInstant(now))
    )

    def request(
        method: str, path: str, body: dict[str, object] | None = None, *, key: str = "paper-api-key"
    ) -> Response:
        async def send() -> Response:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.request(
                    method, path, json=body, headers={"Idempotency-Key": key}
                )

        return asyncio.run(send())

    created = request(
        "POST",
        "/api/v1/paper-bets",
        {"signalId": str(values["signal_id"]), "stakeAmount": "10", "currency": "EUR"},
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    identity = payload["data"]["paperBetId"]
    request_trace = UUID(created.headers["X-Trace-Id"])
    with Session(context.engine) as session:
        audit = session.scalar(
            select(AuditEventRecord).where(
                AuditEventRecord.target_type == "signals.paper_bets",
                AuditEventRecord.target_id == identity,
            )
        )
        assert audit is not None and audit.trace_id == request_trace and audit.actor == "api-local"
        assert audit.after_refs["signal_id"] == str(values["signal_id"])
    assert payload["meta"]["dataMode"] == "real"
    assert payload["data"]["status"] == "open"
    mock_app = create_app(
        settings=_settings(postgresql_url, "mock"),
        readiness_probe=_ReadyProbe(),
        clock=FixedClock(UtcInstant(now)),
    )
    mock_bet = _request(mock_app, "/api/v1/paper-bets").json()["data"][0]
    assert set(mock_bet) == set(payload["data"])
    listing = request("GET", "/api/v1/paper-bets?limit=1").json()
    assert listing["page"]["total"] == 1
    assert set(listing["data"][0]) == set(payload["data"])
    assert request("GET", "/api/v1/paper-bets?offset=1&limit=1").json()["data"] == []
    refused = request(
        "POST",
        "/api/v1/admin/paper-bets/settle",
        {"paperBetId": identity, "status": "won", "profitLoss": "70", "reason": "Forged"},
    )
    assert refused.status_code == 400
    pending = request(
        "POST",
        "/api/v1/admin/paper-bets/settle",
        {"paperBetId": identity, "reason": "Check source"},
        key="pending-api-key",
    )
    assert pending.status_code == 200, pending.text
    assert pending.json()["data"]["status"] == "pending_review"
    with Session(context.engine) as session:
        revision = session.scalar(select(PaperSettlementRecord))
        assert revision is not None and revision.evidence["requestReason"] == "Check source"
    assert request("GET", "/api/v1/paper-bets?status=pending_review").json()["page"]["total"] == 1
    missing = request("GET", "/api/v1/paper-bets/metrics?currency=EUR")
    assert missing.status_code == 200, missing.text
    assert missing.json()["data"]["reportId"] is None
    mock_metrics = _request(mock_app, "/api/v1/paper-bets/metrics?currency=EUR").json()
    assert set(mock_metrics["data"]) == set(missing.json()["data"])
    closing_id = observe_quote(
        context,
        PaperBet.model_validate_json(json.dumps(payload["data"])),
        context.event.starts_at - timedelta(seconds=30),
        context.event.starts_at - timedelta(seconds=29),
        odds="4",
    )
    arrival = context.event.starts_at + timedelta(hours=1)
    arrive_result(context, arrival, red_won=False)
    later = FixedClock(UtcInstant(arrival + timedelta(minutes=6)))
    app = create_app(settings=settings, readiness_probe=_ReadyProbe(), clock=later)
    lost = request(
        "POST",
        "/api/v1/admin/paper-bets/settle",
        {"paperBetId": identity, "reason": "Read arrived OE"},
        key="lost-api-key",
    )
    assert lost.status_code == 200, lost.text
    assert lost.json()["data"]["status"] == "lost"
    assert lost.json()["data"]["profitLoss"] == "-10.00000000"
    detail = request("GET", f"/api/v1/paper-bets/{identity}").json()["data"]
    assert detail["profitLoss"] == lost.json()["data"]["profitLoss"]
    assert detail["clv"] == "1.000000000000"
    assert detail["closingOddsSnapshotId"] == str(closing_id)
    assert detail["clvIsProxy"] is True
    report = PostgresFinancialReportingService(context.engine, clock=later).build(currency="EUR")
    metrics = request("GET", "/api/v1/paper-bets/metrics?currency=EUR").json()
    assert metrics["data"]["reportId"] == str(report.report_id)
    assert metrics["data"]["estimates"]["roi"]["value"] == "-1"
    assert metrics["data"]["estimates"]["roi"]["sampleSize"] == 1
    assert request("GET", f"/api/v1/paper-reports/{report.report_id}").status_code == 200
    export_path = os.environ.get("PAPER_GATE_REPORT_PATH")
    if export_path:
        Path(export_path).write_text(
            json.dumps(
                {
                    "gate": "P7",
                    "fixture": True,
                    "financialPerformanceValidated": False,
                    "notice": (
                        "Synthetic observed-quote fixture. "
                        "Not a financial backtest or live performance."
                    ),
                    "reportId": str(report.report_id),
                    "computedAt": report.computed_at.isoformat(),
                    "inputFingerprint": report.input_fingerprint,
                    "reportFingerprint": report.report_fingerprint,
                    "inputEvidence": report.input_evidence,
                    "document": report.document,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
