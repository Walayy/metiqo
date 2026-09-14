"""Transport navigateur → fichier : intégrité, dates et données réelles rejouées."""

import asyncio
import copy
import json
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from infra.scripts.build_stake_reader import extension_source
from playwright.async_api import Route, async_playwright, expect

from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.providers.stake_browser_file import MAX_EXPORT_BYTES, StakeBrowserFileScraper, main
from metiquo.providers.stake_parser import StakeScrapeError
from tests.providers.test_stake_scraping import FIXTURE, REPLAY_TIME, recorded_doms, replay_html

ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT / "browser/stake-reader"


def browser_export() -> dict[str, Any]:
    states = recorded_doms()
    return {
        "format": "metiquo.stake-browser.v1",
        "exportedAt": REPLAY_TIME.isoformat(),
        "discoveredEvents": 1,
        "failures": [],
        "blocked": False,
        "captures": [
            {
                "url": states[0]["dom"]["url"],
                "timeZone": "Europe/Paris",
                "startedAt": REPLAY_TIME.isoformat(),
                "observedAt": REPLAY_TIME.isoformat(),
                "expectedTabs": [s["tab"] for s in states],
                "warnings": [],
                "states": [{**s, "capturedAt": REPLAY_TIME.isoformat()} for s in states],
            }
        ],
    }


def read_export(tmp_path: Path, payload: dict[str, Any]) -> Any:
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return asyncio.run(
        StakeBrowserFileScraper(path, clock=FixedClock(UtcInstant(REPLAY_TIME))).collect()
    )


def test_extension_extracts_exactly_the_same_dom_as_python() -> None:
    assert (EXTENSION / "extract-dom.js").read_text(encoding="utf-8") == extension_source()


def test_file_transport_preserves_every_market_and_original_observation_time(
    tmp_path: Path,
) -> None:
    payload = browser_export()
    result = read_export(tmp_path, payload)
    capture = result.captures[0]
    assert len(capture.markets) == 55
    assert sum(len(m.outcomes) for m in capture.markets) == 154
    assert capture.observed_at == REPLAY_TIME
    path = tmp_path / "capture.json"
    later = REPLAY_TIME + timedelta(hours=1)
    replay = asyncio.run(
        StakeBrowserFileScraper(path, clock=FixedClock(UtcInstant(later))).collect()
    )
    assert replay.captures == result.captures
    assert "BROWSER_EXPORT_STALE" in replay.failures


@pytest.mark.parametrize(
    "fault", ["future", "identity", "order", "zone", "tab", "duplicates", "format", "incomplete"]
)
def test_invalid_exports_are_rejected(tmp_path: Path, fault: str) -> None:
    payload = browser_export()
    capture = payload["captures"][0]
    if fault == "future":
        payload["exportedAt"] = (REPLAY_TIME + timedelta(seconds=1)).isoformat()
    elif fault == "identity":
        capture["states"][-1]["dom"]["participants"] = ["Other", "Teams"]
    elif fault == "order":
        capture["startedAt"] = (REPLAY_TIME + timedelta(seconds=1)).isoformat()
    elif fault == "zone":
        capture["timeZone"] = "Not/A_Zone"
    elif fault == "tab":
        capture["states"][-1]["dom"]["markets"][0]["label"] = "Map 1 Gagnant - Two options"
    elif fault == "duplicates":
        payload["captures"].append(copy.deepcopy(capture))
        payload["discoveredEvents"] = 2
    elif fault == "format":
        payload["format"] = "not-the-protocol"
    elif fault == "incomplete":
        capture["states"].pop()
    with pytest.raises(StakeScrapeError):
        read_export(tmp_path, payload)


def test_timezone_is_read_from_browser_instead_of_assuming_paris(tmp_path: Path) -> None:
    payload = browser_export()
    payload["captures"][0]["timeZone"] = "UTC"
    result = read_export(tmp_path, payload)
    assert result.captures[0].event.starts_at.hour == 17


def test_blocked_export_keeps_completed_captures(tmp_path: Path) -> None:
    payload = browser_export()
    payload.update(blocked=True, failures=["ACCESS_CHALLENGE"], discoveredEvents=2)
    result = read_export(tmp_path, payload)
    assert result.blocked and len(result.captures) == 1


@pytest.mark.parametrize("fault", ["missing", "truncated", "oversized"])
def test_file_read_errors_are_explicit(tmp_path: Path, fault: str) -> None:
    path = tmp_path / "export.json"
    if fault == "truncated":
        path.write_text('{"captures":', encoding="utf-8")
    elif fault == "oversized":
        path.write_bytes(b" " * (MAX_EXPORT_BYTES + 1))
    with pytest.raises(StakeScrapeError) as caught:
        asyncio.run(StakeBrowserFileScraper(path).collect())
    assert caught.value.code == (
        "BROWSER_EXPORT_MISSING" if fault == "missing" else "BROWSER_EXPORT_INVALID"
    )


@pytest.mark.parametrize("fault", ["missing-start", "already-started"])
def test_non_prematch_event_does_not_discard_other_completed_events(
    tmp_path: Path, fault: str
) -> None:
    payload = browser_export()
    other = copy.deepcopy(payload["captures"][0])
    other["url"] = other["url"].replace("822193-", "999999-")
    for state in other["states"]:
        state["dom"]["url"] = other["url"]
        state["dom"]["displayedStart"] = "" if fault == "missing-start" else "10:00 08/09/2026"
    payload["captures"].append(other)
    payload["discoveredEvents"] = 2
    result = read_export(tmp_path, payload)
    assert len(result.captures) == 1
    expected = "START_TIME_MISSING" if fault == "missing-start" else "EVENT_ALREADY_STARTED"
    assert result.failures == (other["url"].rsplit("/", 1)[1] + ":" + expected,)


def test_diagnostic_does_not_call_an_empty_export_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = browser_export()
    payload.update(captures=[], discoveredEvents=0)
    path = tmp_path / "empty.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["stake_browser_file", str(path)])
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 1
    assert json.loads(capsys.readouterr().out)["state"] == "failed"


@pytest.mark.integration
@pytest.mark.parametrize("mode", ["opened", "scan", "partial-blocked"])
def test_installed_extension_downloads_dom_then_python_reads_it(tmp_path: Path, mode: str) -> None:
    async def run() -> None:
        states = json.loads(
            FIXTURE.with_name("stake-9z-dom-20260908.json").read_text(encoding="utf-8")
        )
        event = states[0]["dom"]["url"]
        competition = event.rsplit("/", 1)[0]
        async with async_playwright() as runtime:
            context = await runtime.chromium.launch_persistent_context(
                tmp_path / "profile",
                channel="chromium",
                headless=True,
                locale="fr-FR",
                timezone_id="Europe/Paris",
                accept_downloads=True,
                downloads_path=tmp_path / "downloads",
                args=[f"--disable-extensions-except={EXTENSION}", f"--load-extension={EXTENSION}"],
            )
            try:
                browser = context.browser
                assert browser is not None
                cdp = await browser.new_browser_cdp_session()
                await cdp.send(
                    "Browser.setDownloadBehavior",
                    {
                        "behavior": "allow",
                        "downloadPath": str(tmp_path / "downloads"),
                    },
                )
                requested: list[str] = []

                async def route_source(route: Route) -> None:
                    url = route.request.url
                    requested.append(url)
                    if url.endswith("/822193-giantx-natus-vincere"):
                        await route.fulfill(
                            status=403,
                            content_type="text/html",
                            body="<title>Access denied</title><p>Forbidden</p>",
                        )
                        return
                    if url == event:
                        body = replay_html(states)
                    else:
                        link = competition if url.endswith("/all") else event
                        relative = link.removeprefix("https://stake.bet")
                        body = f'<div id="main-content"><a href="{relative}">lien</a></div>'
                    await route.fulfill(status=200, content_type="text/html", body=body)

                await context.route("https://stake.bet/**", route_source)
                worker = (
                    context.service_workers[0]
                    if context.service_workers
                    else await context.wait_for_event("serviceworker")
                )
                extension_id = worker.url.split("/")[2]
                if mode != "scan":
                    source = await context.new_page()
                    await source.goto(event)
                if mode == "partial-blocked":
                    blocked_page = await context.new_page()
                    await blocked_page.goto(
                        "https://stake.bet/fr/sports/league-of-legends/international-1/"
                        "lec-2026-summer-playoffs-t3/822193-giantx-natus-vincere"
                    )
                panel = await context.new_page()
                await panel.goto(f"chrome-extension://{extension_id}/panel.html")
                await panel.locator("#repeat").check()
                await panel.locator("#" + ("scan" if mode == "scan" else "opened")).click()
                await expect(panel.locator("#status")).to_have_text(
                    re.compile(r".*(?:exporté|impossible).*"),
                    timeout=60000,
                )
                suffix = " · collecte incomplète" if mode == "partial-blocked" else ""
                assert await panel.locator("#status").text_content() == (
                    f"1 match(s) exporté(s){suffix}."
                ), await panel.locator("#report").text_content()
                if mode == "partial-blocked":
                    await expect(panel.locator("#repeat")).not_to_be_checked()
                    await expect(panel.locator("#stop")).to_be_disabled()
                else:
                    await expect(panel.locator("#stop")).to_be_enabled()
                    await panel.locator("#stop").click()
                    await expect(panel.locator("#stop")).to_be_disabled()
                    await expect(panel.locator("#repeat")).not_to_be_checked()
                files = list((tmp_path / "downloads").rglob("*.json"))
                assert len(files) == 1
                result = await StakeBrowserFileScraper(files[0]).collect()
                assert len(result.captures) == 1
                if mode == "partial-blocked":
                    assert result.blocked and "ACCESS_CHALLENGE" in result.failures[0]
                else:
                    assert not result.failures
                assert len(result.captures[0].markets) == 11
                assert sum(len(m.outcomes) for m in result.captures[0].markets) == 22
                assert all("/api/" not in url for url in requested)
            finally:
                await context.close()

    asyncio.run(run())
