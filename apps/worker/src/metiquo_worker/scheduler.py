"""Persistent scheduler. Only registered collectors can be dispatched; never a shell command."""

import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from metiquo_core.config import Settings
from metiquo_core.models import (
    CollectorState,
    IngestionRun,
    ScriptRun,
    ScriptSchedule,
    WorkerStatus,
)
from metiquo_core.scheduling import SCRIPTS, upcoming
from sqlalchemy import Engine, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from metiquo_worker.catalog_sync import sync_catalog
from metiquo_worker.ingestion import collect
from metiquo_worker.jobs import CollectionBusy, source_lock
from metiquo_worker.loltv_browser import close_browser
from metiquo_worker.loltv_policy import LoltvBlocked
from metiquo_worker.loltv_sync import next_live_due, sync_loltv
from metiquo_worker.selection_results import settle_selections
from metiquo_worker.stake_policy import StakeDeferred
from metiquo_worker.stake_sync import sync_stake
from metiquo_worker.worker_logs import bind_run, emit, error_context, prune

logger = logging.getLogger(__name__)
SCHEDULER_LOCK = 62883200
SOURCE_SCHEDULER_LOCKS = {
    "lol-catalog": SCHEDULER_LOCK + 1,
    "oracles-elixir": SCHEDULER_LOCK + 2,
    "loltv": SCHEDULER_LOCK + 3,
    "stake": SCHEDULER_LOCK + 4,
    "settlements": SCHEDULER_LOCK + 5,
}


def enabled_scripts(settings: Settings, only: list[str] | None) -> list[str]:
    enabled_by_source = {
        "lol-catalog": settings.catalog_enabled,
        "oracles-elixir": settings.oracle_enabled,
        "loltv": settings.loltv_enabled,
        "stake": settings.stake_enabled,
        "settlements": settings.settlements_enabled,
    }
    return [
        key
        for key, definition in SCRIPTS.items()
        if enabled_by_source[definition.source] and (not only or definition.source in only)
    ]


def heartbeat(engine: Engine, scripts: list[str], path: Path, worker_id: int = 1) -> None:
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        db.execute(
            insert(WorkerStatus)
            .values(id=worker_id, seen_at=now, scripts=scripts)
            .on_conflict_do_update(
                index_elements=[WorkerStatus.id], set_={"seen_at": now, "scripts": scripts}
            )
        )
    path.touch()


def tick(engine: Engine, settings: Settings, scripts: list[str], stopping: threading.Event) -> None:
    for source, lock_id in SOURCE_SCHEDULER_LOCKS.items():
        group = [key for key in scripts if SCRIPTS[key].source == source]
        if group:
            _tick_source(engine, settings, group, stopping, lock_id)


def _tick_source(
    engine: Engine, settings: Settings, scripts: list[str], stopping: threading.Event, lock_id: int
) -> None:
    # This connection-level lock spans dispatch and execution, so another worker cannot
    # mistake a live run for an interrupted one or claim the same queue entry.
    with source_lock(engine, lock_id):
        now = datetime.now(UTC)
        with Session(engine) as db, db.begin():
            interrupted = db.execute(
                update(ScriptRun)
                .where(ScriptRun.status == "running", ScriptRun.script_id.in_(scripts))
                .values(
                    status="interrupted",
                    finished_at=now,
                    error="Exécution interrompue par un arrêt du worker.",
                )
                .returning(ScriptRun.id, ScriptRun.script_id)
            ).all()
            rows = db.scalars(
                select(ScriptSchedule)
                .where(ScriptSchedule.id.in_(scripts))
                .order_by(ScriptSchedule.id)
                .with_for_update()
            ).all()
            for row in rows:
                live_due = None
                # The default minute schedule is a continuous live service. Its
                # durable per-match deadlines can wake it between cron ticks.
                # A paused or custom cron remains under the administrator's control.
                if (
                    row.id == "loltv-matches"
                    and row.enabled
                    and row.cron in {"* * * * *", "*/1 * * * *"}
                ):
                    state = db.get(CollectorState, "loltv")
                    live_due = next_live_due(state.data, settings) if state else None
                if row.enabled and (
                    row.next_run_at <= now or live_due is not None and live_due <= now.timestamp()
                ):
                    active = db.scalar(
                        select(ScriptRun.id).where(
                            ScriptRun.script_id == row.id,
                            ScriptRun.status.in_(["queued", "running"]),
                        )
                    )
                    if active is None:
                        db.add(
                            ScriptRun(
                                script_id=row.id,
                                trigger="schedule",
                                status="queued",
                                requested_at=now,
                                available_at=now,
                            )
                        )
                    # Coalesce missed ticks after downtime into one run, never a burst.
                    row.next_run_at = upcoming(row.cron, row.timezone, now, 1)[0]
            db.flush()
            ids = list(
                db.scalars(
                    select(ScriptRun.id)
                    .where(
                        ScriptRun.status == "queued",
                        ScriptRun.script_id.in_(scripts),
                        ScriptRun.available_at <= now,
                    )
                    .order_by(ScriptRun.requested_at)
                )
            )
        for interrupted_id, interrupted_script in interrupted:
            binding = bind_run(interrupted_script, interrupted_id)
            try:
                emit(engine, settings.worker_status_id, "run_interrupted")
            finally:
                binding.reset()
        for run_id in ids:
            if stopping.is_set():
                break
            with Session(engine) as db, db.begin():
                run = db.get(ScriptRun, run_id, with_for_update=True)
                assert run is not None
                script_id = run.script_id
                run.status, run.started_at = "running", datetime.now(UTC)
                run.error = None
            binding = bind_run(script_id, run_id)
            emit(engine, settings.worker_status_id, "run_started")
            try:
                settlement_details: dict[str, int] | None = None
                if script_id == "lol-catalog":
                    ingestion_id = sync_catalog(engine, settings)
                elif script_id in {"oracle-latest", "oracle-full"}:
                    ingestion_id = collect(engine, settings, latest=script_id == "oracle-latest")
                elif script_id == "loltv-matches":
                    ingestion_id = sync_loltv(engine, settings)
                elif script_id == "stake-markets":
                    ingestion_id = sync_stake(engine, settings, script_run_id=run_id)
                elif script_id == "settle-selections":
                    settlement_details = settle_selections(engine)
                    ingestion_id = None
                else:
                    raise ValueError("Unregistered script")
                with Session(engine) as db, db.begin():
                    run = db.get(ScriptRun, run_id)
                    ingestion = db.get(IngestionRun, ingestion_id) if ingestion_id else None
                    assert run is not None
                    run.ingestion_run_id = ingestion_id
                    run.status = ingestion.status if ingestion else "succeeded"
                    run.finished_at = datetime.now(UTC)
                    if ingestion is not None and ingestion.status != "succeeded":
                        run.error = "La collecte a échoué. Consultez les journaux du worker."
                    outcome = run.status
                    details = ingestion.details if ingestion else settlement_details or {}
                counts = {
                    key: details[key]
                    for key in (
                        "snapshots",
                        "quotes",
                        "markets",
                        "eventsFailed",
                        "leagues",
                        "teams",
                        "imported",
                        "unchanged",
                        "published",
                        "created",
                        "knownEvents",
                        "pendingDetails",
                        "unavailableFeeds",
                        "examined",
                        "changed",
                        "pending",
                        "won",
                        "lost",
                        "void",
                    )
                    if isinstance(details.get(key), int)
                }
                if isinstance(details.get("errors"), list):
                    counts["errors"] = len(cast(list[object], details["errors"]))
                code = (
                    "run_partial"
                    if outcome == "succeeded" and details.get("complete") is False
                    else "run_succeeded"
                    if outcome == "succeeded"
                    else "run_failed"
                )
                emit(engine, settings.worker_status_id, code, context={"status": outcome, **counts})
            except StakeDeferred as error:
                now = datetime.now(UTC)
                with Session(engine) as db, db.begin():
                    if error.retry_at <= now.timestamp():
                        # No cooldown: finish this run and let the next cron tick retry.
                        db.execute(
                            update(ScriptRun)
                            .where(ScriptRun.id == run_id)
                            .values(
                                status="failed",
                                finished_at=now,
                                error="Stake : accès refusé par la source.",
                            )
                        )
                    else:
                        db.execute(
                            update(ScriptRun)
                            .where(ScriptRun.id == run_id)
                            .values(
                                status="queued",
                                started_at=None,
                                available_at=datetime.fromtimestamp(error.retry_at, UTC),
                                error="Stake différé : délai source ou budget en attente.",
                            )
                        )
                emit(
                    engine,
                    settings.worker_status_id,
                    "run_failed" if error.retry_at <= now.timestamp() else "run_deferred",
                    context={"retryAt": datetime.fromtimestamp(error.retry_at, UTC)},
                )
            except LoltvBlocked as error:
                retry_at = (
                    datetime.fromtimestamp(error.retry_at, UTC)
                    if error.retry_at
                    else datetime.now(UTC)
                    + timedelta(seconds=settings.loltv_block_cooldown_seconds)
                )
                logger.warning("Loltv deferred until %s (%s)", retry_at.isoformat(), error.reason)
                with Session(engine) as db, db.begin():
                    db.execute(
                        update(ScriptRun)
                        .where(ScriptRun.id == run_id)
                        .values(
                            status="queued",
                            started_at=None,
                            available_at=retry_at,
                            error="Loltv indisponible. Reprise après le délai source.",
                        )
                    )
                emit(
                    engine, settings.worker_status_id, "run_deferred", context={"retryAt": retry_at}
                )
            except CollectionBusy:
                with Session(engine) as db, db.begin():
                    db.execute(
                        update(ScriptRun)
                        .where(ScriptRun.id == run_id)
                        .values(
                            status="queued",
                            started_at=None,
                            available_at=datetime.now(UTC) + timedelta(seconds=60),
                        )
                    )
                emit(engine, settings.worker_status_id, "run_busy")
            except Exception as error:
                logger.error("Script %s failed (%s)", script_id, type(error).__name__)
                with Session(engine) as db, db.begin():
                    db.execute(
                        update(ScriptRun)
                        .where(ScriptRun.id == run_id)
                        .values(
                            status="failed",
                            finished_at=datetime.now(UTC),
                            error="La collecte a échoué. Consultez les journaux du worker.",
                        )
                    )
                emit(engine, settings.worker_status_id, "run_failed", context=error_context(error))
            finally:
                binding.reset()


def serve_schedules(
    engine: Engine,
    settings: Settings,
    only: list[str] | None,
    stopping: threading.Event,
    path: Path,
) -> None:
    scripts = enabled_scripts(settings, only)
    heartbeat(engine, scripts, path, settings.worker_status_id)
    prune(engine)
    emit(engine, settings.worker_status_id, "worker_started")

    def pulse() -> None:
        last_prune = time.monotonic()
        while not stopping.wait(20):
            try:
                heartbeat(engine, scripts, path, settings.worker_status_id)
            except Exception as error:
                logger.error("Worker heartbeat failed (%s)", type(error).__name__)
                emit(
                    engine,
                    settings.worker_status_id,
                    "heartbeat_failed",
                    context=error_context(error),
                )
            if time.monotonic() - last_prune >= 3600:
                prune(engine)
                last_prune = time.monotonic()

    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()

    def source_loop(group: list[str]) -> None:
        try:
            while not stopping.is_set():
                try:
                    tick(engine, settings, group, stopping)
                except CollectionBusy:
                    logger.info("Another scheduler owns the queue")
                except Exception as error:
                    logger.error("Scheduler failed (%s)", type(error).__name__)
                    emit(
                        engine,
                        settings.worker_status_id,
                        "scheduler_failed",
                        context=error_context(error),
                    )
                stopping.wait(5)
        finally:
            if "loltv-matches" in group:
                close_browser()

    # Independent sources keep separate browser threads and durable locks.
    # A large Oracle ZIP must not suspend the Loltv live refresh queue.
    workers = [
        threading.Thread(
            target=source_loop,
            args=([key for key in scripts if SCRIPTS[key].source == source],),
            daemon=True,
            name=f"collector-{source}",
        )
        for source in SOURCE_SCHEDULER_LOCKS
        if any(SCRIPTS[key].source == source for key in scripts)
    ]
    for worker in workers:
        worker.start()
    try:
        while not stopping.wait(1):
            if settings.worker_stop_file and settings.worker_stop_file.exists():
                stopping.set()
    finally:
        stopping.set()
        for worker in workers:
            worker.join(
                timeout=settings.stake_timeout_seconds + 10 if settings.stake_enabled else 5
            )
        thread.join(timeout=5)
        emit(engine, settings.worker_status_id, "worker_stopped")
