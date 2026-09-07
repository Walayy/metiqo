"""Handlers métier disponibles avant la planification automatique."""

import hashlib
from datetime import timedelta

from sqlalchemy import Engine, select

from metiquo.config import Settings
from metiquo.db.raw_models import IngestionRun, SourceCatalog
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.ingestion.freshness import FreshnessPolicy
from metiquo.ingestion.operations import refresh_catalog, verify_snapshot
from metiquo.ingestion.sync import OracleElixirYearSync, SyncFailed
from metiquo.paper.reporting import PostgresFinancialReportingService
from metiquo.paper.settlement_job import PostgresPaperSettlementService
from metiquo.worker.alerts import PostgresAlertMonitor
from metiquo.worker.contracts import JobContext, JobHandler


class AlertHandler:
    def __init__(self, engine: Engine, settings: Settings) -> None:
        self.engine, self.settings = engine, settings

    def handle(self, context: JobContext) -> dict[str, object]:
        context.cancellation.raise_if_cancelled()
        notices = PostgresAlertMonitor(self.engine, self.settings, context.clock).check()
        return {"alertEvents": [str(identity) for identity in notices]}


class OracleCatalogHandler:
    def __init__(self, engine: Engine, settings: Settings) -> None:
        self.engine, self.settings = engine, settings

    def handle(self, context: JobContext) -> dict[str, object]:
        context.cancellation.raise_if_cancelled()
        result = refresh_catalog(self.settings, self.engine, clock=context.clock)
        if result["usedFallback"]:
            raise BusinessError(
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "Catalogue confirmé par fallback ; découverte distante indisponible",
                retryable=True,
            )
        return {
            "origin": result["origin"],
            "decisions": result["decisions"],
            "alerts": result["alerts"],
        }


class OracleSyncHandler:
    def __init__(self, engine: Engine, settings: Settings, *, deep: bool = False) -> None:
        self.engine, self.settings, self.deep = engine, settings, deep

    def handle(self, context: JobContext) -> dict[str, object]:
        context.cancellation.raise_if_cancelled()
        year = context.payload.get("year")
        if type(year) is not int or not 2014 <= year <= 2200:
            raise BusinessError(ErrorCode.INVALID_INPUT, "Année du job invalide")
        if self.deep:
            with self.engine.connect() as connection:
                identity = connection.scalar(
                    select(SourceCatalog.current_snapshot_id).where(
                        SourceCatalog.provider == "oracles_elixir",
                        SourceCatalog.dataset == "league_of_legends_match_data",
                        SourceCatalog.season_year == year,
                        SourceCatalog.status == "active",
                    )
                )
            if identity is None:
                raise BusinessError(ErrorCode.INVALID_STATE, "Aucun snapshot validé à contrôler")
            return verify_snapshot(self.engine, self.settings, identity)
        report = OracleElixirYearSync(
            engine=self.engine, settings=self.settings, clock=context.clock
        ).sync_year(
            year=year,
            policy=FreshnessPolicy(allow_stale=True),
            check_unchanged=True,
            request_key_hash=hashlib.sha256(str(context.job_id).encode()).hexdigest(),
        )
        with self.engine.connect() as connection:
            failure_code = connection.scalar(
                select(IngestionRun.error_code).where(
                    IngestionRun.id == report.run_id, IngestionRun.status == "failed"
                )
            )
        if failure_code is not None or report.transport == "validated-private-mirror":
            raise SyncFailed(
                "Snapshot conservé ; synchronisation distante indisponible",
                error_code=failure_code or "SOURCE_UNAVAILABLE",
                run_id=report.run_id,
            )
        return {
            "runId": str(report.run_id),
            "snapshotId": str(report.snapshot_id),
            "freshness": report.freshness.status.value,
        }


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
        "ops.alerts": AlertHandler(engine, settings),
        "oe.catalog": OracleCatalogHandler(engine, settings),
        "oe.sync": OracleSyncHandler(engine, settings),
        "oe.audit": OracleSyncHandler(engine, settings),
        "oe.deep": OracleSyncHandler(engine, settings, deep=True),
        "paper.report": PaperReportHandler(engine, settings),
        "paper.settle": PaperSettlementHandler(engine, settings),
    }
