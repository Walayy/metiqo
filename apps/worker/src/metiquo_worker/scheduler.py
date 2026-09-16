"""Persistent scheduler. Only registered collectors can be dispatched; never a shell command."""

import logging
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from metiquo_core.config import Settings
from metiquo_core.models import IngestionRun, ScriptRun, ScriptSchedule, WorkerStatus
from metiquo_core.scheduling import SCRIPTS, upcoming
from sqlalchemy import Engine, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from metiquo_worker.catalog_sync import sync_catalog
from metiquo_worker.ingestion import collect
from metiquo_worker.jobs import CollectionBusy, source_lock

logger = logging.getLogger(__name__)
SCHEDULER_LOCK = 62883200


def enabled_scripts(settings: Settings, only: list[str] | None) -> list[str]:
    return [
        key
        for key, definition in SCRIPTS.items()
        if (settings.catalog_enabled if key == "lol-catalog" else settings.oracle_enabled)
        and (not only or definition.source in only)
    ]


def heartbeat(engine: Engine, scripts: list[str], path: Path) -> None:
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        db.execute(
            insert(WorkerStatus)
            .values(id=1, seen_at=now, scripts=scripts)
            .on_conflict_do_update(
                index_elements=[WorkerStatus.id], set_={"seen_at": now, "scripts": scripts}
            )
        )
    path.touch()


def tick(engine: Engine, settings: Settings, scripts: list[str], stopping: threading.Event) -> None:
    # This connection-level lock spans dispatch and execution, so another worker cannot
    # mistake a live run for an interrupted one or claim the same queue entry.
    with source_lock(engine, SCHEDULER_LOCK):
        now = datetime.now(UTC)
        with Session(engine) as db, db.begin():
            db.execute(
                update(ScriptRun)
                .where(ScriptRun.status == "running")
                .values(
                    status="interrupted",
                    finished_at=now,
                    error="Exécution interrompue par un arrêt du worker.",
                )
            )
            rows = db.scalars(
                select(ScriptSchedule)
                .where(ScriptSchedule.id.in_(scripts))
                .order_by(ScriptSchedule.id)
                .with_for_update()
            ).all()
            for row in rows:
                if row.enabled and row.next_run_at <= now:
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
        for run_id in ids:
            if stopping.is_set():
                break
            with Session(engine) as db, db.begin():
                run = db.get(ScriptRun, run_id, with_for_update=True)
                assert run is not None
                script_id = run.script_id
                run.status, run.started_at = "running", datetime.now(UTC)
            try:
                if script_id == "lol-catalog":
                    ingestion_id = sync_catalog(engine, settings)
                elif script_id in {"oracle-latest", "oracle-full"}:
                    ingestion_id = collect(engine, settings, latest=script_id == "oracle-latest")
                else:
                    raise ValueError("Unregistered script")
                with Session(engine) as db, db.begin():
                    run = db.get(ScriptRun, run_id)
                    ingestion = db.get(IngestionRun, ingestion_id)
                    assert run is not None and ingestion is not None
                    run.ingestion_run_id = ingestion_id
                    run.status = ingestion.status
                    run.finished_at = datetime.now(UTC)
                    if ingestion.status != "succeeded":
                        run.error = "La collecte a échoué. Consultez les journaux du worker."
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


def serve_schedules(
    engine: Engine,
    settings: Settings,
    only: list[str] | None,
    stopping: threading.Event,
    path: Path,
) -> None:
    scripts = enabled_scripts(settings, only)
    heartbeat(engine, scripts, path)

    def pulse() -> None:
        while not stopping.wait(20):
            try:
                heartbeat(engine, scripts, path)
            except Exception as error:
                logger.error("Worker heartbeat failed (%s)", type(error).__name__)

    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    try:
        while not stopping.is_set():
            try:
                tick(engine, settings, scripts, stopping)
            except CollectionBusy:
                logger.info("Another scheduler owns the queue")
            except Exception as error:
                logger.error("Scheduler failed (%s)", type(error).__name__)
            stopping.wait(5)
    finally:
        stopping.set()
        thread.join(timeout=5)
