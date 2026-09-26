"""Regressions from the production incident of September 26, without source requests."""

import copy
import json
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from metiquo_api.admin import run_data
from metiquo_api.main import create_app
from metiquo_core.config import Settings
from metiquo_core.models import (
    IngestionRun,
    MatchSnapshot,
    ScriptRun,
    ScriptSchedule,
    WorkerLogEntry,
)
from metiquo_core.source_issues import historical_loltv_issues, safe_source_issues
from metiquo_worker import loltv_sync, scheduler
from metiquo_worker.loltv_diagnostics import LoltvSourceError, record_issue
from metiquo_worker.loltv_feed import AnonymousSessions, FeedReader
from metiquo_worker.loltv_policy import LoltvBlocked
from metiquo_worker.sources.loltv import ROOT_URL, listing
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from test_live_regressions import event
from test_loltv_pages import MemoryPolicy, captured, sample


def listing_document(states):
    """Synthetic transport with the actual provider's WALKOVER state."""
    rows = [
        {
            "id": str(index),
            "slug": f"fixture-{index}",
            "date": datetime.now(UTC).isoformat(),
            "state": state,
            "team1": {"id": "home", "name": "Alpha"},
            "team2": {"id": "away", "name": "Beta"},
            "stage": {"tournament": {"id": "cup", "name": "Cup"}},
            "team1_score": 1,
            "team2_score": 0,
            "best_of": 1,
        }
        for index, state in enumerate(states)
    ]
    links = "".join(f'<a href="/match/{row["slug"]}">Match</a>' for row in rows)
    transport = "a:" + json.dumps({"matches": rows}) + "\n"
    return (
        "<main>"
        + links
        + "</main><script>self.__next_f.push("
        + json.dumps([1, transport])
        + ")</script>"
    )


def test_walkover_is_published_without_inventing_played_games():
    rows, _, _ = listing(listing_document(["WALKOVER", "COMPLETED"]), ROOT_URL + "/matches/results")
    assert [row.status for row in rows] == ["walkover", "finished"]
    assert (rows[0].home_score, rows[0].away_score) == (1, 0)
    assert rows[0].payload["rendered"]["maps"] == []


def test_future_unknown_status_cannot_discard_the_other_matches_on_a_listing():
    metrics = {}
    rows, _, _ = listing(
        listing_document(["COMPLETED", "NEW_STATUS", "WALKOVER"]),
        ROOT_URL + "/matches/results",
        metrics=metrics,
    )
    assert [row.source_id for row in rows] == ["0", "2"]
    assert metrics["sourceIssues"][0]["code"] == "loltv_unknown_state"
    assert metrics["sourceIssues"][0]["eventId"] == "1"
    assert len(metrics["errors"]) == 1


@pytest.mark.parametrize("malformed", [None, "wrong_id", "started", "missing_teams"])
def test_empty_unstarted_feed_is_unavailable_but_invalid_frames_remain_errors(
    tmp_path, monkeypatch, malformed
):
    value = sample("detail")
    game = next(game for game in value.payload["sourceGames"] if game["state"] == "STARTED")
    acquired = {g["id"] for g in value.payload["sourceGames"] if g["id"] != game["id"]}
    metrics = {}
    reader = FeedReader(
        Settings(database_url="postgresql+psycopg://unused/unused_test", artifact_dir=tmp_path),
        MemoryPolicy(),
        {},
        metrics,
        AnonymousSessions(),
    )
    monkeypatch.setattr(reader, "discover", lambda *_: "a" * 40)
    raw = {
        "id": game["id"],
        "type": "feed",
        "state": "UNSTARTED",
        "timestamp": None,
        "teams": [],
        "events": [],
    }
    if malformed == "wrong_id":
        raw["id"] = "another-game"
    if malformed == "started":
        raw["state"] = "STARTED"
    if malformed == "missing_teams":
        del raw["teams"]
    calls, published = [], []

    def response(request):
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(
                200,
                headers={
                    "Set-Cookie": "loltv.scope=private; Domain=.loltv.gg; Path=/; Secure; HttpOnly"
                },
            )
        return httpx.Response(200, json=raw)

    before = copy.deepcopy(value)
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = reader.enrich(client, captured("detail"), value, acquired, published.append)
    assert calls == ["POST", "GET"]  # No loop or extra session after an empty frame.
    assert published == [] and result == before
    if malformed is None:
        assert metrics.get("errors", []) == []
        assert metrics["unavailableFeeds"] == 1
        assert metrics["sourceIssues"][0]["code"] == "loltv_feed_unavailable"
    else:
        assert len(metrics["errors"]) == 1
        assert metrics["sourceIssues"][0]["code"] == "loltv_feed_invalid"
    assert "private" not in json.dumps(metrics)


def test_source_diagnostics_allow_only_local_reasons_and_non_sensitive_paths():
    issues = safe_source_issues(
        [
            {
                "code": "loltv_feed_unavailable",
                "reason": "password=secret",
                "resource": "https://feed.loltv.gg/feed/card?token=secret",
                "eventId": "fixture",
                "sourceState": "UNSTARTED",
                "cookies": "secret",
            },
            {"code": ["invalid"]},
            {"code": "arbitrary", "reason": "secret"},
        ]
    )
    assert len(issues) == 1 and issues[0]["resource"] == "/feed/card"
    assert "secret" not in json.dumps(issues)
    legacy = historical_loltv_issues(
        [
            {
                "url": "https://loltv.gg/matches/results?token=secret",
                "message": "Unknown LoLTV match state: WALKOVER",
            }
        ]
    )
    assert legacy[0]["code"] == "loltv_unknown_state" and "secret" not in json.dumps(legacy)


def test_stale_pages_back_off_durably_then_reset_after_a_valid_read(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(loltv_sync.time, "time", lambda: clock[0])
    policy = MemoryPolicy()
    settings = Settings(database_url="postgresql+psycopg://unused/unused_test")
    url = ROOT_URL + "/matches/results"
    observed = []

    def prepare():
        collector = loltv_sync.Collector(None, settings, policy, uuid4())
        collector.pages = {url: collector.pages[url]}
        collector.state["pages"] = collector.pages
        monkeypatch.setattr(collector, "publish", observed.extend)
        return collector

    def stale(*_):
        raise LoltvSourceError("loltv_stale_listing", "Stale source", cacheAgeSeconds=3000000)

    first = prepare()
    monkeypatch.setattr(first, "fetch", stale)
    first.run()
    assert first.pages[url]["due"] == clock[0] + 900
    clock[0] += 901
    resumed = prepare()
    monkeypatch.setattr(resumed, "fetch", stale)
    resumed.run()
    assert resumed.pages[url]["due"] == clock[0] + 1800
    clock[0] += 1801
    recovered = prepare()
    monkeypatch.setattr(recovered, "fetch", lambda *_: listing_document(["WALKOVER"]))
    recovered.run()
    assert "sourceFailures" not in recovered.pages[url]
    assert len(observed) == 1 and observed[0].status == "walkover"


@pytest.mark.integration
@pytest.mark.parametrize(
    "published,fatal,expected",
    [
        (True, False, "succeeded"),
        (True, True, "succeeded"),
        (False, False, "failed"),
        (False, True, "failed"),
    ],
)
def test_run_outcome_tracks_committed_observations_and_retains_safe_incidents(
    database, monkeypatch, published, fatal, expected
):
    engine, settings = database
    monkeypatch.setattr(loltv_sync, "discover_archived_events", lambda *_: ([], []))

    def run(collector):
        if published:
            collector.publish([event()])
        record_issue(
            collector.details,
            ROOT_URL + "/matches/results",
            LoltvSourceError(
                "loltv_stale_listing", "unsafe-secret-message", cacheAgeSeconds=3000000
            ),
        )
        if fatal:
            raise RuntimeError("unsafe-secret-message")

    monkeypatch.setattr(loltv_sync.Collector, "run", run)
    with Session(engine) as db, db.begin():
        db.execute(
            update(ScriptSchedule)
            .where(ScriptSchedule.id == "loltv-matches")
            .values(next_run_at=datetime.now(UTC) - timedelta(minutes=1))
        )
    scheduler.tick(engine, settings, ["loltv-matches"], threading.Event())
    with Session(engine) as db:
        script = db.scalar(select(ScriptRun))
        ingestion = db.get(IngestionRun, script.ingestion_run_id)
        assert script.status == ingestion.status == expected
        assert ingestion.details["complete"] is False
        assert "unsafe-secret-message" not in json.dumps(ingestion.details)
        entries = list(db.scalars(select(WorkerLogEntry)))
        assert any(
            entry.code == ("run_partial" if published else "run_failed") for entry in entries
        )
        assert any(entry.code == "loltv_stale_listing" for entry in entries)
        if published:
            assert db.scalar(select(MatchSnapshot)) is not None
        response = run_data(script, ingestion)
        assert response["sourceIssues"][0]["cacheAgeSeconds"] == 3000000


@pytest.mark.integration
def test_refusal_after_publication_keeps_partial_success_and_persists_cooldown(
    database, monkeypatch
):
    engine, settings = database
    monkeypatch.setattr(loltv_sync, "discover_archived_events", lambda *_: ([], []))

    def run(collector):
        collector.publish([event()])
        raise collector.policy.block(429, "document", "3600")

    monkeypatch.setattr(loltv_sync.Collector, "run", run)
    run_id = loltv_sync.sync_loltv(engine, settings)
    with Session(engine) as db:
        run = db.get(IngestionRun, run_id)
        assert run.status == "succeeded" and run.details["complete"] is False
        assert run.details["blocked"] is True
    with pytest.raises(LoltvBlocked):
        loltv_sync.sync_loltv(engine, settings)


@pytest.mark.integration
def test_walkover_api_does_not_borrow_cards_or_a_normal_result_from_oracle(database):
    engine, settings = database
    value = replace(event(), status="walkover", home_score=1, away_score=0)
    from metiquo_core.models import EsportMatch
    from metiquo_worker.loltv_publication import _publish_events
    from test_live_regressions import snapshot

    _publish_events(engine, [value])
    with Session(engine) as db, db.begin():
        match = db.scalar(select(EsportMatch))
        previous = snapshot(match, 1)
        previous.source, previous.source_id = "oracles-elixir", "oracle-id"
        previous.source_url, previous.sha256 = "https://example.test/oracle", "a" * 64
        previous.payload["maps"] = [
            previous.payload["maps"][0],
            {**previous.payload["maps"][0], "number": 2},
        ]
        previous.payload["seriesScore"] = {"home": 2, "away": 0}
        db.add(previous)  # Even a later Oracle projection cannot erase the forfeit.
    with TestClient(create_app(settings)) as client:
        item = client.get("/api/v1/matches").json()["items"][0]
    assert item["status"] == "walkover"
    assert item["seriesScore"] == {"home": 1, "away": 0}
    assert item["maps"] == []


@pytest.mark.integration
def test_historical_partial_correction_requires_both_committed_snapshot_and_counter(
    database, monkeypatch
):
    engine, settings = database
    monkeypatch.setattr(loltv_sync, "discover_archived_events", lambda *_: ([], []))
    monkeypatch.setattr(loltv_sync.Collector, "run", lambda collector: collector.publish([event()]))
    run_id = loltv_sync.sync_loltv(engine, settings)
    empty_id = uuid4()
    with Session(engine) as db, db.begin():
        run = db.get(IngestionRun, run_id)
        run.status, run.error = "failed", "Some source pages failed"
        now = datetime.now(UTC) + timedelta(hours=1)
        db.add(
            IngestionRun(
                id=empty_id,
                source="loltv",
                scope="test",
                status="failed",
                error="Original error",
                started_at=now,
                finished_at=now,
                details={"published": 24},
            )
        )
        db.add(
            ScriptRun(
                script_id="loltv-matches",
                trigger="schedule",
                status="failed",
                requested_at=now,
                available_at=now,
                started_at=now,
                finished_at=now,
                ingestion_run_id=run_id,
                error="Old diagnostic",
            )
        )
    command.downgrade(Config("alembic.ini"), "0020")
    command.upgrade(Config("alembic.ini"), "head")
    with Session(engine) as db:
        corrected = db.get(IngestionRun, run_id)
        assert corrected.status == "succeeded" and corrected.details["complete"] is False
        assert corrected.details["statusCorrection"]["previousError"] == "Some source pages failed"
        assert db.get(IngestionRun, empty_id).status == "failed"
        assert db.scalar(select(ScriptRun)).status == "succeeded"
