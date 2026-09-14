"""Transport local des DOM lus par l'extension ; aucun accès réseau ni exécution de code."""

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, ValidationError

from metiquo.contracts.base import ContractModel, NonEmptyText, UtcDateTime
from metiquo.contracts.stake_scraping import ScrapedMarket, StakeEventCapture
from metiquo.foundation.time import Clock, SystemClock
from metiquo.providers.stake_browser import ScrapeResult
from metiquo.providers.stake_parser import StakeScrapeError, parse_event, parse_markets, public_url

MAX_EXPORT_BYTES = 16 * 1024 * 1024


class BrowserState(ContractModel):
    tab: NonEmptyText
    captured_at: UtcDateTime = Field(alias="capturedAt")
    dom: dict[str, Any]


class BrowserCapture(ContractModel):
    url: NonEmptyText
    time_zone: NonEmptyText = Field(alias="timeZone")
    started_at: UtcDateTime = Field(alias="startedAt")
    observed_at: UtcDateTime = Field(alias="observedAt")
    expected_tabs: tuple[NonEmptyText, ...] = Field(
        alias="expectedTabs", min_length=1, max_length=10
    )
    states: tuple[BrowserState, ...] = Field(min_length=1, max_length=10)
    warnings: tuple[NonEmptyText, ...] = Field(max_length=100)


class BrowserExport(ContractModel):
    format: Literal["metiquo.stake-browser.v1"]
    exported_at: UtcDateTime = Field(alias="exportedAt")
    discovered_events: int = Field(alias="discoveredEvents", ge=0, le=10000)
    captures: tuple[BrowserCapture, ...] = Field(max_length=40)
    failures: tuple[NonEmptyText, ...] = Field(max_length=400)
    blocked: bool


def convert_capture(raw: BrowserCapture) -> StakeEventCapture:
    url = public_url(raw.url, event_only=True)
    ZoneInfo(raw.time_zone)  # Valider le fuseau réellement déclaré par le navigateur.
    tabs = tuple(state.tab for state in raw.states)
    if (
        tabs[0] != "tab-main"
        or raw.expected_tabs[0] != "tab-main"
        or len(set(tabs)) != len(tabs)
        or len(set(raw.expected_tabs)) != len(raw.expected_tabs)
        or not set(tabs) <= set(raw.expected_tabs)
    ):
        raise ValueError("Navigation d'onglets incohérente")
    initial = raw.states[0].dom
    markets: list[ScrapedMarket] = []
    previous_at = raw.started_at
    for state in raw.states:
        if not previous_at <= state.captured_at <= raw.observed_at:
            raise ValueError("Chronologie de lecture incohérente")
        previous_at = state.captured_at
        dom = state.dom
        if (
            public_url(dom["url"], event_only=True) != url
            or dom["participants"] != initial["participants"]
            or dom["competition"] != initial["competition"]
            or tuple(dom["tabs"]) != raw.expected_tabs
        ):
            raise ValueError("L'identité du match a changé")
        if state.tab != "tab-main":
            if not re.fullmatch(r"tab-map-[1-5]", state.tab):
                raise ValueError("Onglet non pris en charge")
            prefix = "Map " + state.tab.removeprefix("tab-map-") + " "
            if not dom["markets"] or any(not m["label"].startswith(prefix) for m in dom["markets"]):
                raise ValueError("Marchés d'un autre onglet")
        markets.extend(parse_markets(dom, state.tab, state.captured_at))
    event = parse_event(initial, raw.observed_at, display_timezone=raw.time_zone)
    last_event = parse_event(raw.states[-1].dom, raw.observed_at, display_timezone=raw.time_zone)
    if event.starts_at != last_event.starts_at:
        raise ValueError("L'heure du match a changé")
    warnings = list(raw.warnings)
    if any(not m.expanded or not m.outcomes for m in markets):
        warnings.append("MARKETS_WITHOUT_VISIBLE_OUTCOMES")
    return StakeEventCapture(
        event=event,
        source_url=url,
        observed_at=raw.observed_at,
        expected_tabs=raw.expected_tabs,
        visited_tabs=tabs,
        markets=tuple(markets),
        warnings=tuple(dict.fromkeys(warnings)),
    )


class StakeBrowserFileScraper:
    def __init__(
        self, path: Path, *, clock: Clock | None = None, max_age_seconds: int = 90
    ) -> None:
        self.path, self.clock = path, clock or SystemClock()
        self.max_age_seconds = max_age_seconds

    async def collect(self, urls: Sequence[str] = ()) -> ScrapeResult:
        selected = {public_url(url, event_only=True) for url in urls}
        try:
            with self.path.open("rb") as stream:
                payload = stream.read(MAX_EXPORT_BYTES + 1)
        except OSError:
            raise StakeScrapeError(
                "BROWSER_EXPORT_MISSING", "Export du navigateur indisponible"
            ) from None
        try:
            if len(payload) > MAX_EXPORT_BYTES:
                raise ValueError("Export trop volumineux")
            export = BrowserExport.model_validate_json(payload)
            if export.exported_at > self.clock.now().value:
                raise ValueError("Export daté dans le futur")
            captures = []
            failures = list(export.failures)
            seen: set[str] = set()
            for raw in export.captures:
                if raw.observed_at > export.exported_at:
                    raise ValueError("Capture postérieure à l'export")
                source_url = public_url(raw.url, event_only=True)
                if source_url in seen:
                    raise ValueError("Match dupliqué dans l'export")
                seen.add(source_url)
                try:
                    capture = convert_capture(raw)
                except StakeScrapeError as error:
                    if error.code not in {"EVENT_ALREADY_STARTED", "START_TIME_MISSING"}:
                        raise
                    failures.append(f"{source_url.rsplit('/', 1)[1]}:{error.code}")
                    continue
                if not selected or capture.source_url in selected:
                    captures.append(capture)
            if export.discovered_events < len(export.captures):
                raise ValueError("Nombre de matchs incohérent")
            if (
                self.clock.now().value - export.exported_at
            ).total_seconds() > self.max_age_seconds or any(
                (self.clock.now().value - min(m.captured_at for m in c.markets)).total_seconds()
                > self.max_age_seconds
                for c in captures
            ):
                failures.append("BROWSER_EXPORT_STALE")
            failures.extend(
                f"{url.rsplit('/', 1)[1]}:NOT_IN_EXPORT" for url in sorted(selected - seen)
            )
            return ScrapeResult(
                tuple(captures), tuple(failures), export.discovered_events, export.blocked
            )
        except (ValueError, KeyError, TypeError, ValidationError, ZoneInfoNotFoundError) as error:
            raise StakeScrapeError(
                "BROWSER_EXPORT_INVALID", "Export navigateur invalide"
            ) from error


def main() -> None:
    """Diagnostic local utilisable sans PostgreSQL ni serveur HTTP."""
    import asyncio

    parser = argparse.ArgumentParser(description="Valider un export DOM du navigateur")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        result = asyncio.run(StakeBrowserFileScraper(args.file).collect())
    except StakeScrapeError as error:
        print(json.dumps({"state": "failed", "code": error.code, "detail": str(error)}))
        raise SystemExit(2) from None
    partial = bool(result.failures or any(c.warnings for c in result.captures))
    print(
        json.dumps(
            {
                "state": "blocked"
                if result.blocked
                else "failed"
                if not result.captures
                else "partial"
                if partial
                else "validated",
                "events": len(result.captures),
                "failures": result.failures,
                "warnings": [w for c in result.captures for w in c.warnings],
                "markets": sum(len(c.markets) for c in result.captures),
                "outcomes": sum(len(m.outcomes) for c in result.captures for m in c.markets),
                "observedAt": [c.observed_at.isoformat() for c in result.captures],
            }
        )
    )
    if result.blocked or partial or not result.captures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
