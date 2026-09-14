"""Scraping navigateur standard, borné et sans accès direct à une API Stake."""

import asyncio
import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from patchright.async_api import Error as PatchrightError
from patchright.async_api import TimeoutError as PatchrightTimeout
from playwright.async_api import BrowserContext, Page, Response
from playwright.async_api import Error as BrowserError
from playwright.async_api import TimeoutError as BrowserTimeout

from metiquo.contracts.stake_scraping import ScrapedMarket, StakeEventCapture
from metiquo.foundation.time import Clock, SystemClock
from metiquo.providers.stake_assets import limit_static_assets
from metiquo.providers.stake_discovery import read_discovery, write_discovery
from metiquo.providers.stake_dom import EXTRACT_DOM
from metiquo.providers.stake_parser import (
    STAKE_LIST_URL,
    StakeScrapeError,
    parse_event,
    parse_markets,
    public_url,
)
from metiquo.providers.stake_runtime import stake_context

BROWSER_ERRORS = (BrowserError, PatchrightError)
BROWSER_TIMEOUTS = (BrowserTimeout, PatchrightTimeout)


@dataclass(frozen=True, slots=True)
class ScrapeLimits:
    timeout_seconds: int = 240
    page_timeout_seconds: int = 30
    max_events: int = 40
    max_competitions: int = 30
    concurrency: int = 2
    navigation_interval_seconds: float = 1.0
    max_expansions: int = 30
    challenge_timeout_seconds: int = 45

    def __post_init__(self) -> None:
        if not (
            10 <= self.timeout_seconds <= 1800
            and 5 <= self.page_timeout_seconds <= 90
            and 1 <= self.max_events <= 100
            and 1 <= self.max_competitions <= 100
            and 1 <= self.concurrency <= 3
            and 1 <= self.navigation_interval_seconds <= 60
            and 1 <= self.max_expansions <= 100
            and 1 <= self.challenge_timeout_seconds <= 90
        ):
            raise ValueError("Limites de scraping invalides")


@dataclass(frozen=True, slots=True)
class ScrapeResult:
    captures: tuple[StakeEventCapture, ...]
    failures: tuple[str, ...]
    discovered_events: int
    blocked: bool = False


class StakeBrowserScraper:
    def __init__(
        self,
        limits: ScrapeLimits | None = None,
        *,
        clock: Clock | None = None,
        checkpoint: Callable[[], None] = lambda: None,
        channel: Literal["chromium", "chrome", "msedge"] = "chromium",
        headless: bool = True,
        engine: Literal["playwright", "patchright"] = "playwright",
        profile_dir: Path | None = None,
        discovery_cache: Path | None = None,
    ) -> None:
        self.limits = limits or ScrapeLimits()
        self.clock, self.checkpoint = clock or SystemClock(), checkpoint
        self.channel, self.headless = channel, headless
        self.engine, self.profile_dir = engine, profile_dir
        self.discovery_cache = discovery_cache
        self._next_navigation = 0.0
        self._navigation_lock: asyncio.Lock | None = None
        self._access_refusal: StakeScrapeError | None = None

    async def collect(self, urls: Sequence[str] = ()) -> ScrapeResult:
        checked_urls = tuple(dict.fromkeys(public_url(url, event_only=True) for url in urls))
        if len(checked_urls) > self.limits.max_events:
            raise ValueError("Nombre de matchs demandé supérieur à la limite")
        self._navigation_lock = asyncio.Lock()
        self._access_refusal = None
        self._next_navigation = 0.0
        completed: dict[str, StakeEventCapture] = {}
        discovered: tuple[str, ...] = ()
        failures: list[str] = []
        try:
            async with (
                asyncio.timeout(self.limits.timeout_seconds),
                stake_context(
                    engine=self.engine,
                    channel=self.channel,
                    headless=self.headless,
                    profile_dir=self.profile_dir,
                ) as context,
            ):
                context.set_default_timeout(self.limits.page_timeout_seconds * 1000)
                await limit_static_assets(context)
                # Chargement normal des images, styles, polices et scripts du site.
                discovered = checked_urls
                if not discovered and self.discovery_cache is not None:
                    discovered = read_discovery(self.discovery_cache, self.clock)
                if not discovered:
                    discovered = await self._discover(context, failures=failures)
                    if self.discovery_cache is not None and not failures:
                        try:
                            write_discovery(self.discovery_cache, self.clock, discovered)
                        except OSError:
                            failures.append("DISCOVERY_CACHE_UNAVAILABLE")
                if len(discovered) > self.limits.max_events:
                    failures.append("EVENT_LIMIT_REACHED")
                semaphore = asyncio.Semaphore(self.limits.concurrency)

                async def read(url: str) -> StakeEventCapture | None:
                    async with semaphore:
                        try:
                            if self._access_refusal is not None:
                                failures.append(f"{url.rsplit('/', 1)[1]}:NOT_ATTEMPTED")
                                return None
                            capture = await self._event(context, url)
                            completed[url] = capture
                            logging.getLogger(__name__).info(
                                "stake.event_collected %s markets=%s",
                                capture.event.provider_event_id,
                                len(capture.markets),
                            )
                            return capture
                        except StakeScrapeError as error:
                            if error.blocked:
                                self._access_refusal = error
                            failures.append(f"{url.rsplit('/', 1)[1]}:{error.code}")
                            return None
                        except BROWSER_TIMEOUTS:
                            failures.append(f"{url.rsplit('/', 1)[1]}:PAGE_TIMEOUT")
                            return None
                        except BROWSER_ERRORS:
                            failures.append(f"{url.rsplit('/', 1)[1]}:PAGE_UNAVAILABLE")
                            return None
                        except (ValueError, KeyError, TypeError):
                            failures.append(f"{url.rsplit('/', 1)[1]}:DOM_SCHEMA_CHANGED")
                            return None

                tasks = [
                    asyncio.create_task(read(url)) for url in discovered[: self.limits.max_events]
                ]
                try:
                    captures = await asyncio.gather(*tasks)
                finally:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                return ScrapeResult(
                    tuple(c for c in captures if c is not None),
                    tuple(failures),
                    len(discovered),
                    blocked=self._access_refusal is not None,
                )
        except TimeoutError:
            if completed:
                return ScrapeResult(
                    tuple(completed[url] for url in discovered if url in completed),
                    (*failures, "RUN_TIMEOUT"),
                    len(discovered),
                    blocked=self._access_refusal is not None,
                )
            raise StakeScrapeError("RUN_TIMEOUT", "Délai global de collecte dépassé") from None
        except BROWSER_ERRORS:
            raise StakeScrapeError(
                "BROWSER_UNAVAILABLE", "Navigateur indisponible ou navigation interrompue"
            ) from None

    async def _navigate(self, page: Page, url: str) -> None:
        self.checkpoint()
        assert self._navigation_lock is not None
        async with self._navigation_lock:
            await asyncio.sleep(max(0, self._next_navigation - time.monotonic()))
            if self._access_refusal is not None:
                raise self._access_refusal
            self._next_navigation = time.monotonic() + self.limits.navigation_interval_seconds
        latest: Response | None = None

        def observe(response: Response) -> None:
            nonlocal latest
            if response.request.is_navigation_request() and response.frame == page.main_frame:
                latest = response

        page.on("response", observe)
        try:
            response = await page.goto(public_url(url), wait_until="domcontentloaded")
            if response and response.headers.get("cf-mitigated") == "challenge":
                # Laisser le navigateur exécuter la vérification JavaScript du site.
                # Un 403 définitif ou un CAPTCHA non résolu ne devient jamais un succès.
                try:
                    await page.locator("#main-content").wait_for(
                        timeout=self.limits.challenge_timeout_seconds * 1000
                    )
                except BROWSER_TIMEOUTS:
                    raise StakeScrapeError(
                        "ACCESS_CHALLENGE", "Vérification Cloudflare non résolue", blocked=True
                    ) from None
                response = latest
                if not response or response.status != 200 or response.headers.get("cf-mitigated"):
                    raise StakeScrapeError(
                        "ACCESS_CHALLENGE", "Vérification Cloudflare non résolue", blocked=True
                    )
            code = response.status if response else 0
        finally:
            page.remove_listener("response", observe)
        logging.getLogger(__name__).info(
            "stake.navigation", extra={"route": url, "status_code": code}
        )
        if code in {401, 403, 429, 451}:
            raise StakeScrapeError(
                f"HTTP_{code}", f"Stake refuse la collecte publique (HTTP {code})", blocked=True
            )
        if code != 200:
            raise StakeScrapeError(f"HTTP_{code}", "Page Stake indisponible")
        if "just a moment" in (await page.title()).casefold():
            raise StakeScrapeError(
                "ACCESS_CHALLENGE", "Page de contrôle d'accès Stake", blocked=True
            )
        try:
            if public_url(page.url) != public_url(url):
                raise ValueError("Identité de page modifiée")
        except ValueError:
            raise StakeScrapeError(
                "UNEXPECTED_REDIRECT", "Redirection hors page publique attendue"
            ) from None
        await page.locator("#main-content").wait_for()
        # Attendre les liens français rendus côté client : le SSR initial utilise un autre fuseau.
        await page.locator('a[href^="/fr/sports/league-of-legends/"]').first.wait_for()
        await asyncio.sleep(0.75)

    async def _expand(self, page: Page) -> tuple[str, ...]:
        # Le slider de score peut afficher une combinaison suspendue alors que les autres
        # scores sont ouverts. "Tout" est un contrôle d'affichage, jamais une sélection.
        revealed_scores: set[str] = set()
        for step in range(self.limits.max_expansions + 1):
            self.checkpoint()
            closed = page.locator(
                "#main-content .secondary-accordion:not(.is-open) > .header:visible"
            )
            more = page.locator('#main-content [data-testid="load-more"]:visible')
            headers = page.locator(
                "#main-content .secondary-accordion.level-2 > .header:visible"
            ).filter(has=page.get_by_role("button", name="Tout", exact=True))
            score = None
            score_label = ""
            for index in range(await headers.count()):
                header = headers.nth(index)
                label = await header.locator("[data-ds-text]").first.text_content()
                all_scores = header.get_by_role("button", name="Tout", exact=True)
                if label and label not in revealed_scores and await all_scores.is_visible():
                    score, score_label = all_scores, label
                    break
            if not await closed.count() and not await more.count() and score is None:
                return ()
            if step == self.limits.max_expansions:
                return ("EXPANSION_LIMIT_REACHED",)
            if await closed.count():
                await closed.first.click()
            elif await more.count():
                await more.first.click()
            elif score is not None:
                await score.click()
                revealed_scores.add(score_label)
            await asyncio.sleep(0.25)
        raise AssertionError("Boucle de dépliage bornée")

    async def _dom(self, page: Page) -> dict[str, Any]:
        self.checkpoint()
        value: dict[str, Any] = await page.evaluate(EXTRACT_DOM)
        return value

    async def _discover(
        self, context: BrowserContext, *, failures: list[str] | None = None
    ) -> tuple[str, ...]:
        failures = failures if failures is not None else []
        page = await context.new_page()
        try:
            await self._navigate(page, STAKE_LIST_URL)
            if await self._expand(page):
                raise StakeScrapeError("DISCOVERY_INCOMPLETE", "Liste des compétitions incomplète")
            dom = await self._dom(page)
            competitions = self._links(dom, segments=5)
            if not competitions:
                raise StakeScrapeError("COMPETITIONS_MISSING", "Liste des compétitions absente")
            if len(competitions) > self.limits.max_competitions:
                failures.append("COMPETITION_LIMIT_REACHED")
            events: dict[str, None] = {}
            for url in competitions[: self.limits.max_competitions]:
                try:
                    await self._navigate(page, url)
                    if await self._expand(page):
                        failures.append(f"{url.rsplit('/', 1)[1]}:DISCOVERY_INCOMPLETE")
                    for event in self._links(await self._dom(page), segments=6):
                        events[event] = None
                except StakeScrapeError as error:
                    if error.blocked:
                        raise StakeScrapeError(
                            error.code, f"{url.rsplit('/', 1)[1]} : {error}", blocked=True
                        ) from None
                    failures.append(f"{url.rsplit('/', 1)[1]}:{error.code}")
                except BROWSER_TIMEOUTS:
                    failures.append(f"{url.rsplit('/', 1)[1]}:PAGE_TIMEOUT")
                except BROWSER_ERRORS:
                    failures.append(f"{url.rsplit('/', 1)[1]}:PAGE_UNAVAILABLE")
            if not events:
                raise StakeScrapeError("NO_EVENTS", "Aucun match découvert sur les pages publiques")
            return tuple(events)
        finally:
            await page.close()

    @staticmethod
    def _links(dom: dict[str, Any], *, segments: int) -> tuple[str, ...]:
        links: dict[str, None] = {}
        for link in dom["links"]:
            try:
                url = public_url(link, event_only=segments == 6)
            except ValueError:
                continue
            if len(url.removeprefix("https://stake.bet/").split("/")) == segments:
                links[url] = None
        return tuple(links)

    async def _event(self, context: BrowserContext, url: str) -> StakeEventCapture:
        page = await context.new_page()
        try:
            await self._navigate(page, url)
            await page.locator('#main-content [data-testid="tab-main"]').wait_for()
            first = await self._dom(page)
            # Refuser tout de suite les matchs sans début vérifiable, notamment le live.
            initial_event = parse_event(first, self.clock.now().value)
            tabs = tuple(first["tabs"])
            if not tabs or tabs[0] != "tab-main" or len(tabs) > 10:
                raise StakeScrapeError("TABS_CHANGED", "Navigation des marchés non reconnue")
            markets: list[ScrapedMarket] = []
            visited: list[str] = []
            warnings: list[str] = []
            for tab in tabs:
                if tab != "tab-main" and not re.fullmatch(r"tab-map-[1-5]", tab):
                    warnings.append(f"UNSUPPORTED_TAB:{tab}")
                    continue
                # Le premier onglet est déjà chargé : recliquer peut réinitialiser
                # ses contrôles alors que leur dépliage est en cours.
                if tab != "tab-main":
                    await page.get_by_test_id(tab).click()
                await page.wait_for_function(
                    """tab => {
                      const labels = Array.from(document.querySelectorAll(
                        '#main-content .secondary-accordion.level-2 > .header [data-ds-text]'
                      )).filter(n => n.getClientRects().length > 0)
                        .map(n => n.textContent.trim());
                      if (!labels.length) return false;
                      const map = tab.replace('tab-map-', '');
                      return tab === 'tab-main' ? labels.some(x => !x.startsWith('Map ')) :
                        labels.every(x => x.startsWith('Map ' + map + ' ') ||
                          x.endsWith(', sur la carte ' + map));
                    }""",
                    arg=tab,
                )
                warnings.extend(await self._expand(page))
                dom = await self._dom(page)
                if tab == "tab-main":
                    initial_event = parse_event(dom, self.clock.now().value)
                if tab != "tab-main":
                    prefix = "Map " + tab.removeprefix("tab-map-") + " "
                    if not dom["markets"] or not all(
                        m["label"].startswith(prefix)
                        or m["label"].endswith(", sur la carte " + tab.removeprefix("tab-map-"))
                        for m in dom["markets"]
                    ):
                        raise StakeScrapeError("TAB_NOT_READY", "L'onglet demandé n'est pas chargé")
                at = self.clock.now().value
                markets.extend(parse_markets(dom, tab, at))
                visited.append(tab)
            if any(not m.expanded or not m.outcomes for m in markets):
                warnings.append("MARKETS_WITHOUT_VISIBLE_OUTCOMES")
            event = parse_event(dom, self.clock.now().value)
            if (
                dom["participants"] != first["participants"]
                or dom["competition"] != first["competition"]
            ):
                raise StakeScrapeError(
                    "EVENT_CHANGED", "Identité du match modifiée pendant la lecture"
                )
            # Le dernier onglet n'expose plus le marché du match avec les noms complets.
            event = event.model_copy(update={"participants": initial_event.participants})
            return StakeEventCapture(
                event=event,
                source_url=url,
                observed_at=self.clock.now().value,
                expected_tabs=tabs,
                visited_tabs=tuple(visited),
                markets=tuple(markets),
                warnings=tuple(dict.fromkeys(warnings)),
            )
        finally:
            await page.close()
