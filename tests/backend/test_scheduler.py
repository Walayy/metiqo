import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from metiquo_core.config import Settings
from metiquo_core.models import IngestionRun, ScriptRun, ScriptSchedule
from metiquo_core.scheduling import upcoming
from metiquo_worker import scheduler
from sqlalchemy import select, update
from sqlalchemy.orm import Session


def test_cron_dates_use_paris_timezone_and_daylight_saving():
    assert upcoming("0 4 * * *", "Europe/Paris", datetime(2026, 3, 28, 4, tzinfo=UTC)) == [
        datetime(2026, 3, 29, 2, tzinfo=UTC),
        datetime(2026, 3, 30, 2, tzinfo=UTC),
        datetime(2026, 3, 31, 2, tzinfo=UTC),
    ]
    assert upcoming("0 4 * * *", "Europe/Paris", datetime(2026, 10, 24, 4, tzinfo=UTC))[
        0
    ] == datetime(2026, 10, 25, 3, tzinfo=UTC)
    assert upcoming("0 3 * * 1", "UTC", datetime(2026, 9, 16, tzinfo=UTC))[0] == datetime(
        2026, 9, 21, 3, tzinfo=UTC
    )


@pytest.mark.parametrize(
    "cron,zone",
    [
        ("* * * * * *", "UTC"),
        ("@hourly", "UTC"),
        ("0 0 31 2 *", "UTC"),
        ("70 0 * * *", "UTC"),
        ("* * * * *", "Mars/Base"),
        ("0 0 * * *; echo x", "UTC"),
    ],
)
def test_invalid_crons_are_rejected(cron, zone):
    with pytest.raises(ValueError):
        upcoming(cron, zone, datetime(2026, 1, 1, tzinfo=UTC))


def test_worker_environment_remains_a_hard_gate():
    settings = Settings(database_url="postgresql://unused", catalog_enabled=False)
    assert scheduler.enabled_scripts(settings, None) == ["oracle-latest", "oracle-full"]
    assert scheduler.enabled_scripts(settings, ["lol-catalog"]) == []


@pytest.mark.integration
def test_scheduler_coalesces_missed_runs_and_continues_after_failure(database, monkeypatch):
    engine, settings = database
    with Session(engine) as db, db.begin():
        db.execute(update(ScriptSchedule).values(next_run_at=datetime.now(UTC) - timedelta(days=8)))

    def fail(*_):
        raise RuntimeError("secret source diagnostic")

    calls = []

    def collect(*_, latest):
        calls.append(latest)
        run_id = uuid4()
        with Session(engine) as db, db.begin():
            db.add(
                IngestionRun(
                    id=run_id,
                    source="oracles-elixir",
                    scope="latest" if latest else "all",
                    status="succeeded",
                )
            )
        return run_id

    monkeypatch.setattr(scheduler, "sync_catalog", fail)
    monkeypatch.setattr(scheduler, "collect", collect)
    monkeypatch.setattr(scheduler, "sync_loltv", fail)
    for _ in range(2):
        scheduler.tick(engine, settings, list(scheduler.SCRIPTS), threading.Event())
    assert sorted(calls) == [False, True]
    with Session(engine) as db:
        runs = db.scalars(select(ScriptRun)).all()
        assert len(runs) == 4
        assert sorted(row.status for row in runs) == ["failed", "failed", "succeeded", "succeeded"]
        assert all("secret" not in (row.error or "") for row in runs)
        assert all(
            row.next_run_at > datetime.now(UTC) for row in db.scalars(select(ScriptSchedule))
        )


@pytest.mark.integration
def test_queued_manual_run_survives_pause_busy_source_and_restart(database, monkeypatch):
    engine, settings = database
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        db.execute(update(ScriptSchedule).values(enabled=False))
        run = ScriptRun(
            script_id="lol-catalog", trigger="manual", requested_at=now, available_at=now
        )
        db.add(run)
        db.flush()
        run_id = run.id

    def busy(*_):
        raise scheduler.CollectionBusy()

    monkeypatch.setattr(scheduler, "sync_catalog", busy)
    scheduler.tick(engine, settings, ["lol-catalog"], threading.Event())
    with Session(engine) as db, db.begin():
        run = db.get(ScriptRun, run_id)
        assert run.status == "queued" and run.available_at > now
        run.status = "running"
    scheduler.tick(engine, settings, ["lol-catalog"], threading.Event())
    with Session(engine) as db:
        assert db.get(ScriptRun, run_id).status == "interrupted"
