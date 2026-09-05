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
from datetime import date, datetime
from enum import IntEnum
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, Table, create_engine, func, insert, select

from metiquo.config import ConfigurationError, ObjectStoreBackend, Settings, load_settings
from metiquo.contracts.enums import DataMode
from metiquo.db.raw_models import CanonicalRow, IngestionRun, Snapshot, SourceCatalog
from metiquo.features.dataset import FeatureDatasetBuilder
from metiquo.foundation.time import SystemClock
from metiquo.ingestion.backfill import BackfillOrchestrator, YearSyncResult
from metiquo.ingestion.catalog import (
    LandingPageFetcher,
    SourceCatalogRepository,
    reconcile_catalog,
)
from metiquo.ingestion.fallback_catalog import (
    CatalogDiscoveryService,
    VersionedFallbackCatalog,
)
from metiquo.ingestion.freshness import FreshDataRequired, FreshnessPolicy
from metiquo.ingestion.invalidation import RevisionInvalidationService
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.ingestion.raw_loader import RawTabularLoader
from metiquo.ingestion.sync import OracleElixirYearSync, SyncFailed
from metiquo.models import (
    GameWinnerTrainingWorkflow,
    ModelArtifactStore,
    WalkForwardConfig,
)

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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    machine_readable = bool(arguments.json)
    try:
        settings = load_settings()
        engine = _engine(settings)
        try:
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
    except (CliError, ConfigurationError, ValueError) as error:
        document = {
            "ok": False,
            "errorCode": getattr(error, "code", "INVALID_CONFIGURATION"),
            "message": str(error),
        }
        exit_code = getattr(error, "exit_code", ExitCode.USAGE_OR_CONFIGURATION)
    except Exception as error:
        document = {
            "ok": False,
            "errorCode": "UNEXPECTED_FAILURE",
            "message": str(error),
        }
        exit_code = ExitCode.SOURCE_FAILURE
    _emit(document, machine_readable=machine_readable, failed=exit_code != ExitCode.SUCCESS)
    return int(exit_code)


def _dispatch(
    arguments: argparse.Namespace,
    settings: Settings,
    engine: Engine,
) -> tuple[dict[str, object], ExitCode]:
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
    clock = SystemClock()
    fallback = VersionedFallbackCatalog.load(settings.oe_source_catalog_path)
    outage_reason: str | None
    if settings.app_data_mode is DataMode.MOCK:
        discovery = fallback.as_discovery(clock)
        used_fallback = True
        outage_reason = "mock mode: external discovery disabled"
    else:
        resolution = CatalogDiscoveryService(
            LandingPageFetcher(clock=clock), fallback, clock=clock
        ).resolve()
        discovery = resolution.discovery
        used_fallback = resolution.used_fallback
        outage_reason = resolution.outage_reason
    with engine.begin() as connection:
        repository = SourceCatalogRepository(connection)
        reconciliation = reconcile_catalog(discovery, repository.active_records())
        repository.apply(reconciliation)
    return {
        "ok": True,
        "command": "catalog.refresh",
        "origin": discovery.origin,
        "usedFallback": used_fallback,
        "outageReason": outage_reason,
        "decisions": [
            {
                "year": decision.year,
                "status": decision.status,
                "candidateIds": [candidate.drive_file_id for candidate in decision.candidates],
            }
            for decision in reconciliation.decisions
        ],
        "alerts": [
            {"kind": alert.kind, "year": alert.year, "message": alert.message}
            for alert in reconciliation.alerts
        ],
    }


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
