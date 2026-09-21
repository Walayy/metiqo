"""Behavioral regressions for cache, deduplication and stop-on-refusal."""

from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from metiquo_core.config import Settings
from metiquo_worker import sofascore_policy, sofascore_sync
from metiquo_worker.sofascore_policy import SofaScoreBlocked, SofaScorePolicy
from metiquo_worker.sources import sofascore
from patchright.sync_api import TimeoutError as BrowserTimeout
from test_live_regressions import event


@pytest.fixture
def isolated_scraper(monkeypatch):
    monkeypatch.setattr(sofascore, "_STATE", sofascore._ScrapeState())
    monkeypatch.setattr(sofascore, "_BROWSER", sofascore._BrowserState())
    monkeypatch.setattr(sofascore, "_VISITED_PAGES", set())
    monkeypatch.setattr(sofascore, "_BLOCK_ERROR", None)
    monkeypatch.setattr(sofascore, "_POLICY", None)
    return Settings(database_url="postgresql://unused", sofascore_enabled=True)


def test_known_window_refreshes_only_due_days(monkeypatch, isolated_scraper):
    today = date(2026, 9, 21)
    days = tuple(today + timedelta(days=i) for i in [*range(8), *range(-7, 0)])
    at = 100000.0
    monkeypatch.setattr(sofascore.clock, "monotonic", lambda: at)
    sofascore._STATE.listing_days = days
    sofascore._STATE.day_fetched_at = {day.isoformat(): at - 60 for day in days}
    page = SimpleNamespace(
        url="",
        content=lambda: "",
        wait_for_selector=lambda *a, **k: None,
        wait_for_timeout=lambda _: None,
    )
    navigations = []

    def navigate(page, url, settings):
        navigations.append(url)
        page.url = url
        return True

    monkeypatch.setattr(sofascore, "_browser_page", lambda _: page)
    monkeypatch.setattr(sofascore, "_navigate", navigate)
    monkeypatch.setattr(sofascore, "_links", lambda *a: [])
    assert sofascore.scrape(isolated_scraper, today=today) == []
    assert navigations == []
    at += 121
    sofascore.scrape(isolated_scraper, today=today)
    assert navigations == [sofascore._day_url(today)]
    at += 720
    sofascore.scrape(isolated_scraper, today=today)
    assert len(navigations) == 9  # Today twice, seven future days, no historical day.
    assert not any(
        str(today - timedelta(days=i)) in url for url in navigations for i in range(1, 8)
    )


def test_recommendations_across_fifteen_days_open_each_match_once(monkeypatch, isolated_scraper):
    page = SimpleNamespace(
        url="",
        content=lambda: "",
        wait_for_selector=lambda *a, **k: None,
        wait_for_timeout=lambda _: None,
    )
    navigations = []
    base = event()

    def navigate(page, url, settings):
        navigations.append(url)
        page.url = url
        return True

    monkeypatch.setattr(sofascore, "_browser_page", lambda _: page)
    monkeypatch.setattr(sofascore, "_navigate", navigate)
    monkeypatch.setattr(
        sofascore,
        "_links",
        lambda html, day, url: [sofascore.SofaLink(base.url, "42", day, "Alpha Beta")],
    )
    monkeypatch.setattr(sofascore, "_reveal_match_details", lambda _: None)
    monkeypatch.setattr(sofascore, "_event_from_page", lambda *a: base)
    assert sofascore.scrape(isolated_scraper, today=date(2026, 9, 21)) == [base]
    assert len(navigations) == 16
    assert navigations.count(base.url) == 1


def test_alias_urls_and_failed_pages_are_never_retried_in_same_pass(monkeypatch, isolated_scraper):
    calls = []

    def goto(url, **kwargs):
        calls.append(url)
        raise RuntimeError("page load interrupted")

    monkeypatch.setattr(sofascore.clock, "monotonic", lambda: 100000.0)
    page = SimpleNamespace(goto=goto)
    with pytest.raises(RuntimeError):
        sofascore._navigate(
            page, "https://www.sofascore.com/esports/match/a#id:42", isolated_scraper
        )
    assert not sofascore._navigate(
        page, "https://www.sofascore.com/fr/esports/match/alias#id:42,tab:games", isolated_scraper
    )
    assert len(calls) == 1


def test_first_refusal_ends_the_pass_before_next_day(monkeypatch, isolated_scraper):
    calls = []
    stopped = []
    request = SimpleNamespace(resource_type="document")

    def goto(url, **kwargs):
        calls.append(url)
        sofascore._observe_response(
            SimpleNamespace(url=url, status=403, headers={}, request=request)
        )
        raise RuntimeError("page was closed on refusal")

    page = SimpleNamespace(goto=goto)
    monkeypatch.setattr(sofascore, "_browser_page", lambda _: page)
    monkeypatch.setattr(sofascore, "_stop_source_network", lambda: stopped.append(True))
    with pytest.raises(SofaScoreBlocked):
        sofascore.scrape(isolated_scraper, today=date(2026, 9, 21))
    assert len(calls) == len(stopped) == 1


@pytest.mark.parametrize("status,resource_type", [(403, "document"), (429, "xhr")])
def test_refusal_is_persisted_before_closing_page_can_resume_cycle(
    monkeypatch, isolated_scraper, caplog, status, resource_type
):
    saved = []

    def block(status, reason, retry_after, **metadata):
        saved.append({"status": status, "retry_after": retry_after, **metadata})
        return SofaScoreBlocked("persisted", status=status, reason=reason, retry_at=12345678999)

    monkeypatch.setattr(sofascore, "_POLICY", SimpleNamespace(block=block))
    # A synchronous browser call in this callback can yield to the interrupted
    # goto/cycle before the callback resumes. The durable refusal must be ready.
    monkeypatch.setattr(sofascore, "_stop_source_network", sofascore._raise_if_blocked)
    response = SimpleNamespace(
        url="https://www.sofascore.com/fr/esports/lol/2026-09-17",
        status=status,
        headers={"retry-after": "120", "content-type": "text/html"},
        request=SimpleNamespace(resource_type=resource_type),
    )
    with pytest.raises(SofaScoreBlocked) as caught:
        sofascore._observe_response(response)
    assert caught.value.retry_at == 12345678999
    assert saved == [
        {
            "status": status,
            "retry_after": "120",
            "request_url": response.url,
            "resource_type": resource_type,
        }
    ]
    assert "SofaScore refused" in caplog.text


def test_live_refresh_reads_only_new_maps_and_cache_is_not_fresh(monkeypatch, isolated_scraper):
    old = {"number": 1, "status": "finished"}
    base = replace(event(), status="live", payload={"rendered": {"maps": [old]}})
    sofascore._STATE.events = {"42": base}
    selected, pauses = [], []

    def tab(test_id):
        index = int(test_id.split("-")[-1])
        return SimpleNamespace(
            count=lambda: int(index < 3),
            first=SimpleNamespace(
                get_attribute=lambda _: "false", click=lambda **k: selected.append(index)
            ),
        )

    page = SimpleNamespace(
        get_by_test_id=tab,
        wait_for_timeout=pauses.append,
        wait_for_function=lambda *a, **k: SimpleNamespace(
            json_value=lambda: {"number": k["arg"]["index"] + 1}, dispose=lambda: None
        ),
    )
    monkeypatch.setattr(sofascore, "_resolve_portrait_labels", lambda _: None)
    monkeypatch.setattr(
        sofascore,
        "_rendered_map",
        lambda capture, **k: {"number": k["number"], "status": k["status"]},
    )
    maps = sofascore._visible_maps(page, event_status="live", source_id="42")
    assert selected == [1, 2]
    assert [item["number"] for item in maps] == [2, 3]
    fresh = replace(base, payload={"rendered": {"maps": maps}})
    cached = sofascore._cache_event(fresh, base)
    assert [item["number"] for item in cached.payload["rendered"]["maps"]] == [1, 2, 3]
    assert [item["number"] for item in fresh.payload["rendered"]["maps"]] == [2, 3]


def test_failed_tab_keeps_pause_and_does_not_retry(monkeypatch, isolated_scraper):
    attempts, pauses = [], []

    def click(index):
        attempts.append(index)
        raise BrowserTimeout("tab not actionable")

    def tab(test_id):
        index = int(test_id.split("-")[-1])
        return SimpleNamespace(
            count=lambda: int(index < 2),
            first=SimpleNamespace(get_attribute=lambda _: "false", click=lambda **k: click(index)),
        )

    page = SimpleNamespace(get_by_test_id=tab, wait_for_timeout=pauses.append)
    assert sofascore._visible_maps(page, event_status="live", source_id="42") == []
    assert attempts == [0, 1]
    assert len(pauses) == 1 and 4000 <= pauses[0] <= 8000


@pytest.mark.integration
def test_pause_starts_after_page_completion_and_survives_new_policy(database, monkeypatch):
    engine, settings = database
    now = [100000.0]
    pauses = []
    monkeypatch.setattr(sofascore_policy.time, "time", lambda: now[0])
    monkeypatch.setattr(sofascore_policy.RANDOM, "uniform", lambda *a: 15.0)

    def sleep(seconds):
        pauses.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(sofascore_policy.time, "sleep", sleep)
    first = SofaScorePolicy(engine, settings)
    first.before_request()
    now[0] += 100
    first.page_completed({"saved": "page"})
    restarted = SofaScorePolicy(engine, settings)
    restarted.before_request()
    assert pauses == [15.0]
    assert restarted.read()["lastRequestAt"] == 100115.0
    assert restarted.read()["checkpoint"] == {"saved": "page"}


@pytest.mark.integration
def test_unpublished_maps_do_not_survive_as_fresh_cache(database, monkeypatch):
    engine, settings = database
    monkeypatch.setattr(sofascore, "_STATE", sofascore._ScrapeState())
    monkeypatch.setattr(sofascore, "_POLICY", None)
    monkeypatch.setattr(sofascore, "_BLOCK_ERROR", None)
    monkeypatch.setattr(sofascore, "idle_browser", lambda: None)
    observed = replace(
        event(),
        status="live",
        payload={"rendered": {"maps": [{"number": 1, "status": "finished"}]}},
    )

    def scrape(*args, **kwargs):
        sofascore._STATE.fresh = [observed]
        sofascore._STATE.events = {"42": observed}
        sofascore._STATE.event_fetched_at = {"42": 100000.0}
        return [observed]

    def failed_publication(*args):
        raise RuntimeError("simulated publication failure")

    monkeypatch.setattr(sofascore_sync, "scrape", scrape)
    monkeypatch.setattr(sofascore_sync, "_save_event", failed_publication)
    with pytest.raises(RuntimeError, match="collection failed"):
        sofascore_sync.sync_sofascore(engine, settings)
    saved = SofaScorePolicy(engine, settings).read()["checkpoint"]
    assert "42" not in saved["events"]
    assert "42" not in saved["event_fetched_at"]
