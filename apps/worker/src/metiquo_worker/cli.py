import argparse
import json
import logging
import signal
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from metiquo_core.config import Settings
from metiquo_core.db import create_db
from metiquo_core.models import CatalogMetadata, Dataset, IngestionRun
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from metiquo_worker.catalog_sync import sync_catalog
from metiquo_worker.ingestion import SOURCE, CollectionBusy, collect

logger = logging.getLogger(__name__)


def due_scope(engine: Engine, settings: Settings) -> tuple[bool, bool]:
    with Session(engine) as session:
        latest_year = (
            select(func.max(Dataset.file_year)).where(Dataset.source == SOURCE).scalar_subquery()
        )
        latest = session.scalar(
            select(Dataset.checked_at).where(
                Dataset.source == SOURCE,
                Dataset.file_year == latest_year,
                Dataset.active_version_id.is_not(None),
            )
        )
        full = session.scalar(
            select(IngestionRun.finished_at)
            .where(
                IngestionRun.source == SOURCE,
                IngestionRun.status == "succeeded",
                IngestionRun.scope == "all",
            )
            .order_by(IngestionRun.finished_at.desc())
            .limit(1)
        )
    now = datetime.now(UTC)
    full_due = full is None or (now - full).total_seconds() >= settings.oracle_full_refresh_seconds
    due = latest is None or (now - latest).total_seconds() >= settings.oracle_interval_seconds
    return due or full_due, full_due


def catalog_due(engine: Engine, settings: Settings) -> bool:
    with Session(engine) as session:
        metadata = session.get(CatalogMetadata, 1)
        checked = metadata.checked_at if metadata and metadata.active_version_id else None
    return (
        checked is None
        or (datetime.now(UTC) - checked).total_seconds() >= settings.catalog_interval_seconds
    )


def serve(engine: Engine, settings: Settings, only: list[str] | None = None) -> None:
    stopping = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopping.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    heartbeat = (
        Path("/tmp/metiquo-worker.heartbeat")
        if Path("/tmp").is_dir()
        else Path(".cache/backend/worker.heartbeat")
    )
    heartbeat.parent.mkdir(parents=True, exist_ok=True)
    retry_at = {"lol-catalog": 0.0, "oracles-elixir": 0.0}
    failures = {"lol-catalog": 0, "oracles-elixir": 0}
    logger.info(
        "Worker started; catalog=%s, Oracle=%s; Stake has no registered job",
        settings.catalog_enabled,
        settings.oracle_enabled,
    )
    while not stopping.is_set():
        heartbeat.touch()
        for source in retry_at:
            if stopping.is_set():
                break
            enabled = (
                settings.catalog_enabled if source == "lol-catalog" else settings.oracle_enabled
            )
            if not enabled or (only and source not in only) or time.monotonic() < retry_at[source]:
                continue
            try:
                if source == "lol-catalog":
                    if catalog_due(engine, settings):
                        sync_catalog(engine, settings)
                else:
                    due, full = due_scope(engine, settings)
                    if due:
                        collect(engine, settings, latest=not full)
                failures[source] = 0
            except CollectionBusy:
                logger.info("%s already running; checking again later", source)
                retry_at[source] = time.monotonic() + 60
            except Exception as error:
                failures[source] += 1
                delay = min(1800, 60 * 2 ** min(failures[source] - 1, 5))
                retry_at[source] = time.monotonic() + delay
                logger.error("%s failed (%s); retry in %ss", source, type(error).__name__, delay)
        stopping.wait(30)
    engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Metiquo data worker")
    commands = parser.add_subparsers(dest="command", required=True)
    scheduler = commands.add_parser("serve", help="Schedule LoL catalog daily and Oracle updates")
    scheduler.add_argument(
        "--only",
        action="append",
        choices=["lol-catalog", "oracles-elixir"],
        help="Schedule only the selected source (repeatable)",
    )
    catalog = commands.add_parser(
        "sync-lol-catalog", help="Collect and publish the LoL reference and logos"
    )
    catalog.add_argument(
        "--allow-coverage-drop",
        action="store_true",
        help="Manually accept a verified drop of more than 20%% of identities",
    )
    command = commands.add_parser(
        "sync-oracles-elixir",
        aliases=["collect"],
        help="Collect Oracle CSVs; collect is the legacy alias",
    )
    scope = command.add_mutually_exclusive_group()
    scope.add_argument("--years", type=int, nargs="+", help="Specific source file years")
    scope.add_argument(
        "--latest", action="store_true", help="Latest discovered year; default is all years"
    )
    args = parser.parse_args()
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    engine = create_db(settings)
    try:
        if args.command == "serve":
            serve(engine, settings, args.only)
        else:
            try:
                if args.command == "sync-lol-catalog":
                    run_id = sync_catalog(
                        engine, settings, allow_coverage_drop=args.allow_coverage_drop
                    )
                else:
                    run_id = collect(
                        engine,
                        settings,
                        set(args.years) if args.years else None,
                        latest=args.latest,
                    )
                with Session(engine) as session:
                    run = session.get(IngestionRun, run_id)
                    assert run is not None
                    details = {k: v for k, v in run.details.items() if k != "pages"}
                    print(
                        json.dumps(
                            {
                                "runId": str(run_id),
                                "source": run.source,
                                "status": run.status,
                                **details,
                            }
                        )
                    )
            except CollectionBusy as error:
                parser.exit(75, f"Collection busy: {error}\n")
            except (RuntimeError, ValueError) as error:
                parser.exit(1, f"Collection failed: {error}\n")
    finally:
        engine.dispose()
