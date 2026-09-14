"""Rafales et échecs de téléchargements dans le véritable navigateur."""

import asyncio
from pathlib import Path

import pytest
from playwright.async_api import Route

from metiquo.providers.stake_assets import limit_static_assets
from metiquo.providers.stake_runtime import stake_context


@pytest.mark.integration
@pytest.mark.parametrize("same_document", [False, True])
def test_static_burst_is_bounded_and_failed_downloads_release_slots(
    tmp_path: Path, same_document: bool
) -> None:
    async def run() -> None:
        active = peak = completed = 0
        started = asyncio.Event()
        async with stake_context(
            engine="patchright", channel="chromium", headless=True, profile_dir=tmp_path / "profile"
        ) as context:

            async def serve(route: Route) -> None:
                nonlocal active, peak, completed
                if "/_app/" not in route.request.url:
                    await route.fulfill(content_type="text/html", body="<title>Asset burst</title>")
                    return
                active += 1
                started.set()
                peak = max(peak, active)
                try:
                    await asyncio.sleep(0.04)
                    if route.request.url.endswith("/0.mjs"):
                        await route.abort("failed")
                    else:
                        await route.fulfill(content_type="text/javascript", body="export {};")
                    completed += 1
                finally:
                    active -= 1

            await context.route("https://stake.bet/**", serve)
            await limit_static_assets(context, concurrency=4)
            page = await context.new_page()
            await page.goto("https://stake.bet/")
            pending = asyncio.create_task(
                page.evaluate(
                    """async () => {
                      const results = await Promise.allSettled(Array.from({length: 48},
                        (_, i) => import('/_app/' + i + '.mjs')));
                      return results.reduce((counts, r) => {
                        counts[r.status] = (counts[r.status] || 0) + 1;
                        return counts;
                      }, {});
                    }"""
                )
            )
            await asyncio.wait_for(started.wait(), timeout=5)
            if same_document:
                await page.evaluate("history.replaceState({}, '', '#map-1')")
            result = await asyncio.wait_for(pending, timeout=5)
            assert result == {"fulfilled": 47, "rejected": 1}
            assert completed == 48 and active == 0 and peak == 4

    asyncio.run(run())


@pytest.mark.integration
def test_closing_page_with_queued_assets_does_not_hold_context_open(tmp_path: Path) -> None:
    async def run() -> None:
        started = asyncio.Event()
        async with stake_context(
            engine="patchright", channel="chromium", headless=True, profile_dir=tmp_path / "profile"
        ) as context:

            async def serve(route: Route) -> None:
                if "/_app/" in route.request.url:
                    started.set()
                    await asyncio.sleep(0.2)
                    await route.abort()
                else:
                    await route.fulfill(
                        content_type="text/html", body="<title>Cancel burst</title>"
                    )

            await context.route("https://stake.bet/**", serve)
            await limit_static_assets(context, concurrency=1)
            page = await context.new_page()
            await page.goto("https://stake.bet/")
            await page.evaluate(
                """() => { for(let i=0; i<40; i++)
                  fetch('/_app/'+i+'.mjs').catch(()=>{}); }"""
            )
            await asyncio.wait_for(started.wait(), timeout=5)
            await asyncio.wait_for(page.close(), timeout=5)

    asyncio.run(asyncio.wait_for(run(), timeout=15))


@pytest.mark.integration
def test_navigation_cancels_queued_downloads_without_starving_next_page(tmp_path: Path) -> None:
    async def run() -> None:
        started = asyncio.Event()
        async with stake_context(
            engine="patchright", channel="chromium", headless=True, profile_dir=tmp_path / "profile"
        ) as context:

            async def serve(route: Route) -> None:
                if "/_app/" in route.request.url:
                    started.set()
                    await asyncio.sleep(0.15)
                    await route.fulfill(content_type="text/javascript", body="export {};")
                else:
                    await route.fulfill(content_type="text/html", body="<title>Navigate</title>")

            await context.route("https://stake.bet/**", serve)
            await limit_static_assets(context, concurrency=2)
            page = await context.new_page()
            await page.goto("https://stake.bet/first")
            await page.evaluate(
                """() => { for(let i=0; i<80; i++)
                  fetch('/_app/old/'+i+'.mjs').catch(()=>{}); }"""
            )
            await asyncio.wait_for(started.wait(), timeout=5)
            await page.goto("https://stake.bet/second")
            assert (
                await asyncio.wait_for(
                    page.evaluate("async () => (await fetch('/_app/new.mjs')).status"), timeout=5
                )
                == 200
            )

    asyncio.run(asyncio.wait_for(run(), timeout=15))
