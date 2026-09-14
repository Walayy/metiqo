"""Orchestration du scraping, conservation intégrale et temporisation durable."""

import asyncio
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.config import ObjectStoreBackend, OddsProvider, Settings
from metiquo.contracts.enums import DataMode
from metiquo.db.odds_models import StakePageCapture, StakeScrapeRun
from metiquo.foundation.locks import resource_lock
from metiquo.foundation.time import Clock, SystemClock
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.providers.manual_import import ManualImportOddsProvider
from metiquo.providers.stake_browser import ScrapeLimits, ScrapeResult, StakeBrowserScraper
from metiquo.providers.stake_browser_file import StakeBrowserFileScraper
from metiquo.providers.stake_parser import PROVIDER_CODE, StakeScrapeError
from metiquo.providers.stake_public import winner_provider
from metiquo.services.odds_capture import OddsCaptureService, OddsCaptureSource


class PublicScraper(Protocol):
    async def collect(self, urls: Sequence[str] = ()) -> ScrapeResult: ...


def scrape_stake(
    engine: Engine,
    settings: Settings,
    urls: Sequence[str] = (),
    *,
    clock: Clock | None = None,
    scraper: PublicScraper | None = None,
    checkpoint: Callable[[], None] = lambda: None,
) -> dict[str, object]:
    if (
        settings.app_data_mode is not DataMode.REAL
        or settings.odds_provider is not OddsProvider.STAKE_PUBLIC
    ):
        raise ValueError("La collecte exige APP_DATA_MODE=real et ODDS_PROVIDER=stake_public")
    if settings.object_store_backend is not ObjectStoreBackend.FILESYSTEM:
        raise ValueError("La collecte exige OBJECT_STORE_BACKEND=filesystem")
    clock = clock or SystemClock()
    file_mode = scraper is None and settings.stake_browser_capture_file is not None
    source = OddsCaptureSource("public_scrape", "Stake · pages publiques", "stake-public:attempt")
    capture_service = OddsCaptureService(engine, clock)
    with resource_lock(engine, "stake:browser"):
        checkpoint()
        started = clock.now().value
        with engine.connect() as connection:
            last = connection.execute(
                select(StakeScrapeRun.__table__)
                .order_by(StakeScrapeRun.finished_at.desc(), StakeScrapeRun.id.desc())
                .limit(1)
            ).first()
        next_allowed = last.next_attempt_at if last is not None else started
        if file_mode and last is not None:
            # Lire un fichier local ne sollicite pas Stake : le délai réseau d'une
            # ancienne tentative ne doit pas empêcher de recevoir un nouvel export.
            next_allowed = min(
                next_allowed,
                last.finished_at + timedelta(seconds=settings.stake_scrape_interval_seconds),
            )
        if next_allowed > started:
            return {
                "command": "odds-scrape",
                "state": "cooldown",
                "events": 0,
                "nextAttemptAt": next_allowed.isoformat(),
                "detail": last.detail if last is not None else None,
            }
        if scraper is None and settings.stake_browser_capture_file is not None:
            scraper = StakeBrowserFileScraper(
                settings.stake_browser_capture_file,
                clock=clock,
                max_age_seconds=settings.odds_provider_max_age_seconds.get(
                    PROVIDER_CODE, settings.odds_max_age_seconds
                ),
            )
        scraper = scraper or StakeBrowserScraper(
            ScrapeLimits(
                timeout_seconds=settings.stake_scrape_timeout_seconds,
                max_events=settings.stake_scrape_max_events,
                concurrency=settings.stake_scrape_concurrency,
                navigation_interval_seconds=settings.stake_scrape_navigation_interval_seconds,
            ),
            clock=clock,
            checkpoint=checkpoint,
            channel=settings.stake_browser_channel,
            headless=settings.stake_browser_headless,
            engine=settings.stake_browser_engine,
            profile_dir=settings.object_store_root / "work" / "stake-browser",
            discovery_cache=settings.object_store_root / "work" / "stake-discovery.json",
        )
        detail: str | None
        try:
            result = asyncio.run(scraper.collect(urls))
        except StakeScrapeError as error:
            result = ScrapeResult((), (error.code,), 0)
            state = "blocked" if error.blocked else "failed"
            detail = f"{error.code} : {error}"
        else:
            state = (
                "partial"
                if result.failures or any(c.warnings for c in result.captures)
                else "operational"
            )
            if not result.captures:
                state = "failed"
            if result.blocked:
                state = "blocked"
            detail = "; ".join(result.failures)[:512] or None
        checkpoint()
        finished = clock.now().value
        # Des captures futures sont refusées avant toute archive ou publication.
        if any(c.observed_at > finished for c in result.captures):
            raise ValueError("La capture navigateur ne peut pas être future")
        delay = settings.stake_scrape_interval_seconds
        if not file_mode and state in {"blocked", "failed"}:
            delay = settings.stake_scrape_backoff_seconds
            if last is not None and last.status in {"blocked", "failed"}:
                delay = max(
                    delay,
                    min(86400, int((last.next_attempt_at - last.finished_at).total_seconds()) * 2),
                )
        next_attempt = finished + timedelta(seconds=delay)
        run_id = uuid4()
        stored_captures = []
        store = FilesystemObjectStore(settings.object_store_root / "odds")
        for capture in result.captures:
            checkpoint()
            provider = winner_provider(capture, clock)
            payload = capture.model_dump_json(by_alias=True).encode()
            stored = store.put_source(year=finished.year, chunks=(payload,), source_kind="bin")
            stored_captures.append((capture, provider, stored))
        inserted = 0
        with engine.begin() as connection:
            connection.execute(
                insert(StakeScrapeRun).values(
                    id=run_id,
                    started_at=started,
                    finished_at=finished,
                    status=state,
                    detail=detail,
                    next_attempt_at=next_attempt,
                    event_count=len(result.captures),
                )
            )
            for capture, provider, stored in stored_captures:
                reference = f"odds/{stored.object_key}"
                connection.execute(
                    insert(StakePageCapture)
                    .values(
                        id=uuid5(NAMESPACE_URL, f"stake-public:{stored.sha256}"),
                        run_id=run_id,
                        provider_event_id=capture.event.provider_event_id,
                        starts_at=capture.event.starts_at,
                        observed_at=capture.observed_at,
                        sha256=stored.sha256,
                        raw_payload_reference=reference,
                        payload=capture.model_dump(mode="json", by_alias=True),
                    )
                    .on_conflict_do_nothing(index_elements=["sha256"])
                )
                if provider.observation_count:
                    report = capture_service.capture_event(
                        provider,
                        capture.event,
                        OddsCaptureSource(
                            "public_scrape", source.provider_display_name, reference, stored.sha256
                        ),
                        connection=connection,
                    )
                    inserted += report.inserted_snapshots
        if state != "operational":
            capture_service.record_failure(
                ManualImportOddsProvider(PROVIDER_CODE, clock=clock),
                source,
                clock.now().value,
                StakeScrapeError(state.upper(), detail or "Collecte partielle"),
            )
        return {
            "command": "odds-scrape",
            "collectionMode": "public_scrape",
            "state": state,
            "runId": str(run_id),
            "events": len(result.captures),
            "discoveredEvents": result.discovered_events,
            "markets": sum(len(c.markets) for c in result.captures),
            "outcomes": sum(len(m.outcomes) for c in result.captures for m in c.markets),
            "insertedSnapshots": inserted,
            "detail": detail,
            "nextAttemptAt": next_attempt.isoformat(),
        }
