"""DOM-only collection must preserve partial data and normal site loading."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace

from metiquo_core.config import Settings
from metiquo_worker.sofascore_policy import SofaScoreBlocked
from metiquo_worker.sources import sofascore
from test_live_regressions import event


def test_page_with_unlabelled_portraits_keeps_its_maps_without_api_enrichment(monkeypatch):
    raw = {
        "id": 42,
        "startTimestamp": 1789984800,
        "bestOf": 3,
        "status": {"type": "inprogress"},
        "homeTeam": {"id": 1, "name": "Alpha", "image": "https://img.sofascore.com/home"},
        "awayTeam": {"id": 2, "name": "Beta", "image": "https://img.sofascore.com/away"},
        "tournament": {"id": 3, "name": "Cup", "image": "logo", "category": {"slug": "lol"}},
    }
    data = json.dumps({"props": {"pageProps": {"event": raw}}})
    page = SimpleNamespace(content=lambda: f'<script id="__NEXT_DATA__">{data}</script>')
    maps = [
        {
            "number": 1,
            "status": "live",
            "bans": [],
            "sides": [
                {
                    "players": [
                        {
                            "champion": None,
                            "championImage": "https://img.sofascore.com/api/v1/character/42/image",
                        }
                    ]
                }
            ],
        }
    ]
    monkeypatch.setattr(sofascore, "_visible_maps", lambda *args, **kwargs: maps)
    monkeypatch.setattr(sofascore, "_visible_signals", lambda _: {})
    link = sofascore.SofaLink(event().url, "42", event().starts_at.date(), "Alpha Beta")
    observed = sofascore._event_from_page(page, link)
    assert observed is not None
    assert observed.payload["rendered"]["maps"] == maps
    assert maps[0]["sides"][0]["players"][0]["champion"] is None
    assert maps[0]["bans"] == []


def test_successful_site_api_responses_are_not_read(monkeypatch):
    class Response:
        url = "https://api.sofascore.com/api/v1/esports-game/42/lineups"
        status = 200

        def json(self):
            raise AssertionError("API payloads must not be consumed")

        def body(self):
            raise AssertionError("API response bodies must not be consumed")

    monkeypatch.setattr(sofascore, "_BLOCK_ERROR", None)
    sofascore._observe_response(Response())
    assert sofascore._BLOCK_ERROR is None


def test_site_api_refusal_cuts_network_once_without_reading_its_body(monkeypatch):
    actions, blocks = [], []
    request = SimpleNamespace(resource_type="xhr", url="https://www.sofascore.com/api/v1/event/42")

    def block(status, reason, retry_after, **metadata):
        blocks.append((status, reason, retry_after, metadata))
        return SofaScoreBlocked("blocked", status=status)

    monkeypatch.setattr(sofascore, "_BLOCK_ERROR", None)
    monkeypatch.setattr(sofascore, "_POLICY", SimpleNamespace(block=block))
    monkeypatch.setattr(sofascore, "_stop_source_network", lambda: actions.append("stop"))
    url = "https://www.sofascore.com/api/v1/event/42"
    sofascore._observe_response(
        SimpleNamespace(url=url, status=403, headers={"retry-after": "3600"}, request=request)
    )
    sofascore._observe_response(SimpleNamespace(url=url, status=403, headers={}, request=request))
    assert actions == ["stop"]
    assert blocks == [
        (403, "browser-response", "3600", {"request_url": url, "resource_type": "xhr"})
    ]


def test_missing_dom_labels_do_not_trigger_five_minute_historical_revisits(monkeypatch):
    observed = replace(
        event(),
        status="finished",
        payload={
            "rendered": {
                "maps": [
                    {
                        "number": 1,
                        "status": "finished",
                        "bans": [],
                        "sides": [
                            {
                                "players": [
                                    {
                                        "champion": None,
                                        "championImage": "https://img.sofascore.com/api/v1/character/42/image",
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        },
    )
    monkeypatch.setattr(
        sofascore,
        "_STATE",
        sofascore._ScrapeState(events={"42": observed}, event_fetched_at={"42": 1.0}),
    )
    link = sofascore.SofaLink(observed.url, "42", observed.starts_at.date(), "Alpha Beta")
    settings = Settings(database_url="postgresql+psycopg://test@localhost/test")
    assert not sofascore._should_refresh_event(link, 302.0, settings)
    assert not sofascore._should_refresh_event(link, 3599.0, settings)
    assert sofascore._should_refresh_event(link, 3602.0, settings)


def test_full_pass_visits_all_fifteen_days_and_more_than_120_matches(monkeypatch):
    today = date(2026, 9, 21)
    base = event()
    page = SimpleNamespace(
        url="",
        content=lambda: "",
        wait_for_selector=lambda *args, **kwargs: None,
        wait_for_timeout=lambda _: None,
    )
    navigations = []

    def navigate(page, url, settings):
        navigations.append(url)
        page.url = url
        return True

    def links(html, day, url):
        return [
            sofascore.SofaLink(f"{base.url}-{day}-{index}", f"{day}-{index}", day, "Alpha Beta")
            for index in range(9)
        ]

    def parsed(page, link):
        return replace(
            base,
            source_id=link.source_id,
            url=link.url,
            status="scheduled",
            starts_at=datetime.combine(link.day, datetime.min.time(), UTC),
        )

    monkeypatch.setattr(sofascore, "_STATE", sofascore._ScrapeState())
    monkeypatch.setattr(sofascore, "_POLICY", None)
    monkeypatch.setattr(sofascore.clock, "monotonic", lambda: 100000.0)
    monkeypatch.setattr(sofascore, "_browser_page", lambda _: page)
    monkeypatch.setattr(sofascore, "_navigate", navigate)
    monkeypatch.setattr(sofascore, "_links", links)
    monkeypatch.setattr(sofascore, "_reveal_match_details", lambda _: None)
    monkeypatch.setattr(sofascore, "_event_from_page", parsed)
    settings = Settings(
        database_url="postgresql+psycopg://test@localhost/test", sofascore_enabled=True
    )
    result = sofascore.scrape(settings, today=today)
    assert len(sofascore._STATE.day_fetched_at) == 15
    assert len(result) == 135
    assert len(navigations) == len(set(navigations)) == 150
    assert sofascore.scrape(settings, today=today) == []
    assert len(navigations) == 150


def test_missing_selected_panel_never_reuses_previous_map(monkeypatch):
    from patchright.sync_api import TimeoutError

    clicked = []

    def tab(test_id):
        return SimpleNamespace(
            count=lambda: int(test_id in {"tab-0", "tab-1"}),
            first=SimpleNamespace(
                click=lambda **kwargs: clicked.append(test_id),
                get_attribute=lambda _: "false",
            ),
        )

    def timeout(*args, **kwargs):
        raise TimeoutError("The newly selected panel has not loaded")

    page = SimpleNamespace(
        get_by_test_id=tab,
        wait_for_function=timeout,
        evaluate=lambda *args: {"number": 1},
        wait_for_timeout=lambda _: None,
    )
    monkeypatch.setattr(sofascore, "_BLOCK_ERROR", None)
    monkeypatch.setattr(sofascore, "_resolve_portrait_labels", lambda _: None)
    monkeypatch.setattr(sofascore, "_rendered_map", lambda capture, **kwargs: capture)
    assert sofascore._visible_maps(page, event_status="finished", source_id="42") == [{"number": 1}]
    assert clicked == ["tab-0", "tab-1"]
