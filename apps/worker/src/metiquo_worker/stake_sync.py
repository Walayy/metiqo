"""Scheduled public Stake collection, including live markets and suspensions."""

import logging
import traceback
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from metiquo_core.config import Settings
from metiquo_core.models import BookmakerQuote, BookmakerSnapshot, IngestionRun, ScriptRun
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from metiquo_worker.jobs import source_lock, start_run
from metiquo_worker.stake_browser import (
    StakeBrowser,
    StakeCycleComplete,
    StakeEventStopped,
    StakeEventTransition,
)
from metiquo_worker.stake_policy import StakeDeferred, StakePolicy
from metiquo_worker.stake_storage import known_events, publish, remember_event, remember_events
from metiquo_worker.worker_logs import emit, error_context

logger = logging.getLogger(__name__)
SOURCE_LOCK = 62883404


def sync_stake(engine: Engine, settings: Settings, *, script_run_id: UUID | None = None) -> UUID:
    if not settings.stake_enabled:
        raise ValueError("Stake collection is not enabled in this worker")
    with source_lock(engine, SOURCE_LOCK):
        policy = StakePolicy(engine, settings)
        policy.check()
        run_id = start_run(engine, "stake", "markets:" + ",".join(settings.stake_games))
        metrics: dict[str, int] = {
            "eventsScanned": 0,
            "eventsCollected": 0,
            "liveEvents": 0,
            "eventsStopped": 0,
            "eventsFailed": 0,
            "markets": 0,
            "selections": 0,
            "quotes": 0,
            "openQuotes": 0,
            "suspendedQuotes": 0,
            "snapshots": 0,
        }
        event_errors: list[dict[str, str]] = []
        details: dict[str, object] = {
            "mode": "scheduled-and-live",
            "games": settings.stake_games,
            "eventErrors": event_errors,
        }
        stage = "browser_start"
        current_event: str | None = None

        def progress(browser: StakeBrowser | None = None) -> None:
            with Session(engine) as db, db.begin():
                row = db.get(IngestionRun, run_id)
                assert row is not None
                row.details = {
                    **row.details,
                    **details,
                    **metrics,
                    **(
                        {"requestEvents": browser.requests, "refusals": browser.refusals}
                        if browser
                        else {}
                    ),
                }

        def finish(failure: Exception | None = None) -> bool:
            details["complete"] = bool(details.get("complete", True)) and not (
                metrics["eventsFailed"] or failure
            )
            with Session(engine) as db, db.begin():
                run = db.get(IngestionRun, run_id)
                assert run is not None
                persisted_snapshots = db.scalar(
                    select(func.count())
                    .select_from(BookmakerSnapshot)
                    .where(BookmakerSnapshot.run_id == run_id)
                )
                persisted_quotes = db.scalar(
                    select(func.count())
                    .select_from(BookmakerQuote)
                    .join(BookmakerSnapshot, BookmakerQuote.snapshot_id == BookmakerSnapshot.id)
                    .where(BookmakerSnapshot.run_id == run_id)
                )
                metrics["snapshots"] = persisted_snapshots or 0
                metrics["quotes"] = persisted_quotes or 0
                succeeded = bool(persisted_snapshots) or not (failure or metrics["eventsFailed"])
                run.details = {**run.details, **details, **metrics}
                run.status = "succeeded" if succeeded else "failed"
                run.finished_at = datetime.now(UTC)
                if succeeded:
                    run.error = None
                elif failure:
                    run.error = f"stake_collection: {type(failure).__name__}"
                else:
                    run.error = "No event snapshots were published; previous data preserved"
                return succeeded

        if script_run_id:
            with Session(engine) as db, db.begin():
                script = db.get(ScriptRun, script_run_id)
                assert script is not None
                script.ingestion_run_id = run_id
        progress()
        try:
            with StakeBrowser(settings, policy) as browser:
                browser.on_discovery = lambda events: remember_events(engine, events)
                try:
                    for game in settings.stake_games:
                        stage, current_event = "listing", None
                        fixtures = browser.fixtures(game)
                        remember_events(engine, fixtures)
                        known = known_events(engine, game)
                        fixtures.sort(
                            key=lambda event: (
                                0 if event.status == "live" else 1,
                                known.get(event.source_id, (None, False, 0))[2],
                                event.source_id,
                            )
                        )
                        metrics["eventsScanned"] += len(fixtures)
                        for fixture in fixtures:
                            current_event = fixture.source_id
                            _, stopped, _ = known.get(fixture.source_id, (None, False, 0))
                            if stopped:
                                metrics["eventsStopped"] += 1
                                current_event = None
                                continue
                            try:
                                stage = "event_traversal"
                                for attempt in range(2):
                                    try:
                                        captures, closing = browser.event(fixture)
                                        break
                                    except StakeEventTransition as error:
                                        remember_event(engine, error.metadata)
                                        if error.metadata.status != "live" or attempt:
                                            raise ValueError(str(error)) from error
                                stage = "publication"
                                counts = publish(
                                    engine,
                                    run_id,
                                    captures,
                                    closing,
                                    guard_seconds=settings.stake_start_guard_seconds,
                                )
                                metrics["eventsCollected"] += 1
                                metrics["liveEvents"] += int(closing.status == "live")
                                for key, count in counts.items():
                                    metrics[key] += count
                                if counts["snapshots"]:
                                    emit(
                                        engine,
                                        settings.worker_status_id,
                                        "stake_event_published",
                                        event_id=fixture.source_id,
                                        context={
                                            "snapshots": counts["snapshots"],
                                            "quotes": counts["quotes"],
                                            "markets": counts["markets"],
                                        },
                                    )
                            except StakeEventStopped as error:
                                remember_event(engine, error.metadata, stop_reason=error.reason)
                                metrics["eventsStopped"] += 1
                            except ValueError as error:
                                metrics["eventsFailed"] += 1
                                event_errors.append(
                                    {"eventId": fixture.source_id, "reason": str(error)[:200]}
                                )
                                logger.warning(
                                    "Stake event %s not published (%s)",
                                    fixture.source_id,
                                    str(error)[:200],
                                )
                                emit(
                                    engine,
                                    settings.worker_status_id,
                                    "stake_market_ambiguous"
                                    if str(error) == "Ambiguous source market identity"
                                    else "stake_event_rejected",
                                    event_id=fixture.source_id,
                                    context={"kind": type(error).__name__},
                                )
                            progress(browser)
                            current_event = None
                        details["complete"] = metrics["eventsFailed"] == 0
                except StakeCycleComplete as error:
                    details["complete"] = False
                    details["deferredReason"] = str(error)
                finally:
                    progress(browser)
            finish()
            return run_id
        except StakeDeferred as error:
            details.update(
                {"complete": False, "deferredReason": error.reason, "retryAt": error.retry_at}
            )
            if finish(error):
                return run_id
            raise
        except Exception as error:
            frames = [
                f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}"
                for frame in traceback.extract_tb(error.__traceback__)[-8:]
            ]
            details["interruption"] = {
                "stage": stage,
                "eventId": current_event,
                "kind": type(error).__name__,
                "frames": frames,
            }
            logger.error(
                "Stake collection interrupted (stage=%s, event=%s, kind=%s, frames=%s)",
                stage,
                current_event,
                type(error).__name__,
                frames,
            )
            emit(
                engine,
                settings.worker_status_id,
                "stake_cycle_interrupted",
                event_id=current_event,
                context={**error_context(error), "step": stage},
            )
            if finish(error):
                return run_id
            raise
