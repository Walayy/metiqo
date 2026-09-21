import copy
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from metiquo_api.main import _snapshot_score
from metiquo_core.config import Settings
from metiquo_core.matches import merge_completed_map
from metiquo_core.models import (
    EsportMatch,
    IngestionRun,
    League,
    MatchSnapshot,
    ScriptRun,
    ScriptSchedule,
)
from metiquo_worker import scheduler, sofascore_sync
from metiquo_worker.matching import normalize_name, resolve_team
from metiquo_worker.oracle_match_sync import _date_ranges
from metiquo_worker.sofascore_policy import SofaScoreBlocked, SofaScorePolicy, retry_after_seconds
from metiquo_worker.sources import sofascore
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from test_live_regressions import event, identities, snapshot


def test_retry_after_accepts_seconds_and_http_date():
    now = datetime(2026, 9, 21, 10, tzinfo=UTC).timestamp()
    assert retry_after_seconds("3600", now) == 3600
    assert retry_after_seconds("Mon, 21 Sep 2026 11:00:00 GMT", now) == 3600
    assert retry_after_seconds("Mon, 21 Sep 2026 09:00:00 GMT", now) == 0
    assert retry_after_seconds("not a date", now) == 0


def test_unicode_identities_and_distinct_rosters_are_not_collapsed():
    assert normalize_name("雷霆戰隊") == "雷霆戰隊"
    _, home, _ = identities()
    home.data = {"name": "Alpha Gaming"}
    assert resolve_team("Alpha Esports", [home]).team_id == home.id
    for name in ["Gaming", "Alpha B", "Alpha 2", "Alpha Prime", "Alpha Academy"]:
        assert resolve_team(name, [home]) is None


def test_postponed_event_is_rechecked_for_resumption_and_unknown_status_stays_unknown(monkeypatch):
    observed = replace(event(), status="postponed")
    monkeypatch.setattr(
        sofascore,
        "_STATE",
        sofascore._ScrapeState(events={"42": observed}, event_fetched_at={"42": 1.0}),
    )
    link = sofascore.SofaLink(observed.url, "42", observed.starts_at.date(), "Alpha Beta")
    settings = Settings(database_url="postgresql+psycopg://test@localhost/test")
    assert not sofascore._should_refresh_event(link, 120.0, settings)
    assert sofascore._should_refresh_event(link, 182.0, settings)
    assert sofascore._status({"status": {"type": "canceled"}}) == "cancelled"
    assert sofascore._status({"status": {"type": "interrupted"}}) == "postponed"
    assert sofascore._status({"status": {"type": "new-unknown-state"}}) is None


def test_stage_uses_explicit_parent_brand_even_when_its_name_is_generic():
    parent = League(
        id="lck-cl", data={"name": "LCK Challengers", "slug": "lck-cl", "image": "/logo.png"}
    )
    brand = sofascore_sync._competition_brand_from_source(
        "Playoffs", {"event": {"tournament": {"uniqueTournament": {"slug": "lck-cl"}}}}, [parent]
    )
    assert brand is parent


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


def test_checkpoint_survives_a_new_monotonic_clock_without_new_observation(monkeypatch):
    observed = event()
    monkeypatch.setattr(sofascore.clock, "time", lambda: 100000)
    monkeypatch.setattr(sofascore.clock, "monotonic", lambda: 5000)
    monkeypatch.setattr(
        sofascore,
        "_STATE",
        sofascore._ScrapeState(
            listing_days=(observed.starts_at.date(),),
            events={"42": observed},
            event_fetched_at={"42": 4990},
            day_fetched_at={observed.starts_at.date().isoformat(): 4990},
            fresh=[observed],
        ),
    )
    saved = sofascore.checkpoint()
    monkeypatch.setattr(sofascore.clock, "time", lambda: 100100)
    monkeypatch.setattr(sofascore.clock, "monotonic", lambda: 100)
    sofascore.restore_checkpoint(saved)
    assert sofascore._STATE.events["42"] == observed
    assert sofascore._STATE.event_fetched_at["42"] == -10
    assert not sofascore._STATE.fresh


def test_oracle_preserves_extra_sofascore_fields_without_overriding_explicit_zero():
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
    monkeypatch.setattr("metiquo_worker.sofascore_policy.time.time", lambda: now)
    policy = SofaScorePolicy(engine, settings)
    blocked = policy.block(429, "test-source", "3600")
    assert blocked.retry_at == now + 3600
    policy.checkpoint({"listing_cursor": 4})
    fresh_process = SofaScorePolicy(engine, settings)
    with pytest.raises(SofaScoreBlocked):
        fresh_process.before_request()
    assert fresh_process.read()["checkpoint"] == {"listing_cursor": 4}
    assert fresh_process.block(403, "parallel-response").retry_at == blocked.retry_at
    assert fresh_process.read()["consecutiveBlocks"] == 1
    monkeypatch.setattr("metiquo_worker.sofascore_policy.time.time", lambda: now + 3601)
    fresh_process.block(
        403,
        "still-refused",
        request_url="https://www.sofascore.com/api/v1/event/42?token=secret#fragment",
        resource_type="xhr",
    )
    assert fresh_process.read()["consecutiveBlocks"] == 2
    assert fresh_process.read()["blockedUntil"] == now + 3601 + 1800
    assert fresh_process.read()["lastBlockUrl"] == "https://www.sofascore.com/api/v1/event/42"
    assert fresh_process.read()["lastBlockResourceType"] == "xhr"


@pytest.mark.integration
def test_partial_batch_is_published_and_restart_cannot_retry_during_block(database, monkeypatch):
    engine, settings = database
    settings.sofascore_enabled = True
    monkeypatch.setattr(sofascore, "_STATE", sofascore._ScrapeState())
    monkeypatch.setattr(sofascore, "_POLICY", None)
    monkeypatch.setattr(sofascore, "idle_browser", lambda: None)
    calls = []

    def scrape(*args, **kwargs):
        calls.append(1)
        sofascore._STATE.fresh = [replace(event(), status="scheduled")]
        raise sofascore._POLICY.block(403, "http-403")

    monkeypatch.setattr(sofascore_sync, "scrape", scrape)
    for _ in range(2):
        with pytest.raises(SofaScoreBlocked):
            sofascore_sync.sync_sofascore(engine, settings)
    assert len(calls) == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MatchSnapshot)) == 1
        runs = list(db.scalars(select(IngestionRun)))
        assert len(runs) == 1 and runs[0].status == "failed"
        assert runs[0].details["events"] == 1


@pytest.mark.integration
def test_scheduler_defers_one_job_without_repeated_failure_rows(database, monkeypatch):
    engine, settings = database
    with Session(engine) as db, db.begin():
        db.execute(
            update(ScriptSchedule)
            .where(ScriptSchedule.id == "sofascore-matches")
            .values(next_run_at=datetime.now(UTC) - timedelta(hours=1))
        )
    calls = []

    def refused(*args):
        calls.append(1)
        raise SofaScorePolicy(engine, settings).block(403, "http-403")

    monkeypatch.setattr(scheduler, "sync_sofascore", refused)
    for _ in range(2):
        scheduler.tick(engine, settings, ["sofascore-matches"], threading.Event())
    assert len(calls) == 1
    with Session(engine) as db:
        runs = list(db.scalars(select(ScriptRun)))
        assert len(runs) == 1 and runs[0].status == "queued"
        assert runs[0].available_at > datetime.now(UTC)


@pytest.mark.integration
def test_oracle_work_does_not_block_sofascore_or_mark_it_interrupted(database, monkeypatch):
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
    monkeypatch.setattr(scheduler, "sync_sofascore", lambda *args: record("sofascore"))
    worker = threading.Thread(
        target=scheduler.tick, args=(engine, settings, ["oracle-latest"], threading.Event())
    )
    worker.start()
    try:
        assert started.wait(5)
        scheduler.tick(engine, settings, ["sofascore-matches"], threading.Event())
        with Session(engine) as db:
            states = {run.script_id: run.status for run in db.scalars(select(ScriptRun))}
            assert states == {"oracle-latest": "running", "sofascore-matches": "succeeded"}
    finally:
        release.set()
        worker.join(10)
