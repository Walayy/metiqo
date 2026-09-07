"""Handlers métier disponibles avant la planification automatique."""

from datetime import timedelta

from sqlalchemy import Engine

from metiquo.config import Settings
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.paper.reporting import PostgresFinancialReportingService
from metiquo.paper.settlement_job import PostgresPaperSettlementService
from metiquo.worker.contracts import JobContext, JobHandler


class PaperReportHandler:
    def __init__(self, engine: Engine, settings: Settings) -> None:
        self.engine, self.settings = engine, settings

    def handle(self, context: JobContext) -> dict[str, object]:
        context.cancellation.raise_if_cancelled()
        currency = context.payload.get("currency")
        if not isinstance(currency, str):
            raise BusinessError(ErrorCode.INVALID_INPUT, "Devise du job absente")
        report = PostgresFinancialReportingService(
            self.engine,
            closing_max_age_seconds=self.settings.paper_closing_max_age_seconds,
            clock=context.clock,
        ).build(currency=currency)
        return {"reportId": str(report.report_id), "reportFingerprint": report.report_fingerprint}


class PaperSettlementHandler:
    def __init__(self, engine: Engine, settings: Settings) -> None:
        self.engine, self.settings = engine, settings

    def handle(self, context: JobContext) -> dict[str, object]:
        context.cancellation.raise_if_cancelled()
        service = PostgresPaperSettlementService(
            self.engine,
            source_sla=timedelta(seconds=self.settings.oe_freshness_sla_seconds),
            settlement_delay=timedelta(seconds=self.settings.paper_settlement_delay_seconds),
            clock=context.clock,
        )
        report = service.run_pending(
            max_attempts=self.settings.paper_settlement_max_attempts,
            checkpoint=context.cancellation.raise_if_cancelled,
        )
        if report.failed:
            raise BusinessError(
                ErrorCode.DEPENDENCY_UNAVAILABLE, "Échec partiel du règlement paper", retryable=True
            )
        return {"processed": report.processed}


def default_handlers(engine: Engine, settings: Settings) -> dict[str, JobHandler]:
    return {
        "paper.report": PaperReportHandler(engine, settings),
        "paper.settle": PaperSettlementHandler(engine, settings),
    }
