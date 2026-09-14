"""Navigateurs du collecteur, profil dédié et affichage Linux privé."""

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, cast

from patchright.async_api import async_playwright as patched_playwright
from playwright.async_api import BrowserContext, async_playwright

from metiquo.providers.stake_parser import DISPLAY_TIMEZONE, StakeScrapeError


@asynccontextmanager
async def browser_environment(headless: bool) -> AsyncIterator[dict[str, str | float | bool]]:
    environment: dict[str, str | float | bool] = dict(os.environ)
    if headless or sys.platform != "linux" or environment.get("DISPLAY"):
        yield environment
        return
    # Xvfb choisit un affichage libre et n'écoute aucun port réseau.
    try:
        display = await asyncio.create_subprocess_exec(
            "Xvfb",
            "-displayfd",
            "1",
            "-screen",
            "0",
            "1440x1080x24",
            "-nolisten",
            "tcp",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        raise StakeScrapeError(
            "DISPLAY_UNAVAILABLE", "Installer Xvfb pour le navigateur Linux"
        ) from None
    try:
        assert display.stdout is not None
        number = (await asyncio.wait_for(display.stdout.readline(), timeout=10)).decode().strip()
        if not number.isdigit():
            raise StakeScrapeError("DISPLAY_UNAVAILABLE", "L'affichage privé n'a pas démarré")
        environment["DISPLAY"] = ":" + number
        yield environment
    finally:
        if display.returncode is None:
            display.terminate()
            try:
                await asyncio.wait_for(display.wait(), timeout=5)
            except TimeoutError:
                display.kill()
                await display.wait()


@asynccontextmanager
async def stake_context(
    *,
    engine: Literal["playwright", "patchright"],
    channel: Literal["chromium", "chrome", "msedge"],
    headless: bool,
    profile_dir: Path | None,
) -> AsyncIterator[BrowserContext]:
    async with browser_environment(headless) as environment:
        if engine == "playwright":
            async with async_playwright() as runtime:
                browser = await runtime.chromium.launch(
                    channel=channel, headless=headless, env=environment
                )
                try:
                    yield await browser.new_context(
                        locale="fr-FR",
                        timezone_id=DISPLAY_TIMEZONE,
                        viewport={"width": 1440, "height": 1080},
                        accept_downloads=False,
                    )
                finally:
                    await browser.close()
            return
        with TemporaryDirectory(prefix="metiquo-stake-") as temporary:
            profile = profile_dir or Path(temporary)
            profile.mkdir(parents=True, exist_ok=True)
            async with patched_playwright() as patched:
                context = await patched.chromium.launch_persistent_context(
                    profile,
                    channel=channel,
                    headless=headless,
                    no_viewport=True,
                    locale="fr-FR",
                    timezone_id=DISPLAY_TIMEZONE,
                    accept_downloads=False,
                    env=environment,
                )
                try:
                    # Patchright conserve l'API publique Playwright ; les tests navigateur
                    # vérifient ce contrat avec les deux implémentations concrètes.
                    yield cast(BrowserContext, context)
                finally:
                    await context.close()
