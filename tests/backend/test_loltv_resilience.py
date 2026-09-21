import copy
import threading
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from metiquo_api.main import _snapshot_score
from metiquo_core.matches import merge_completed_map
from metiquo_core.models import (
    CollectorState,
    EsportMatch,
    IngestionRun,
    ScriptRun,
    ScriptSchedule,
)
from metiquo_worker import scheduler
from metiquo_worker.loltv_policy import (
    LoltvBlocked,
    LoltvBudgetExhausted,
    LoltvPolicy,
    retry_after_seconds,
)
from metiquo_worker.loltv_sync import next_live_due
from metiquo_worker.matching import normalize_name, resolve_team
from metiquo_worker.oracle_match_sync import _date_ranges
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from test_live_regressions import identities, snapshot


def test_retry_after_accepts_seconds_and_http_date():
    now = datetime(2026, 9, 21, 10, tzinfo=UTC).timestamp()
    assert retry_after_seconds("3600", now) == 3600
    assert retry_after_seconds("Mon, 21 Sep 2026 11:00:00 GMT", now) == 3600
    assert retry_after_seconds("Mon, 21 Sep 2026 09:00:00 GMT", now) == 0
    assert retry_after_seconds("not a date", now) == 0


def test_live_wakeup_respects_refusals_budget_and_failed_cycle_floor():
    from metiquo_core.config import Settings

    settings = Settings(database_url="postgresql+psycopg://unused/unused_test")
    state = {
        "checkpoint": {
            "cycleStartedAt": 100,
            "events": {
                "live": {"event": {"status": "live"}, "due": 120},
                "past": {"event": {"status": "finished"}, "due": 0},
            },
        }
    }
    assert next_live_due(state, settings) == 120  # No extra cron-minute rounding.
    assert next_live_due({**state, "blockedUntil": 500}, settings) == 500
    assert next_live_due({**state, "budgetStart": 100, "budgetCount": 120}, settings) == 700
    state["checkpoint"]["events"]["live"]["due"] = 0
    assert next_live_due(state, settings) == 130  # A failed cycle cannot busy-loop.


@pytest.mark.integration
@pytest.mark.parametrize(
    "cron,enabled,expected",
    [
        ("*/1 * * * *", True, 1),
        ("* * * * *", True, 1),
        ("*/5 * * * *", True, 0),
        ("*/1 * * * *", False, 0),
    ],
)
def test_live_deadline_wakes_default_schedule_but_honors_pause_and_custom_cron(
    database, monkeypatch, cron, enabled, expected
):
    engine, settings = database
    now = datetime.now(UTC)
    state = {
        "checkpoint": {
            "cycleStartedAt": now.timestamp() - 100,
            "events": {"live": {"event": {"status": "live"}, "due": now.timestamp() - 1}},
        }
    }
    with Session(engine) as db, db.begin():
        db.execute(
            update(ScriptSchedule)
            .where(ScriptSchedule.id == "loltv-matches")
            .values(enabled=enabled, cron=cron, next_run_at=now + timedelta(minutes=1))
        )
        db.add(CollectorState(source="loltv", data=state))
    calls = []

    def collect(*_):
        calls.append(1)
        run_id = uuid4()
        with Session(engine) as db, db.begin():
            db.add(IngestionRun(id=run_id, source="loltv", scope="test", status="succeeded"))
            row = db.get(CollectorState, "loltv")
            row.data = {
                "checkpoint": {
                    "events": {"live": {"event": {"status": "live"}, "due": now.timestamp() + 30}}
                }
            }
        return run_id

    monkeypatch.setattr(scheduler, "sync_loltv", collect)
    for _ in range(2):
        scheduler.tick(engine, settings, ["loltv-matches"], threading.Event())
    assert len(calls) == expected


def test_unicode_identities_and_distinct_rosters_are_not_collapsed():
    assert normalize_name("雷霆戰隊") == "雷霆戰隊"
    _, home, _ = identities()
    home.data = {"name": "Alpha Gaming"}
    assert resolve_team("Alpha Esports", [home]).team_id == home.id
    for name in ["Gaming", "Alpha B", "Alpha 2", "Alpha Prime", "Alpha Academy"]:
        assert resolve_team(name, [home]) is None


def test_oracle_score_follows_current_team_orientation():
    match = EsportMatch(id=uuid4(), home_id="home", away_id="away", format="BO1")
    observed = snapshot(match, 1)
    observed.source = "oracles-elixir"
    observed.payload["seriesScore"] = {"home": 1, "away": 0}
    assert _snapshot_score(observed, match) == {"home": 1, "away": 0}
    match.home_id, match.away_id = match.away_id, match.home_id
    assert _snapshot_score(observed, match) == {"home": 0, "away": 1}


def test_oracle_lookup_merges_overlapping_windows_and_preserves_year_boundaries():
    matches = [
        EsportMatch(id=uuid4(), starts_at=datetime(2026, 12, day, 12, tzinfo=UTC))
        for day in (31, 1, 2)
    ]
    ranges = _date_ranges(matches)
    assert [(first.isoformat(), last.isoformat()) for first, last in ranges] == [
        ("2026-11-29", "2026-12-05"),
        ("2026-12-29", "2027-01-03"),
    ]


def test_oracle_preserves_extra_loltv_fields_without_overriding_explicit_zero():
    from metiquo_core.models import EsportMatch

    match = EsportMatch(id=uuid4(), home_id="home", away_id="away", format="BO3")
    old = snapshot(match, 1).payload["maps"][0]
    old["sides"][0].update(
        {
            "grubs": 3,
            "towers": 8,
            "players": [
                {
                    "role": "TOP",
                    "name": "Player",
                    "champion": "Gnar",
                    "level": 18,
                }
            ],
        }
    )
    current = copy.deepcopy(old)
    current["durationSeconds"] = 1800
    current["sides"][0].update(
        {
            "grubs": None,
            "towers": 0,
            "players": [
                {
                    "role": "TOP",
                    "name": "Player",
                    "champion": "Gnar",
                    "level": None,
                }
            ],
        }
    )
    merged = merge_completed_map(old, current)
    assert merged["durationSeconds"] == 1800
    assert merged["sides"][0]["towers"] == 0
    assert merged["sides"][0]["grubs"] == 3
    assert merged["sides"][0]["players"][0]["level"] == 18
    current["winnerId"] = "away"
    assert merge_completed_map(old, current) == current


@pytest.mark.integration
def test_cooldown_is_shared_after_restart_and_honors_retry_after(database, monkeypatch):
    engine, settings = database
    now = time.time()
    monkeypatch.setattr("metiquo_worker.loltv_policy.time.time", lambda: now)
    policy = LoltvPolicy(engine, settings)
    blocked = policy.block(429, "test-source", "3600")
    assert blocked.retry_at == now + 3600
    policy.checkpoint({"listing_cursor": 4})
    fresh_process = LoltvPolicy(engine, settings)
    with pytest.raises(LoltvBlocked):
        fresh_process.before_request()
    assert fresh_process.read()["checkpoint"] == {"listing_cursor": 4}
    assert fresh_process.block(403, "parallel-response").retry_at == blocked.retry_at
    assert fresh_process.read()["consecutiveBlocks"] == 1
    monkeypatch.setattr("metiquo_worker.loltv_policy.time.time", lambda: now + 3601)
    fresh_process.block(
        403,
        "still-refused",
        request_url="https://feed.loltv.gg/feed/42?token=secret#fragment",
        resource_type="xhr",
    )
    assert fresh_process.read()["consecutiveBlocks"] == 2
    assert fresh_process.read()["blockedUntil"] == now + 3601 + 1800
    assert fresh_process.read()["lastBlockUrl"] == "https://feed.loltv.gg/feed/42"
    assert fresh_process.read()["lastBlockResourceType"] == "xhr"


@pytest.mark.integration
def test_explicit_and_browser_budgets_survive_process_restart(database, monkeypatch):
    engine, settings = database
    settings = settings.model_copy(
        update={"loltv_request_budget": 2, "loltv_browser_request_budget": 2}
    )
    clock = [time.time()]
    monkeypatch.setattr("metiquo_worker.loltv_policy.time.time", lambda: clock[0])
    policy = LoltvPolicy(engine, settings)
    policy.before_request()
    clock[0] += 5
    LoltvPolicy(engine, settings).before_request()
    with pytest.raises(LoltvBudgetExhausted):
        LoltvPolicy(engine, settings).before_request()
    policy.browser_request()
    with pytest.raises(LoltvBudgetExhausted):
        LoltvPolicy(engine, settings).browser_request()
    with pytest.raises(LoltvBudgetExhausted):
        LoltvPolicy(engine, settings).check()
    clock[0] += settings.loltv_budget_window_seconds
    policy.check()
    policy.before_request()
    assert policy.read()["budgetCount"] == 1


def test_later_empty_game_record_keeps_acquired_players_but_not_a_remake():
    old = {
        "number": 1,
        "status": "finished",
        "winnerId": "home",
        "sourceGameId": "g1",
        "sides": [{"teamId": "home", "players": [{"name": f"p{i}"} for i in range(5)]}],
    }
    current = {**old, "sides": [{"teamId": "home", "players": []}]}
    assert len(merge_completed_map(old, current)["sides"][0]["players"]) == 5
    current["sourceGameId"] = "remade-g1"
    assert merge_completed_map(old, current)["sides"][0]["players"] == []


@pytest.mark.integration
def test_scheduler_defers_one_job_without_repeated_failure_rows(database, monkeypatch):
    engine, settings = database
    with Session(engine) as db, db.begin():
        db.execute(
            update(ScriptSchedule)
            .where(ScriptSchedule.id == "loltv-matches")
            .values(next_run_at=datetime.now(UTC) - timedelta(hours=1))
        )
    calls = []

    def refused(*args):
        calls.append(1)
        raise LoltvPolicy(engine, settings).block(403, "http-403")

    monkeypatch.setattr(scheduler, "sync_loltv", refused)
    for _ in range(2):
        scheduler.tick(engine, settings, ["loltv-matches"], threading.Event())
    assert len(calls) == 1
    with Session(engine) as db:
        runs = list(db.scalars(select(ScriptRun)))
        assert len(runs) == 1 and runs[0].status == "queued"
        assert runs[0].available_at > datetime.now(UTC)


@pytest.mark.integration
def test_oracle_work_does_not_block_loltv_or_mark_it_interrupted(database, monkeypatch):
    engine, settings = database
    started, release = threading.Event(), threading.Event()
    with Session(engine) as db, db.begin():
        db.execute(
            update(ScriptSchedule).values(next_run_at=datetime.now(UTC) - timedelta(hours=1))
        )

    def record(source):
        run_id = uuid4()
        with Session(engine) as db, db.begin():
            db.add(IngestionRun(id=run_id, source=source, scope="test", status="succeeded"))
        return run_id

    def slow(*args, **kwargs):
        started.set()
        assert release.wait(10)
        return record("oracles-elixir")

    monkeypatch.setattr(scheduler, "collect", slow)
    monkeypatch.setattr(scheduler, "sync_loltv", lambda *args: record("loltv"))
    worker = threading.Thread(
        target=scheduler.tick, args=(engine, settings, ["oracle-latest"], threading.Event())
    )
    worker.start()
    try:
        assert started.wait(5)
        scheduler.tick(engine, settings, ["loltv-matches"], threading.Event())
        with Session(engine) as db:
            states = {run.script_id: run.status for run in db.scalars(select(ScriptRun))}
            assert states == {"oracle-latest": "running", "loltv-matches": "succeeded"}
    finally:
        release.set()
        worker.join(10)
