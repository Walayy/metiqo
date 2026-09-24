"""Scheduled public Stake collection, including live markets and suspensions."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from metiquo_core.config import Settings
from metiquo_core.models import IngestionRun, ScriptRun
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from metiquo_worker.jobs import fail_run, source_lock, start_run
from metiquo_worker.stake_browser import (
    StakeBrowser,
    StakeCycleComplete,
    StakeEventStopped,
    StakeEventTransition,
)
from metiquo_worker.stake_policy import StakeDeferred, StakePolicy
from metiquo_worker.stake_storage import known_events, publish, remember_event, remember_events

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
        details: dict[str, object] = {"mode": "scheduled-and-live", "games": settings.stake_games}

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
                            _, stopped, _ = known.get(fixture.source_id, (None, False, 0))
                            if stopped:
                                metrics["eventsStopped"] += 1
                                continue
                            try:
                                for attempt in range(2):
                                    try:
                                        captures, closing = browser.event(fixture)
                                        break
                                    except StakeEventTransition as error:
                                        remember_event(engine, error.metadata)
                                        if error.metadata.status != "live" or attempt:
                                            raise ValueError(str(error)) from error
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
                            except StakeEventStopped as error:
                                remember_event(engine, error.metadata, stop_reason=error.reason)
                                metrics["eventsStopped"] += 1
                            except ValueError as error:
                                metrics["eventsFailed"] += 1
                                logger.warning(
                                    "Stake event %s not published (%s)",
                                    fixture.source_id,
                                    str(error)[:200],
                                )
                            progress(browser)
                        details["complete"] = metrics["eventsFailed"] == 0
                except StakeCycleComplete as error:
                    details["complete"] = False
                    details["deferredReason"] = str(error)
                finally:
                    progress(browser)
            with Session(engine) as db, db.begin():
                run = db.get(IngestionRun, run_id)
                assert run is not None
                run.status = "succeeded" if not metrics["eventsFailed"] else "failed"
                run.finished_at = datetime.now(UTC)
                if metrics["eventsFailed"]:
                    run.error = "Some event snapshots were incomplete; previous data preserved"
            return run_id
        except StakeDeferred as error:
            details.update(
                {"complete": False, "deferredReason": error.reason, "retryAt": error.retry_at}
            )
            progress()
            fail_run(engine, run_id, "source_deferred", error)
            raise
        except Exception as error:
            fail_run(engine, run_id, "stake_collection", error)
            raise
