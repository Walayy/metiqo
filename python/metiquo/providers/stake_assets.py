"""Borner les téléchargements statiques sans supprimer de ressource de la page."""

import asyncio
from contextlib import suppress
from weakref import WeakKeyDictionary, WeakSet

from patchright.async_api import Error as PatchrightError
from playwright.async_api import BrowserContext, Frame, Page, Request, Route
from playwright.async_api import Error as BrowserError


async def limit_static_assets(context: BrowserContext, *, concurrency: int = 32) -> None:
    """Éviter ERR_INSUFFICIENT_RESOURCES pendant les rafales de modules du site.

    La place reste occupée jusqu'à la fin du téléchargement, pas seulement jusqu'à
    l'envoi de la requête. Les documents et requêtes métier restent gérés normalement
    par le navigateur. Le routage Playwright désactive son cache HTTP.
    """
    if not 1 <= concurrency <= 128:
        raise ValueError("Concurrence des ressources statiques invalide")
    slots = asyncio.Semaphore(concurrency)
    active: dict[Request, Frame] = {}
    finished: WeakSet[Request] = WeakSet()
    generations: WeakKeyDictionary[Frame, int] = WeakKeyDictionary()
    closed = False

    def release(request: Request) -> None:
        finished.add(request)
        if request in active:
            del active[request]
            slots.release()

    def invalidate(frame: Frame) -> None:
        generations[frame] = generations.get(frame, 0) + 1
        for request, owner in tuple(active.items()):
            if owner == frame or owner.is_detached():
                release(request)

    def close_page(page: Page) -> None:
        for frame in tuple(generations):
            if frame.page == page:
                invalidate(frame)

    def watch(page: Page) -> None:
        page.on("framedetached", invalidate)
        page.on("close", close_page)

    def navigate(request: Request) -> None:
        # history.replaceState et les changements d'onglet ne remplacent pas le
        # document : leurs téléchargements doivent continuer jusqu'au bout.
        if request.is_navigation_request():
            with suppress(BrowserError, PatchrightError):
                invalidate(request.frame)

    def close(_context: BrowserContext) -> None:
        nonlocal closed
        closed = True
        for request in tuple(active):
            release(request)

    async def route_asset(route: Route) -> None:
        try:
            frame = route.request.frame
        except (BrowserError, PatchrightError):
            await route.fallback()
            return
        generation = generations.setdefault(frame, 0)
        await slots.acquire()
        if (
            closed
            or route.request in finished
            or frame.is_detached()
            or generations.get(frame) != generation
        ):
            slots.release()
            return
        active[route.request] = frame
        try:
            await route.fallback()
        except (BrowserError, PatchrightError):
            # Une page peut être fermée pendant que ses modules attendent leur tour.
            release(route.request)
        except BaseException:
            release(route.request)
            raise

    context.on("requestfinished", release)
    context.on("requestfailed", release)
    context.on("request", navigate)
    context.on("close", close)
    context.on("page", watch)
    for page in context.pages:
        watch(page)
    await context.route("https://stake.bet/_app/**", route_asset)
