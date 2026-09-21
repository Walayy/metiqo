"""Captured HTML contracts and queue semantics; no access to the real source."""

import copy
import gzip
import json
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from metiquo_core.config import Settings
from metiquo_worker.loltv_browser import merge_dom
from metiquo_worker.loltv_feed import AnonymousSessions, FeedReader, merge_feed
from metiquo_worker.loltv_policy import LoltvBlocked
from metiquo_worker.loltv_sync import Collector, complete, decode_event, encode_event
from metiquo_worker.sources.loltv import ROOT_URL, detail, flight_records, listing, source_maps

FIXTURES = Path(__file__).parent / "fixtures/loltv"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.setenv("METIQUO_DATABASE_URL", "postgresql+psycopg://unused/unused_test")

    class CapturedDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 21, 18, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr("metiquo_worker.loltv_sync.datetime", CapturedDate)


def captured(name):
    return (FIXTURES / (name + ".html")).read_text(encoding="utf-8")


def sample(name="final"):
    rows, _, _ = listing(captured("results" if name == "final" else "matches"), ROOT_URL)
    slug = "g2-esports" if name == "final" else "skillcamp"
    event = next(row for row in rows if slug in row.url)
    return detail(captured(name), event)


def test_public_pages_decode_identities_pagination_and_unknown_teams():
    events, pages, dates = listing(captured("matches"), ROOT_URL + "/matches")
    assert len(events) == 38
    assert all(event.home_source_id and event.away_source_id for event in events)
    assert all(event.home_name != "TBD" and event.away_name != "TBD" for event in events)
    assert len(dates) > len(events)  # TBD dates still establish pagination coverage.
    assert ROOT_URL + "/matches/all/2" in pages
    assert all(event.starts_at.tzinfo for event in events)


def test_match_header_uses_score_not_the_1500_start_time():
    event = sample()
    assert (event.home_score, event.away_score, event.best_of) == (3, 0, 5)
    assert event.status == "finished"
    game = event.payload["rendered"]["maps"][0]
    assert len(game["bans"]) == 10
    assert [side["side"] for side in game["sides"]] == ["blue", "red"]
    assert all(len(side["players"]) == 5 for side in game["sides"])
    assert game["winner"] == "home"


def test_live_placeholders_never_become_zero_stats_or_sourced_sides():
    event = sample("detail")
    assert (event.home_score, event.away_score) == (1, 1)
    assert event.status == "live"
    assert not complete(event)
    for game in event.payload["rendered"]["maps"]:
        for side in game["sides"]:
            assert side["side"] is None
            assert side["players"] == []
            assert side["towers"] is None


def test_wrong_match_document_fails_even_when_teams_are_similar():
    with pytest.raises(ValueError, match="requested match"):
        detail(captured("final"), sample("detail"))


def test_flight_decodes_utf8_byte_records_and_split_json_without_eval():
    transport = 'a:T3,é!b:{"name":"Alpha"}\n'
    html = "".join(
        "<script>self.__next_f.push(" + json.dumps([1, part]) + ")</script>"
        for part in (transport[:17], transport[17:])
    )
    assert flight_records(html) == {"a": "é!", "b": {"name": "Alpha"}}
    with pytest.raises(ValueError):
        flight_records('<script>self.__next_f.push([1,"a:Tff,x"])</script>')


def test_alias_in_source_is_accepted_without_changing_team_identity():
    event = sample()
    payload = copy.deepcopy(event.payload)
    payload["sourceMatch"]["team1_name"] = "G2"
    renamed = replace(event, payload=payload)
    games = copy.deepcopy(payload["sourceGames"])
    games[0]["teams"][0]["team"]["name"] = "G2"
    assert len(source_maps(games, renamed)[0]["sides"]) == 2


def test_unknown_format_does_not_invent_bo1_from_three_available_games():
    event = replace(sample(), best_of=None)
    html = captured("final").replace("BO<!-- -->5", "Unknown")
    assert detail(html, event).best_of is None


def test_dom_gold_difference_does_not_become_total_gold():
    event = sample("detail")
    players = [
        {
            "name": f"player{i}",
            "champion": "Ahri",
            "championImage": "",
            "kills": 1,
            "deaths": 0,
            "assists": 2,
            "cs": 100,
            "gold": 999,
        }
        for i in range(5)
    ]
    roles = dict(
        zip((p["name"] for p in players), ("TOP", "JGL", "MID", "BOT", "SUP"), strict=True)
    )
    result = merge_dom(
        event,
        {"number": 1, "teams": [{"name": event.home_name, "players": players, "towers": 3}]},
        roles,
    )
    side = result.payload["rendered"]["maps"][0]["sides"][0]
    assert len(side["players"]) == 5
    assert all(player["gold"] is None for player in side["players"])
    assert side["side"] is None


class MemoryPolicy:
    def __init__(self):
        self.data = {}

    def read(self):
        return copy.deepcopy(self.data)

    def checkpoint(self, state):
        self.data["checkpoint"] = copy.deepcopy(state)

    def check(self):
        pass

    def before_request(self):
        pass

    def page_completed(self):
        pass

    def block(self, status, reason, retry_after=None, **kwargs):
        self.data["refused"] = status
        return LoltvBlocked("blocked", status=status)


def test_queue_keeps_completed_cache_without_republishing_it(monkeypatch):
    policy = MemoryPolicy()
    collector = Collector(None, Settings(loltv_render_live=False), policy, uuid4())
    event = sample()
    collector.first = event.starts_at.date() - timedelta(days=7)
    collector.last = event.starts_at.date() + timedelta(days=7)
    collector.events[event.source_id] = {
        "event": encode_event(event),
        "completedGames": {"g": 123},
        "due": 456,
    }
    observed = []
    monkeypatch.setattr(collector, "publish", observed.extend)
    monkeypatch.setattr(collector, "fetch", lambda *_: captured("results"))
    collector.read_listing(None, ROOT_URL + "/matches/results")
    assert collector.events[event.source_id]["completedGames"] == {"g": 123}
    assert all(event.payload["rendered"]["maps"] == [] for event in observed)
    collector.checkpoint()
    resumed = Collector(None, Settings(), policy, uuid4())
    assert resumed.events[event.source_id]["completedGames"] == {"g": 123}
    assert decode_event(collector.events[event.source_id]["event"]).source_id == event.source_id


def test_first_http_refusal_stops_queue_without_retry(tmp_path):
    policy = MemoryPolicy()
    collector = Collector(None, Settings(artifact_dir=tmp_path), policy, uuid4())
    calls = []

    def response(request):
        calls.append(str(request.url))
        return httpx.Response(429, headers={"Retry-After": "3600"})

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(LoltvBlocked):
            collector.read_listing(client, ROOT_URL + "/matches")
    assert calls == [ROOT_URL + "/matches"]
    assert policy.data["refused"] == 429


def test_window_uses_paris_midnight():
    collector = Collector(None, Settings(), MemoryPolicy(), uuid4())
    collector.first = datetime(2026, 9, 14).date()
    collector.last = datetime(2026, 9, 28).date()
    assert collector.in_window(datetime(2026, 9, 13, 22, tzinfo=UTC))
    assert not collector.in_window(datetime(2026, 9, 28, 22, tzinfo=UTC))


def test_anonymous_feed_corrects_placeholder_camps_with_all_five_team_tags():
    raw = json.loads((FIXTURES / "feed.json").read_text())
    event = merge_feed(sample("detail"), raw["id"], raw)
    game = event.payload["rendered"]["maps"][2]
    assert game["status"] == "live"  # A feed without a winner cannot settle the game.
    assert [(s["position"], s["side"]) for s in game["sides"]] == [
        ("home", "blue"),
        ("away", "red"),
    ]
    assert game["sides"][0]["players"][0]["name"] == "Yeti"
    assert game["sides"][0]["players"][0]["gold"] == 11584
    assert game["sides"][1]["dragons"] == 3
    assert game["sides"][0]["heralds"] is None
    assert game["bans"] == []
    assert game["sourceObservedAt"] == raw["timestamp"]
    raw["events"] = [{"type": "GOLD", "clock": 100000}, {"type": "GOLD", "clock": 180000}]
    assert (
        merge_feed(sample("detail"), raw["id"], raw).payload["rendered"]["maps"][2][
            "durationSeconds"
        ]
        == 80
    )
    raw["events"].append({"type": "PAUSE", "clock": 150000, "value": "start"})
    assert (
        merge_feed(sample("detail"), raw["id"], raw).payload["rendered"]["maps"][2][
            "durationSeconds"
        ]
        is None
    )
    different_code = sample("detail")
    different_code.payload["sourceGames"][2]["teams"][0]["team"]["code"] = "OLD"
    assert (
        merge_feed(different_code, raw["id"], raw).payload["rendered"]["maps"][2]["sides"][0][
            "side"
        ]
        == "blue"
    )
    with pytest.raises(ValueError, match="requested game"):
        merge_feed(sample("detail"), "different", raw)
    academy = sample("detail")
    academy.payload["sourceGames"][2]["teams"][0]["team"]["code"] = "SC.A"
    academy.payload["sourceMatch"]["team1"]["code"] = "SC.A"
    assert (
        merge_feed(academy, raw["id"], raw).payload["rendered"]["maps"][2]["sides"][0]["side"]
        == "blue"
    )
    raw["teams"][0]["players"][4]["summoner_name"] = "AP SteeelBack"
    with pytest.raises(ValueError, match="ambiguous"):
        merge_feed(sample("detail"), raw["id"], raw)


def test_feed_discovers_action_once_and_stops_on_refusal_without_saving_cookies(tmp_path):
    policy, state, metrics, calls = MemoryPolicy(), {}, {}, []
    reader = FeedReader(Settings(artifact_dir=tmp_path), policy, state, metrics)
    script_url = ROOT_URL + "/_next/static/chunks/match.js"
    html = '<script src="/_next/static/chunks/match.js"></script>'
    action = "a" * 40

    def response(request):
        calls.append((request.method, str(request.url)))
        if str(request.url) == script_url:
            return httpx.Response(
                200,
                text=f'let G=(0,K.createServerReference)("{action}",K.callServer,'
                'void 0,K.findSourceMapURL,"getFeedSession");',
            )
        if request.method == "POST":
            assert request.headers["Next-Action"] == action
            return httpx.Response(
                200,
                headers={
                    "set-cookie": "loltv.scope=test-secret; Domain=.loltv.gg; "
                    "Path=/; Secure; HttpOnly"
                },
            )
        return httpx.Response(429, headers={"Retry-After": "3600"})

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        assert reader.discover(client, html) == action
        assert reader.discover(client, html) == action
        with pytest.raises(LoltvBlocked):
            reader.enrich(client, html, sample("detail"), set())
    assert [method for method, _ in calls] == ["GET", "POST", "GET"]
    assert policy.data["refused"] == 429
    assert "test-secret" not in json.dumps([state, metrics, policy.data])


def test_live_metadata_cache_reads_only_new_feed_and_never_republishes_old_maps(
    tmp_path, monkeypatch
):
    policy = MemoryPolicy()
    collector = Collector(None, Settings(artifact_dir=tmp_path), policy, uuid4())
    event = sample("detail")
    encoded = encode_event(event)
    (tmp_path / "detail.gz").write_bytes(gzip.compress(captured("detail").encode()))
    collector.events[event.source_id] = {
        "event": encoded,
        "metadataEvent": encoded,
        "metadataAt": time.time(),
        "metadataHtmlPath": "detail.gz",
    }
    monkeypatch.setattr(
        collector, "fetch", lambda *_: pytest.fail("Cached metadata was fetched again")
    )
    observed = []
    monkeypatch.setattr(collector, "publish", observed.extend)

    def enrich(_self, client, html, current, acquired, publish):
        assert current.payload["rendered"]["maps"] == []
        assert current.payload["sourceGames"] == event.payload["sourceGames"]
        return current

    monkeypatch.setattr(FeedReader, "enrich", enrich)
    collector.read_detail(None, event.source_id)
    assert observed == []
    assert collector.details["cachedMetadata"] == 1


def test_live_sessions_are_reused_per_match_expire_and_never_retry_401(tmp_path, monkeypatch):
    clock = [time.time()]
    monkeypatch.setattr("metiquo_worker.loltv_feed.time.time", lambda: clock[0])
    policy, state, metrics, sessions = MemoryPolicy(), {}, {}, AnonymousSessions()
    reader = FeedReader(Settings(artifact_dir=tmp_path), policy, state, metrics, sessions)
    action = "a" * 40
    monkeypatch.setattr(reader, "discover", lambda *_: action)
    event = sample("detail")
    other = replace(event, source_id="other-match")
    feed = json.loads((FIXTURES / "feed.json").read_text())
    acquired = {g["id"] for g in event.payload["sourceGames"] if g["id"] != feed["id"]}
    calls, fail = [], [False]

    def response(request):
        calls.append((request.method, request.headers.get("cookie", "")))
        if request.method == "POST":
            match = json.loads(request.content)[0]
            return httpx.Response(
                200,
                headers={
                    "set-cookie": f"loltv.scope={match}; Domain=.loltv.gg; "
                    "Path=/; Max-Age=90; Secure; HttpOnly"
                },
            )
        return httpx.Response(401) if fail[0] else httpx.Response(200, json=feed)

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        reader.enrich(client, "", event, acquired)
        reader.enrich(client, "", other, acquired)
        reader.enrich(client, "", event, acquired)
        assert [method for method, _ in calls] == ["POST", "GET", "POST", "GET", "GET"]
        assert calls[-1][1] == "loltv.scope=" + event.source_id
        assert metrics["reusedSessions"] == 1
        assert event.source_id not in json.dumps([state, metrics, policy.data])
        clock[0] += 91
        reader.enrich(client, "", event, acquired)
        assert [method for method, _ in calls[-2:]] == ["POST", "GET"]
        fail[0] = True
        count = len(calls)
        reader.enrich(client, "", event, acquired)
        assert len(calls) == count + 1  # No repeated session action on failure.
        assert event.source_id not in sessions.entries
        assert metrics["errors"][-1]["error"] == "HTTPStatusError"


def test_live_reads_preempt_backfill_when_their_deadline_returns(monkeypatch):
    clock = [time.time()]
    monkeypatch.setattr("metiquo_worker.loltv_sync.time.time", lambda: clock[0])
    monkeypatch.setattr("metiquo_worker.loltv_sync.time.monotonic", lambda: clock[0])
    collector = Collector(None, Settings(), MemoryPolicy(), uuid4())
    collector.pages.clear()
    live, finished = sample("detail"), sample()
    collector.events[live.source_id] = {"event": encode_event(live), "due": 0}
    for index in range(3):
        event = replace(finished, source_id=f"history{index}", url=f"{finished.url}/{index}")
        collector.events[event.source_id] = {"event": encode_event(event), "due": 0}
    calls = []

    def read(_client, key):
        calls.append((key, clock[0]))
        is_live = key == live.source_id
        clock[0] += 2 if is_live else 20
        collector.events[key]["due"] = clock[0] + (30 if is_live else 21600)

    monkeypatch.setattr(collector, "read_detail", read)
    collector.run()
    assert [key for key, _ in calls] == [
        live.source_id,
        "history0",
        "history1",
        live.source_id,
        "history2",
    ]
    assert calls[3][1] - calls[0][1] == 42


@pytest.mark.parametrize("waiting_result", [False, True])
def test_live_between_maps_refreshes_metadata_without_waiting_fifteen_minutes(
    tmp_path, monkeypatch, waiting_result
):
    event = sample("detail")
    game_id = event.payload["sourceGames"][2]["id"]
    if not waiting_result:
        event.payload["sourceGames"][2]["state"] = "UNSTARTED"
    collector = Collector(None, Settings(artifact_dir=tmp_path), MemoryPolicy(), uuid4())
    (tmp_path / "detail.gz").write_bytes(gzip.compress(captured("detail").encode()))
    collector.events[event.source_id] = {
        "event": encode_event(event),
        "metadataEvent": encode_event(event),
        "metadataAt": time.time() - 61,
        "metadataHtmlPath": "detail.gz",
        "feedStates": {game_id: {"state": "COMPLETED"}} if waiting_result else {},
    }
    fetched, reads = [], []

    def fetch(*_):
        fetched.append(True)
        return captured("detail")

    def enrich(_self, client, html, current, acquired, publish):
        reads.append(acquired)
        return current

    monkeypatch.setattr(collector, "fetch", fetch)
    monkeypatch.setattr(collector, "publish", lambda *_: None)
    monkeypatch.setattr(FeedReader, "enrich", enrich)
    collector.read_detail(None, event.source_id)
    assert fetched == [True]
    assert (game_id in reads[0]) == waiting_result
    # The final feed is not repeatedly downloaded while HTML still lacks a winner.
    # A new map can be discovered by the next metadata read even at the same score.


def test_live_parse_error_uses_short_backoff_then_recovers(monkeypatch):
    clock = [time.time()]
    monkeypatch.setattr("metiquo_worker.loltv_sync.time.time", lambda: clock[0])
    policy = MemoryPolicy()
    collector = Collector(None, Settings(), policy, uuid4())
    collector.pages.clear()
    live = sample("detail")
    collector.events[live.source_id] = {"event": encode_event(live), "due": 0}

    def fail(*_):
        raise ValueError("LoLTV timestamp is missing")

    monkeypatch.setattr(collector, "read_detail", fail)
    collector.run()
    assert collector.events[live.source_id]["due"] == clock[0] + 60
    clock[0] += 60
    collector.run()
    assert collector.events[live.source_id]["due"] == clock[0] + 120
    clock[0] += 120

    def recovered(*_):
        collector.events[live.source_id]["due"] = clock[0] + 30

    monkeypatch.setattr(collector, "read_detail", recovered)
    collector.run()
    assert collector.events[live.source_id]["liveErrors"] == 0
    assert collector.events[live.source_id]["due"] == clock[0] + 30
