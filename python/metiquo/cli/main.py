"""Commandes opérateur reproductibles pour Oracle's Elixir."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import IntEnum
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, Table, create_engine, func, insert, select

from metiquo.config import ConfigurationError, ObjectStoreBackend, Settings, load_settings
from metiquo.contracts.enums import DataMode
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot, SourceCatalog
from metiquo.features.dataset import FeatureDatasetBuilder
from metiquo.foundation.audit import audit_context
from metiquo.foundation.errors import BusinessError
from metiquo.foundation.time import SystemClock
from metiquo.ingestion.backfill import BackfillOrchestrator, YearSyncResult
from metiquo.ingestion.freshness import FreshDataRequired, FreshnessPolicy
from metiquo.ingestion.invalidation import RevisionInvalidationService
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.ingestion.operations import refresh_catalog
from metiquo.ingestion.raw_loader import RawTabularLoader
from metiquo.ingestion.sync import OracleElixirYearSync, SyncFailed
from metiquo.models import (
    GameWinnerTrainingWorkflow,
    ModelArtifactStore,
    WalkForwardConfig,
)
from metiquo.operations.backup import BackupService
from metiquo.operations.backup_tools import BackupError
from metiquo.paper.creation import PaperBankrollPolicy, PostgresPaperService
from metiquo.paper.reporting import PostgresFinancialReportingService
from metiquo.paper.settlement_job import PostgresPaperSettlementService
from metiquo.services.value_pipeline import PostgresValuePipeline, ValueEvaluationRequest
from metiquo.worker.queue import PostgresJobQueue

_PROVIDER = "oracles_elixir"
_DATASET = "league_of_legends_match_data"


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE_OR_CONFIGURATION = 2
    FRESH_DATA_REQUIRED = 3
    SOURCE_FAILURE = 4
    INTEGRITY_FAILURE = 5
    PARTIAL_BACKFILL = 6


class CliError(RuntimeError):
    def __init__(self, message: str, *, code: str, exit_code: ExitCode) -> None:
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oe", description="Oracle's Elixir pour Metiquo")
    commands = parser.add_subparsers(dest="command", required=True)

    catalog = commands.add_parser("catalog", help="gérer le catalogue de sources")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_refresh = catalog_commands.add_parser("refresh", help="rafraîchir le catalogue")
    _machine_output(catalog_refresh)

    backfill = commands.add_parser("backfill", help="synchroniser une plage d'années")
    backfill.add_argument("--from-year", type=int, required=True)
    backfill.add_argument("--to-year", type=int, required=True)
    backfill.add_argument("--fixture", type=Path)
    _machine_output(backfill)

    sync = commands.add_parser("sync", help="synchroniser une année")
    sync.add_argument("--year", type=int)
    sync.add_argument("--fixture", type=Path)
    freshness = sync.add_mutually_exclusive_group()
    freshness.add_argument("--allow-stale", action="store_true")
    freshness.add_argument("--require-fresh", action="store_true")
    _machine_output(sync)

    verify = commands.add_parser("verify", help="relire et vérifier un snapshot")
    verify.add_argument("--snapshot", type=UUID, required=True)
    _machine_output(verify)

    diff = commands.add_parser("diff", help="comparer deux manifestes de snapshots")
    diff.add_argument("--left", type=UUID, required=True)
    diff.add_argument("--right", type=UUID, required=True)
    _machine_output(diff)

    rebuild = commands.add_parser(
        "rebuild-canonical",
        help="rejouer les snapshots publiés dans le canonical préliminaire",
    )
    rebuild.add_argument("--from", dest="from_date", type=date.fromisoformat, required=True)
    _machine_output(rebuild)

    features_rebuild = commands.add_parser(
        "features-rebuild",
        help="recalculer les feature snapshots à partir d'une date",
    )
    features_rebuild.add_argument(
        "--from",
        dest="from_date",
        type=date.fromisoformat,
        required=True,
    )
    features_rebuild.add_argument("--code-commit")
    _machine_output(features_rebuild)

    model_train = commands.add_parser(
        "model-train",
        help="entraîner et enregistrer un candidat game_winner reproductible",
    )
    model_train.add_argument("--market", choices=("game_winner",), required=True)
    model_train.add_argument("--dataset", type=UUID)
    model_train.add_argument("--code-commit")
    model_train.add_argument("--minimum-train-periods", type=int, default=20)
    model_train.add_argument("--validation-periods", type=int, default=10)
    model_train.add_argument("--final-test-periods", type=int, default=10)
    _machine_output(model_train)
    value = commands.add_parser(
        "value-evaluate", help="évaluer et persister un signal depuis ses preuves"
    )
    value.add_argument("--odds-snapshot", type=UUID, required=True)
    value.add_argument("--event-mapping", type=UUID, required=True)
    value.add_argument("--market-mapping", type=UUID, required=True)
    value.add_argument("--policy", required=True)
    value.add_argument("--prediction", type=UUID)
    _machine_output(value)
    paper = commands.add_parser("paper-create", help="enregistrer une décision fictive manuelle")
    paper.add_argument("--signal", type=UUID, required=True)
    paper.add_argument("--stake", type=Decimal, required=True)
    paper.add_argument("--currency", required=True)
    paper.add_argument("--idempotency-key", required=True)
    paper.add_argument("--actor", required=True)
    _machine_output(paper)
    settle = commands.add_parser(
        "paper-settle", help="régler le ledger depuis les résultats OE validés"
    )
    settle.add_argument("--paper-bet", type=UUID)
    settle.add_argument("--idempotency-key")
    settle.add_argument("--actor", default="oe-settlement-job")
    settle.add_argument("--correction-reason")
    settle.add_argument("--limit", type=int, default=100)
    _machine_output(settle)
    report = commands.add_parser(
        "paper-report", help="matérialiser les métriques du ledger observé"
    )
    report.add_argument("--currency", required=True)
    _machine_output(report)
    jobs = commands.add_parser("jobs", help="consulter, annuler ou relancer les jobs")
    backup = commands.add_parser("backup", help="sauvegarder la base et les objets immuables")
    _machine_output(backup)
    job_commands = jobs.add_subparsers(dest="job_action", required=True)
    for action in ("show", "cancel", "rerun"):
        operation = job_commands.add_parser(action)
        operation.add_argument("job_id", type=UUID)
        if action == "rerun":
            operation.add_argument("--key", required=True)
            operation.add_argument("--actor", required=True)
            operation.add_argument("--reason", required=True)
        _machine_output(operation)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    machine_readable = bool(arguments.json)
    try:
        settings = load_settings()
        engine = _engine(settings)
        try:
            with audit_context(actor=getattr(arguments, "actor", "cli-local"), trace_id=uuid4()):
                document, exit_code = _dispatch(arguments, settings, engine)
        finally:
            engine.dispose()
    except FreshDataRequired as error:
        document = {
            "ok": False,
            "errorCode": "FRESH_DATA_REQUIRED",
            "message": str(error),
            "freshness": error.decision.to_dict(),
        }
        exit_code = ExitCode.FRESH_DATA_REQUIRED
    except SyncFailed as error:
        document = {
            "ok": False,
            "errorCode": error.error_code,
            "message": str(error),
            "runId": str(error.run_id),
        }
        exit_code = ExitCode.SOURCE_FAILURE
    except (CliError, ConfigurationError, ValueError, BusinessError, BackupError) as error:
        document = {
            "ok": False,
            "errorCode": getattr(error, "code", "INVALID_CONFIGURATION"),
            "message": str(error),
        }
        exit_code = getattr(error, "exit_code", ExitCode.USAGE_OR_CONFIGURATION)
    except Exception:
        document = {
            "ok": False,
            "errorCode": "UNEXPECTED_FAILURE",
            "message": "Échec interne ; consulter le code structuré",
        }
        exit_code = ExitCode.SOURCE_FAILURE
    _emit(document, machine_readable=machine_readable, failed=exit_code != ExitCode.SUCCESS)
    return int(exit_code)


def _dispatch(
    arguments: argparse.Namespace,
    settings: Settings,
    engine: Engine,
) -> tuple[dict[str, object], ExitCode]:
    if arguments.command == "backup":
        backup_result = BackupService(engine, settings).run()
        return {
            "command": "backup",
            "backupId": str(backup_result.backup_id),
            "path": str(backup_result.path),
            "copiedObjects": backup_result.copied_objects,
            "warnings": list(backup_result.warnings),
        }, ExitCode.SUCCESS
    if arguments.command == "jobs":
        if settings.app_data_mode is not DataMode.REAL:
            raise CliError(
                "jobs exige APP_DATA_MODE=real",
                code="REAL_MODE_REQUIRED",
                exit_code=ExitCode.USAGE_OR_CONFIGURATION,
            )
        queue = PostgresJobQueue(engine)
        if arguments.job_action == "cancel":
            job = queue.request_cancel(arguments.job_id)
        elif arguments.job_action == "rerun":
            job = queue.rerun(
                arguments.job_id, key=arguments.key, actor=arguments.actor, reason=arguments.reason
            )
        else:
            job = queue.get(arguments.job_id)
        return {
            "command": "jobs",
            "job": {
                "id": str(job.job_id),
                "type": job.job_type,
                "scope": job.scope,
                "status": job.status,
                "attempt": job.attempt,
                "maxAttempts": job.max_attempts,
                "scheduledAt": job.scheduled_at.isoformat(),
                "cancelRequested": job.cancel_requested,
                "errorCode": job.error_code,
                "traceId": str(job.trace_id),
                "rerunOf": str(job.rerun_of) if job.rerun_of else None,
            },
        }, ExitCode.SUCCESS
    if arguments.command == "paper-report":
        if settings.app_data_mode is not DataMode.REAL:
            raise CliError(
                "paper-report exige APP_DATA_MODE=real",
                code="REAL_MODE_REQUIRED",
                exit_code=ExitCode.USAGE_OR_CONFIGURATION,
            )
        financial_report = PostgresFinancialReportingService(
            engine, closing_max_age_seconds=settings.paper_closing_max_age_seconds
        ).build(currency=arguments.currency)
        return {
            "command": "paper-report",
            "reportId": str(financial_report.report_id),
            "computedAt": financial_report.computed_at.isoformat(),
            "fingerprint": financial_report.report_fingerprint,
            "report": financial_report.document,
        }, ExitCode.SUCCESS
    if arguments.command == "paper-settle":
        if settings.app_data_mode is not DataMode.REAL:
            raise CliError(
                "paper-settle exige APP_DATA_MODE=real",
                code="REAL_MODE_REQUIRED",
                exit_code=ExitCode.USAGE_OR_CONFIGURATION,
            )
        service = PostgresPaperSettlementService(
            engine,
            source_sla=timedelta(seconds=settings.oe_freshness_sla_seconds),
            settlement_delay=timedelta(seconds=settings.paper_settlement_delay_seconds),
        )
        if arguments.paper_bet is not None:
            bet = service.settle(
                arguments.paper_bet,
                key=arguments.idempotency_key,
                actor=arguments.actor,
                correction_reason=arguments.correction_reason,
            )
            return {
                "command": "paper-settle",
                "paperBet": bet.model_dump(mode="json", by_alias=True),
            }, ExitCode.SUCCESS
        if arguments.correction_reason or arguments.idempotency_key:
            raise ValueError("Une correction ou une clé explicite exige --paper-bet")
        report = service.run_pending(
            limit=arguments.limit, max_attempts=settings.paper_settlement_max_attempts
        )
        return {
            "command": "paper-settle",
            "processed": report.processed,
            "settled": report.settled,
            "pending": report.pending,
            "failed": [str(identity) for identity in report.failed],
        }, ExitCode.SOURCE_FAILURE if report.failed else ExitCode.SUCCESS
    if arguments.command == "paper-create":
        if settings.app_data_mode is not DataMode.REAL:
            raise CliError(
                "paper-create exige APP_DATA_MODE=real",
                code="REAL_MODE_REQUIRED",
                exit_code=ExitCode.USAGE_OR_CONFIGURATION,
            )
        bet = PostgresPaperService(
            engine,
            bankroll=PaperBankrollPolicy(
                settings.paper_bankroll_policy_version,
                settings.paper_bankroll_currency,
                settings.paper_bankroll_initial,
                settings.paper_max_open_exposure,
            ),
            source_sla=timedelta(seconds=settings.oe_freshness_sla_seconds),
        ).create(
            arguments.idempotency_key,
            arguments.signal,
            arguments.stake,
            arguments.currency,
            actor=arguments.actor,
        )
        return {
            "command": "paper-create",
            "paperBet": bet.model_dump(mode="json", by_alias=True),
        }, ExitCode.SUCCESS
    if arguments.command == "value-evaluate":
        if settings.app_data_mode is not DataMode.REAL:
            raise CliError(
                "value-evaluate exige APP_DATA_MODE=real",
                code="REAL_MODE_REQUIRED",
                exit_code=ExitCode.USAGE_OR_CONFIGURATION,
            )
        result = PostgresValuePipeline(
            engine,
            source_sla=timedelta(seconds=settings.oe_freshness_sla_seconds),
        ).evaluate(
            ValueEvaluationRequest(
                odds_snapshot_id=arguments.odds_snapshot,
                event_mapping_attempt_id=arguments.event_mapping,
                market_mapping_attempt_id=arguments.market_mapping,
                policy_version=arguments.policy,
                prediction_id=arguments.prediction,
            )
        )
        return {
            "command": "value-evaluate",
            "evaluationId": str(result.evaluation_id),
            "signalId": str(result.signal.signal_id) if result.signal else None,
            "grade": result.grade.value,
            "abstentionReasons": [reason.value for reason in result.reasons],
            "computedAt": result.computed_at.isoformat(),
            "fingerprint": result.fingerprint,
        }, ExitCode.SUCCESS
    if arguments.command == "catalog":
        return _catalog_refresh(settings, engine), ExitCode.SUCCESS
    if arguments.command == "sync":
        return _sync(arguments, settings, engine), ExitCode.SUCCESS
    if arguments.command == "backfill":
        document = _backfill(arguments, settings, engine)
        status = document["status"]
        return document, (ExitCode.SUCCESS if status == "succeeded" else ExitCode.PARTIAL_BACKFILL)
    if arguments.command == "verify":
        return _verify(engine, settings, arguments.snapshot), ExitCode.SUCCESS
    if arguments.command == "diff":
        return _diff(engine, arguments.left, arguments.right), ExitCode.SUCCESS
    if arguments.command == "rebuild-canonical":
        return _rebuild(engine, settings, arguments.from_date), ExitCode.SUCCESS
    if arguments.command == "features-rebuild":
        return (
            _features_rebuild(
                engine,
                from_date=arguments.from_date,
                code_commit=arguments.code_commit,
            ),
            ExitCode.SUCCESS,
        )
    if arguments.command == "model-train":
        document = _model_train(
            engine,
            settings,
            dataset_id=arguments.dataset,
            code_commit=arguments.code_commit,
            minimum_train_periods=arguments.minimum_train_periods,
            validation_periods=arguments.validation_periods,
            final_test_periods=arguments.final_test_periods,
        )
        return document, (
            ExitCode.SUCCESS if document["gatePassed"] else ExitCode.INTEGRITY_FAILURE
        )
    raise CliError(
        "commande non reconnue",
        code="INVALID_COMMAND",
        exit_code=ExitCode.USAGE_OR_CONFIGURATION,
    )


def _catalog_refresh(settings: Settings, engine: Engine) -> dict[str, object]:
    return refresh_catalog(settings, engine)


def _sync(
    arguments: argparse.Namespace,
    settings: Settings,
    engine: Engine,
) -> dict[str, object]:
    year = arguments.year if arguments.year is not None else settings.oe_current_year
    policy = _freshness_policy(arguments, settings)
    report = OracleElixirYearSync(engine=engine, settings=settings).sync_year(
        year=year,
        policy=policy,
        fixture_path=arguments.fixture,
    )
    return {
        "ok": True,
        "command": "sync",
        "year": year,
        "runId": str(report.run_id),
        "loadRunId": str(report.load_run_id) if report.load_run_id is not None else None,
        "snapshotId": str(report.snapshot_id) if report.snapshot_id is not None else None,
        "transport": report.transport,
        "freshness": report.freshness.to_dict(),
        "load": (report.load_statistics.to_dict() if report.load_statistics is not None else None),
    }


@dataclass(slots=True)
class _BackfillProcessor:
    service: OracleElixirYearSync
    fixture_path: Path | None

    def sync_year(
        self,
        *,
        provider: str,
        dataset: str,
        year: int,
        job_id: UUID,
        attempt: int,
    ) -> YearSyncResult:
        del job_id, attempt
        if provider != _PROVIDER or dataset != _DATASET:
            raise ValueError("backfill réservé au dataset Oracle's Elixir LoL")
        report = self.service.sync_year(
            year=year,
            policy=FreshnessPolicy(require_fresh=True),
            fixture_path=self.fixture_path,
            run_kind="backfill",
        )
        return YearSyncResult(report.run_id)


def _backfill(
    arguments: argparse.Namespace,
    settings: Settings,
    engine: Engine,
) -> dict[str, object]:
    processor = _BackfillProcessor(
        OracleElixirYearSync(engine=engine, settings=settings), arguments.fixture
    )
    result = BackfillOrchestrator(engine=engine, processor=processor).run(
        provider=_PROVIDER,
        dataset=_DATASET,
        from_year=arguments.from_year,
        to_year=arguments.to_year,
    )
    return {
        "ok": result.status == "succeeded",
        "command": "backfill",
        "jobId": str(result.job_id),
        "status": result.status,
        "fromYear": result.from_year,
        "toYear": result.to_year,
        "years": [
            {
                "year": item.year,
                "status": item.status,
                "attempts": item.attempts,
                "lastRunId": str(item.last_run_id) if item.last_run_id else None,
                "errorCode": item.error_code,
            }
            for item in result.years
        ],
    }


def _verify(engine: Engine, settings: Settings, snapshot_id: UUID) -> dict[str, object]:
    snapshots = cast(Table, Snapshot.__table__)
    with engine.connect() as connection:
        row = (
            connection.execute(select(snapshots).where(snapshots.c.id == snapshot_id))
            .mappings()
            .one_or_none()
        )
    if row is None:
        raise CliError(
            "snapshot introuvable",
            code="SNAPSHOT_NOT_FOUND",
            exit_code=ExitCode.INTEGRITY_FAILURE,
        )
    store = FilesystemObjectStore(settings.object_store_root / "raw" / "oracles_elixir")
    with store.open_source(year=int(row["year"]), sha256=str(row["sha256"])) as stream:
        digest_builder = hashlib.sha256()
        size = 0
        while chunk := stream.read(1024 * 1024):
            digest_builder.update(chunk)
            size += len(chunk)
        digest = digest_builder.hexdigest()
    expected_hash = str(row["sha256"])
    expected_size = int(row["byte_size"])
    valid = digest == expected_hash and size == expected_size and row["status"] == "validated"
    if not valid:
        raise CliError(
            "le snapshot ne correspond pas à son enregistrement validé",
            code="SNAPSHOT_INTEGRITY_MISMATCH",
            exit_code=ExitCode.INTEGRITY_FAILURE,
        )
    return {
        "ok": True,
        "command": "verify",
        "snapshotId": str(snapshot_id),
        "sha256": digest,
        "byteSize": size,
        "objectKey": str(row["object_key"]),
        "status": str(row["status"]),
    }


def _diff(engine: Engine, left_id: UUID, right_id: UUID) -> dict[str, object]:
    snapshots = cast(Table, Snapshot.__table__)
    with engine.connect() as connection:
        rows = {
            row["id"]: row
            for row in connection.execute(
                select(snapshots).where(snapshots.c.id.in_((left_id, right_id)))
            ).mappings()
        }
    missing = [str(snapshot_id) for snapshot_id in (left_id, right_id) if snapshot_id not in rows]
    if missing:
        raise CliError(
            f"snapshot(s) introuvable(s): {', '.join(missing)}",
            code="SNAPSHOT_NOT_FOUND",
            exit_code=ExitCode.INTEGRITY_FAILURE,
        )
    left = rows[left_id]
    right = rows[right_id]
    left_manifest = cast(dict[str, object], left["manifest"])
    right_manifest = cast(dict[str, object], right["manifest"])
    fields = (
        "sha256",
        "byteSize",
        "schemaFingerprint",
        "rowCount",
        "minEventDate",
        "maxEventDate",
        "qualityStatus",
    )
    changes = {
        field: {"left": left_manifest.get(field), "right": right_manifest.get(field)}
        for field in fields
        if left_manifest.get(field) != right_manifest.get(field)
    }
    return {
        "ok": True,
        "command": "diff",
        "left": str(left_id),
        "right": str(right_id),
        "identical": not changes,
        "changes": changes,
    }


def _rebuild(engine: Engine, settings: Settings, from_date: date) -> dict[str, object]:
    catalog = cast(Table, SourceCatalog.__table__)
    snapshots = cast(Table, Snapshot.__table__)
    runs = cast(Table, IngestionRun.__table__)
    with engine.connect() as connection:
        published = (
            connection.execute(
                select(catalog.c.id.label("catalog_id"), snapshots)
                .join(snapshots, catalog.c.current_snapshot_id == snapshots.c.id)
                .where(
                    catalog.c.provider == _PROVIDER,
                    catalog.c.dataset == _DATASET,
                    snapshots.c.status == "validated",
                )
                .order_by(snapshots.c.year)
            )
            .mappings()
            .all()
        )
    store = FilesystemObjectStore(settings.object_store_root / "raw" / "oracles_elixir")
    rebuilt: list[dict[str, object]] = []
    for row in published:
        manifest = cast(dict[str, object], row["manifest"])
        max_date = manifest.get("maxEventDate")
        if (
            isinstance(max_date, str)
            and datetime.fromisoformat(max_date.replace("Z", "+00:00")).date() < from_date
        ):
            continue
        with store.open_source(year=int(row["year"]), sha256=str(row["sha256"])) as stream:
            payload = stream.read()
        compression = str(manifest.get("compression", "none"))
        payload = _decompress_source(payload, compression)
        with tempfile.TemporaryDirectory(prefix="metiquo-rebuild-") as directory:
            csv_path = Path(directory) / "source.csv"
            csv_path.write_bytes(payload)
            run_id = uuid4()
            now = SystemClock().now().value
            with engine.begin() as connection:
                connection.execute(
                    insert(runs).values(
                        id=run_id,
                        source_catalog_id=row["catalog_id"],
                        snapshot_id=row["id"],
                        run_kind="load",
                        status="running",
                        attempt=1,
                        transport="object-store-rebuild",
                        correlation_id=f"oe-rebuild-{run_id}",
                        started_at=now,
                        created_at=now,
                    )
                )
            loaded = RawTabularLoader(engine=engine).load(
                source_catalog_id=row["catalog_id"],
                snapshot_id=row["id"],
                run_id=run_id,
                csv_path=csv_path,
                encoding=str(manifest.get("encoding", "utf-8")),
                delimiter=str(manifest.get("delimiter", ",")),
            )
            RevisionInvalidationService(engine=engine).emit_for_run(run_id)
        rebuilt.append(
            {
                "year": int(row["year"]),
                "snapshotId": str(row["id"]),
                "runId": str(run_id),
                "load": loaded.statistics.to_dict(),
            }
        )
    canonical = cast(Table, CanonicalRow.__table__)
    with engine.connect() as connection:
        row_count = int(
            connection.execute(
                select(func.count())
                .select_from(canonical)
                .where(
                    canonical.c.provider == _PROVIDER,
                    canonical.c.dataset == _DATASET,
                    canonical.c.event_date >= from_date,
                )
            ).scalar_one()
        )
    return {
        "ok": True,
        "command": "rebuild-canonical",
        "from": from_date.isoformat(),
        "snapshotsReplayed": rebuilt,
        "canonicalRowsFromDate": row_count,
    }


def _features_rebuild(
    engine: Engine,
    *,
    from_date: date,
    code_commit: str | None,
) -> dict[str, object]:
    resolved_commit = code_commit or _current_git_commit()
    report = FeatureDatasetBuilder(
        engine=engine,
        code_commit=resolved_commit,
        provider=_PROVIDER,
        dataset=_DATASET,
    ).rebuild_from(from_date)
    return {
        "ok": True,
        "command": "features-rebuild",
        "codeCommit": resolved_commit,
        **report.to_dict(),
    }


def _model_train(
    engine: Engine,
    settings: Settings,
    *,
    dataset_id: UUID | None,
    code_commit: str | None,
    minimum_train_periods: int,
    validation_periods: int,
    final_test_periods: int,
) -> dict[str, object]:
    if settings.object_store_backend is not ObjectStoreBackend.FILESYSTEM:
        raise CliError(
            "model-train exige actuellement OBJECT_STORE_BACKEND=filesystem",
            code="MODEL_STORE_UNSUPPORTED",
            exit_code=ExitCode.USAGE_OR_CONFIGURATION,
        )
    result = GameWinnerTrainingWorkflow(
        engine=engine,
        artifacts=ModelArtifactStore(FilesystemObjectStore(settings.object_store_root / "models")),
        code_commit=code_commit or _current_git_commit(),
        dataset_id=dataset_id,
        walk_forward=WalkForwardConfig(
            minimum_train_periods=minimum_train_periods,
            validation_periods=validation_periods,
            final_test_periods=final_test_periods,
        ),
    ).run()
    return {
        "ok": result.gate_passed,
        "command": "model-train",
        "market": "game_winner",
        **result.document(),
    }


def _current_git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    commit = result.stdout.strip().casefold()
    if result.returncode != 0 or not commit:
        raise CliError(
            "code commit introuvable ; utiliser --code-commit",
            code="CODE_COMMIT_REQUIRED",
            exit_code=ExitCode.USAGE_OR_CONFIGURATION,
        )
    return commit


def _freshness_policy(arguments: argparse.Namespace, settings: Settings) -> FreshnessPolicy:
    if arguments.allow_stale:
        return FreshnessPolicy(allow_stale=True)
    if arguments.require_fresh:
        return FreshnessPolicy(require_fresh=True)
    return FreshnessPolicy.from_settings(settings)


def _decompress_source(payload: bytes, compression: str) -> bytes:
    if compression == "none":
        return payload
    if compression == "gzip":
        return gzip.decompress(payload)
    if compression == "zip":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) != 1:
                raise CliError(
                    "archive de snapshot sans CSV unique",
                    code="ARCHIVE_MEMBER_INVALID",
                    exit_code=ExitCode.INTEGRITY_FAILURE,
                )
            return archive.read(members[0])
    raise CliError(
        "compression de snapshot inconnue",
        code="SNAPSHOT_COMPRESSION_INVALID",
        exit_code=ExitCode.INTEGRITY_FAILURE,
    )


def _engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        connect_args={"options": "-c timezone=UTC"},
        pool_pre_ping=True,
    )


def _machine_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="émettre un objet JSON compact")


def _emit(document: dict[str, object], *, machine_readable: bool, failed: bool) -> None:
    if machine_readable:
        output = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    elif failed and document.get("command") == "model-train":
        output = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
    elif failed:
        output = f"ERREUR [{document.get('errorCode', 'UNKNOWN')}]: {document.get('message', '')}"
    else:
        output = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
    print(output, file=sys.stderr if failed else sys.stdout)
