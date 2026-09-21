import logging
import time

import httpx
from bs4 import BeautifulSoup
from metiquo_core.config import Settings
from patchright.sync_api import Error as BrowserError
from patchright.sync_api import Route, expect, sync_playwright

from metiquo_worker.archive import FILENAME, SourceFile, is_export_url

logger = logging.getLogger(__name__)


def parse_inventory(html: str) -> list[SourceFile]:
    soup = BeautifulSoup(html, "html.parser")
    files: dict[str, SourceFile] = {}
    years: set[int] = set()
    for row in soup.select('[data-id][data-target="doc"]'):
        filename = row.find("strong")
        if filename is None:
            continue
        name = filename.get_text(strip=True)
        match = FILENAME.fullmatch(name)
        if match is None:
            continue
        file_id = str(row["data-id"])
        year = int(match[1])
        if name in files or year in years:
            raise ValueError("Drive inventory contains ambiguous annual files")
        files[name] = SourceFile(file_id, name, year)
        years.add(year)
    if len(files) < 2:
        raise ValueError("Drive inventory is unavailable or insufficient for a group export")
    return sorted(files.values(), key=lambda item: item.year)


def discover(settings: Settings) -> list[SourceFile]:
    response = httpx.get(settings.oracle_folder_url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    return parse_inventory(response.text)


def select_files(inventory: list[SourceFile], years: set[int] | None) -> list[SourceFile]:
    if years is None:
        return inventory
    selected = [file for file in inventory if file.year in years]
    if {file.year for file in selected} != years or not selected:
        raise ValueError("Requested year is absent from the Drive inventory")
    if len(selected) == 1:
        selected.append(next(file for file in inventory if file.id != selected[0].id))
    return sorted(selected, key=lambda item: item.year)


def export_url(settings: Settings, selected: list[SourceFile]) -> str:
    """Use the public multi-file Download action and capture its generated GCS archive."""
    urls: list[str] = []

    def capture(route: Route) -> None:
        url = route.request.url
        if is_export_url(url) and url not in urls:
            urls.append(url)
        route.abort()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.browser_headless, channel="chromium")
        try:
            context = browser.new_context(locale="en-US", accept_downloads=True)
            context.route("https://storage.googleapis.com/drive-bulk-export-anonymous/**", capture)
            page = context.new_page()
            page.set_default_timeout(30_000)
            page.goto(settings.oracle_folder_url, wait_until="domcontentloaded", timeout=60_000)
            # Wait for Drive's hydrated grid, not the transient initial HTML table.
            page.get_by_role("grid").wait_for(timeout=60_000)
            close = page.get_by_role("button", name="Close", exact=True)
            if close.is_visible():
                close.click()
            page.keyboard.press("Escape")
            for index, file in enumerate(selected):
                row = page.get_by_role("row").filter(has=page.get_by_text(file.name, exact=True))
                row.click(modifiers=["Control"] if index else [])
                expect(row).to_have_attribute("aria-selected", "true", timeout=10_000)
            selected_rows = page.locator('[role="row"][aria-selected="true"]')
            try:
                expect(selected_rows).to_have_count(len(selected), timeout=10_000)
                for file in selected:
                    expect(
                        page.get_by_role("row").filter(has=page.get_by_text(file.name, exact=True))
                    ).to_have_attribute("aria-selected", "true", timeout=10_000)
            except AssertionError:
                raise ValueError(
                    f"Drive selection mismatch: expected {len(selected)}, "
                    f"selected {selected_rows.count()}"
                ) from None
            page.get_by_role("row").filter(
                has=page.get_by_text(selected[-1].name, exact=True)
            ).click(button="right")
            page.get_by_role("menuitem", name="Download", exact=True).click()
            logger.info("Drive ZIP export requested: %s files", len(selected))
            deadline = time.monotonic() + settings.oracle_export_timeout_seconds
            while not urls and time.monotonic() < deadline:
                page.wait_for_timeout(500)
                # Drive may render a download link inside an iframe instead of navigating it.
                for frame in page.frames:
                    try:
                        links = frame.locator(
                            'a[href^="https://storage.googleapis.com/drive-bulk-export-anonymous/"]'
                        )
                        for link in links.all():
                            href = link.get_attribute("href")
                            if href and is_export_url(href) and href not in urls:
                                urls.append(href)
                    except BrowserError as error:
                        if frame.is_detached() or "Execution context was destroyed" in str(error):
                            # Drive replaces its hidden frames while preparing an export.
                            continue
                        raise
            if len(urls) != 1:
                raise ValueError("Drive did not produce one complete export within the deadline")
            return urls[0]
        finally:
            browser.close()
