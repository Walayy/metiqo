"""Bounded, resumable LoLTV HTML collection with one shared source budget."""

import gzip
import hashlib
import logging
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from metiquo_core.config import Settings
from metiquo_core.models import IngestionRun, MatchSourceLink
from pydantic import TypeAdapter
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from metiquo_worker.artifacts import store_bytes
from metiquo_worker.jobs import source_lock, start_run
from metiquo_worker.loltv_archive import discover_archived_events
from metiquo_worker.loltv_policy import LoltvBlocked, LoltvBudgetExhausted, LoltvPolicy
from metiquo_worker.loltv_publication import _publish_events
from metiquo_worker.oracle_match_sync import sync_oracle_match_details
from metiquo_worker.sources.loltv import ROOT_URL, SOURCE, LoltvEvent, detail, listing

logger = logging.getLogger(__name__)
LOCK_ID = 7_346_810_210
PARIS = ZoneInfo("Europe/Paris")
MAX_LISTING_CACHE_AGE_SECONDS = 24 * 60 * 60


def next_live_due(data: dict[str, object], settings: Settings) -> float | None:
    """An extra scheduler wakeup only for due live reads, behind all source gates."""
    checkpoint = data.get("checkpoint")
    events = checkpoint.get("events") if isinstance(checkpoint, dict) else None
    if not isinstance(events, dict):
        return None
    due = [
        float(item["due"])
        for item in events.values()
        if isinstance(item, dict)
        and isinstance(item.get("event"), dict)
        and item["event"].get("status") == "live"
        and isinstance(item.get("due"), (int, float))
    ]
    if not due:
        return None
    gates = [min(due)]
    blocked = data.get("blockedUntil")
    if isinstance(blocked, (int, float)):
        gates.append(float(blocked))
    # A failed cycle must not be dispatched every five seconds without making progress.
    started = checkpoint.get("cycleStartedAt") if isinstance(checkpoint, dict) else None
    if isinstance(started, (int, float)) and min(due) <= started:
        gates.append(float(started) + settings.loltv_live_refresh_seconds)
    budget_start, count = data.get("budgetStart"), data.get("budgetCount")
    if (
        isinstance(budget_start, (int, float))
        and isinstance(count, int)
        and count >= settings.loltv_request_budget
    ):
        gates.append(float(budget_start) + settings.loltv_budget_window_seconds)
    return max(gates)


def complete_map(game: object) -> bool:
    return (
        isinstance(game, dict)
        and game.get("status") == "finished"
        and isinstance(game.get("sides"), list)
        and len(game["sides"]) == 2
        and all(
            isinstance(side, dict)
            and isinstance(side.get("players"), list)
            and len(side["players"]) == 5
            for side in game["sides"]
        )
    )


def complete(event: LoltvEvent, acquired: set[str] | None = None) -> bool:
    rendered = event.payload.get("rendered")
    maps = rendered.get("maps") if isinstance(rendered, dict) else None
    if not isinstance(maps, list) or not maps:
        return False
    expected = (event.home_score or 0) + (event.away_score or 0)
    return (
        event.status == "finished"
        and len(maps) == expected
        and all(
            complete_map(game)
            or (
                isinstance(game, dict)
                and game.get("status") == "finished"
                and str(game.get("sourceGameId")) in (acquired or set())
            )
            for game in maps
        )
    )


def encode_event(event: LoltvEvent) -> dict[str, object]:
    return {**asdict(event), "starts_at": event.starts_at.isoformat()}


def decode_event(value: dict[str, object]) -> LoltvEvent:
    return TypeAdapter(LoltvEvent).validate_python(value)


def has_active_feed(event: LoltvEvent, states: dict[str, object]) -> bool:
    games = event.payload.get("sourceGames")
    current_number = (event.home_score or 0) + (event.away_score or 0) + 1
    for game in games if isinstance(games, list) else []:
        if not isinstance(game, dict):
            continue
        feed = states.get(str(game.get("id")))
        if (
            game.get("number") == current_number
            and game.get("livefeed") is True
            and game.get("state") in {"STARTED", "PAUSED"}
            and not (isinstance(feed, dict) and feed.get("state") == "COMPLETED")
        ):
            return True
    return False


class Collector:
    def __init__(self, engine: Engine, settings: Settings, policy: LoltvPolicy, run_id: UUID):
        self.engine, self.settings, self.policy, self.run_id = engine, settings, policy, run_id
        checkpoint = policy.read().get("checkpoint")
        self.state = cast(dict[str, object], checkpoint) if isinstance(checkpoint, dict) else {}
        if self.state.get("version") != 1:
            self.state = {"version": 1, "pages": {}, "events": {}}
        self.pages = cast(dict[str, dict[str, object]], self.state.setdefault("pages", {}))
        self.events = cast(dict[str, dict[str, object]], self.state.setdefault("events", {}))
        self.visited: set[str] = set()
        self.live_attempts: dict[str, float] = {}
        self.details: dict[str, object] = {
            "pages": [],
            "published": 0,
            "created": 0,
            "errors": [],
            "transport": "public-html-and-anonymous-feed"
            if settings.loltv_feed_enabled
            else "public-html",
        }
        self.observed_ids: set[str] = set()
        self.browser = None
        today = datetime.now(PARIS).date()
        self.first, self.last = today - timedelta(days=7), today + timedelta(days=7)
        self.events = {
            key: item
            for key, item in self.events.items()
            if self.in_window(decode_event(cast(dict[str, object], item["event"])).starts_at)
        }
        self.state["events"] = self.events
        for url in (ROOT_URL + "/matches", ROOT_URL + "/matches/results"):
            self.pages.setdefault(url, {"due": 0, "root": url})

    def live_interval(self) -> int:
        # Leave 30% of the existing budget for listings, sessions and corrections.
        # With many simultaneous matches, spread reads instead of raising the cap.
        count = sum(
            decode_event(cast(dict[str, object], item["event"])).status == "live"
            for item in self.events.values()
        )
        return max(
            self.settings.loltv_live_refresh_seconds,
            int(
                count
                * self.settings.loltv_budget_window_seconds
                / (self.settings.loltv_request_budget * 0.7)
            )
            + 1,
        )

    def in_window(self, at: datetime) -> bool:
        return self.first <= at.astimezone(PARIS).date() <= self.last

    def checkpoint(self) -> None:
        self.policy.checkpoint(self.state)

    def seed_archived_events(self, events: list[LoltvEvent], known_ids: set[str]) -> None:
        discoveries: dict[str, dict[str, object]] = {}
        for event in events:
            evidence = event.payload.get("archivedDiscovery")
            if isinstance(evidence, dict) and isinstance(evidence.get("artifactSha256"), str):
                artifact_sha = cast(str, evidence["artifactSha256"])
                summary = discoveries.setdefault(
                    artifact_sha,
                    {**evidence, "candidateCount": 0, "queuedForFreshDetail": 0},
                )
                summary["candidateCount"] = int(cast(int, summary["candidateCount"])) + 1
            if event.source_id in known_ids or event.source_id in self.events:
                continue
            self.events[event.source_id] = {"event": encode_event(event), "due": 0}
            if isinstance(evidence, dict) and isinstance(evidence.get("artifactSha256"), str):
                summary = discoveries[cast(str, evidence["artifactSha256"])]
                summary["queuedForFreshDetail"] = (
                    int(cast(int, summary["queuedForFreshDetail"])) + 1
                )
        if discoveries:
            self.details["archivedDiscovery"] = list(discoveries.values())
            self.checkpoint()

    def publish(self, events: list[LoltvEvent]) -> None:
        if not events:
            return
        _, created = _publish_events(self.engine, events)
        self.details["published"] = int(cast(int, self.details["published"])) + len(events)
        self.details["created"] = int(cast(int, self.details["created"])) + created
        self.observed_ids.update(event.source_id for event in events)

    def fetch(self, client: httpx.Client, url: str) -> str:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "loltv.gg"
            or not parsed.path.startswith(("/matches", "/match/"))
        ):
            raise ValueError("LoLTV document URL outside the source allowlist")
        self.policy.before_request()
        started = time.monotonic()
        with client.stream("GET", url) as response:
            if response.status_code in {403, 429}:
                raise self.policy.block(
                    response.status_code,
                    "document",
                    response.headers.get("retry-after"),
                    request_url=url,
                    resource_type="document",
                )
            response.raise_for_status()
            if response.is_redirect:
                raise ValueError("Unexpected LoLTV redirect")
            if "text/html" not in response.headers.get("content-type", ""):
                raise ValueError("LoLTV did not return a public HTML document")
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > self.settings.catalog_max_page_bytes:
                    raise ValueError("LoLTV document exceeds the size limit")
            html = raw.decode("utf-8")
            if "Sorry, you have been blocked" in html or "<title>Just a moment" in html:
                raise self.policy.block(
                    response.status_code, "challenge", request_url=url, resource_type="document"
                )
            digest, path = store_bytes(
                self.settings.artifact_dir,
                "loltv-pages",
                gzip.compress(bytes(raw), mtime=0),
                "html.gz",
            )
            cast(list[object], self.details["pages"]).append(
                {
                    "url": url,
                    "status": response.status_code,
                    "bytes": len(raw),
                    "durationMs": round((time.monotonic() - started) * 1000),
                    "retrievedAt": datetime.now(UTC).isoformat(),
                    "cacheAge": response.headers.get("age"),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "artifactSha256": digest,
                    "path": path,
                }
            )
        self.policy.page_completed()
        return html

    def read_listing(self, client: httpx.Client, url: str) -> None:
        html = self.fetch(client, url)
        pages = self.details["pages"]
        evidence = pages[-1] if isinstance(pages, list) and pages else None
        age = evidence.get("cacheAge") if isinstance(evidence, dict) else None
        if isinstance(age, str) and age.isdecimal() and int(age) > MAX_LISTING_CACHE_AGE_SECONDS:
            root = str(self.pages[url]["root"])
            self.state.pop("resultsBoundary" if "/results" in root else "upcomingBoundary", None)
            raise ValueError(f"LoLTV listing cache is stale (Age: {age} seconds)")
        found, links, dates = listing(html, url)
        found = [event for event in found if self.in_window(event.starts_at)]
        self.publish(found)
        for event in found:
            previous = self.events.get(event.source_id, {})
            previous_event = previous.get("event")
            changed = isinstance(previous_event, dict) and any(
                previous_event.get(key) != getattr(event, key)
                for key in ("status", "home_score", "away_score")
            )
            # The separate completedGames cache survives listing refreshes.
            # Cached stats stay in their original snapshots, never a new observation.
            self.events[event.source_id] = {
                **previous,
                "event": encode_event(event),
                "due": 0 if changed else previous.get("due", 0),
            }
        root = str(self.pages[url]["root"])
        results = "/results" in root
        interval = (
            self.settings.loltv_results_interval_seconds
            if results
            else self.settings.loltv_listing_interval_seconds
            if url == root
            else self.settings.loltv_future_listing_interval_seconds
        )
        self.pages[url]["due"] = time.time() + interval
        # Follow only the next actually linked page. Out-of-window boundary dates
        # prove we can stop; unknown/empty markup does not prove full coverage.
        boundary = (
            min(dates).astimezone(PARIS).date()
            if results and dates
            else max(dates).astimezone(PARIS).date()
            if dates
            else None
        )
        beyond = boundary is not None and (
            boundary < self.first if results else boundary > self.last
        )
        current = int(url.rsplit("/", 1)[1]) if url.rsplit("/", 1)[1].isdigit() else 1
        next_url = next((link for link in links if link.endswith("/" + str(current + 1))), None)
        if next_url and not beyond:
            self.pages.setdefault(next_url, {"due": 0, "root": root})
        else:
            self.state["resultsBoundary" if results else "upcomingBoundary"] = {
                "at": datetime.now(UTC).isoformat(),
                "date": boundary.isoformat() if boundary else None,
                "page": url,
                "exhausted": not next_url,
                "windowEndReached": beyond,
            }
        # Retire pages past the newly observed boundary; retain the evidence files.
        if beyond or not next_url:
            for other in list(self.pages):
                tail = other.rsplit("/", 1)[1]
                if self.pages[other].get("root") == root and tail.isdigit() and int(tail) > current:
                    del self.pages[other]

    def read_detail(self, client: httpx.Client, key: str) -> None:
        item = self.events[key]
        event = decode_event(cast(dict[str, object], item["event"]))
        metadata = item.get("metadataEvent")
        metadata_at = item.get("metadataAt")
        cached = decode_event(metadata) if isinstance(metadata, dict) else None
        path = item.get("metadataHtmlPath")
        feed_states = item.get("feedStates")
        feed_states = feed_states if isinstance(feed_states, dict) else {}
        metadata_ttl = (
            self.settings.loltv_future_listing_interval_seconds
            if cached and has_active_feed(cached, feed_states)
            else self.settings.loltv_listing_interval_seconds
        )
        use_metadata = (
            self.settings.loltv_feed_enabled
            and event.status == "live"
            and cached is not None
            and isinstance(metadata_at, (int, float))
            and time.time() - metadata_at < metadata_ttl
            and isinstance(path, str)
            and (self.settings.artifact_dir / path).is_file()
            and all(
                getattr(cached, field) == getattr(event, field)
                for field in ("source_id", "status", "home_score", "away_score", "starts_at", "url")
            )
        )
        if use_metadata and cached is not None and isinstance(path, str):
            artifact = (self.settings.artifact_dir / path).resolve()
            if not artifact.is_relative_to(self.settings.artifact_dir.resolve()):
                raise ValueError("LoLTV cached document outside artifact storage")
            html = gzip.decompress(artifact.read_bytes()).decode("utf-8")
            event = replace(
                event,
                payload={
                    **event.payload,
                    "sourceGames": cached.payload.get("sourceGames", []),
                    "patch": cached.payload.get("patch"),
                    "metadataObservedAt": datetime.fromtimestamp(
                        float(cast(float, metadata_at)), UTC
                    ).isoformat(),
                    "rendered": {"maps": []},
                },
            )
            self.details["cachedMetadata"] = (
                int(cast(int, self.details.get("cachedMetadata", 0))) + 1
            )
        else:
            html = self.fetch(client, event.url)
            archived = event.payload.get("archivedDiscovery")
            if isinstance(archived, dict):
                pages = self.details["pages"]
                evidence = pages[-1] if isinstance(pages, list) and pages else None
                age = evidence.get("cacheAge") if isinstance(evidence, dict) else None
                retrieved = evidence.get("retrievedAt") if isinstance(evidence, dict) else None
                discovered = archived.get("retrievedAt")
                if (
                    isinstance(age, str)
                    and age.isdecimal()
                    and isinstance(retrieved, str)
                    and isinstance(discovered, str)
                    and datetime.fromisoformat(retrieved) - timedelta(seconds=int(age))
                    < datetime.fromisoformat(discovered)
                ):
                    raise ValueError("LoLTV detail cache predates the archived discovery")
            updated = detail(html, event, require_score=isinstance(archived, dict))
            if isinstance(archived, dict) and (
                updated.status != "finished"
                or updated.home_score is None
                or updated.away_score is None
            ):
                raise ValueError("LoLTV archived discovery lacks a validated finished detail")
            event = updated
            self.publish([event])
            item["metadataEvent"] = encode_event(event)
            item["metadataAt"] = time.time()
            pages = self.details["pages"]
            if isinstance(pages, list) and pages:
                item["metadataHtmlPath"] = pages[-1]["path"]
        acquired = self.acquired_games(item)
        # A feed can finish before the HTML publishes its winner. Keep its actual
        # final frame; poll metadata for the result/next card instead of rereading
        # the same completed feed. Once HTML settles it, read it once to publish a
        # fully settled map. Source time is never replaced by our cache access time.
        source_games = event.payload.get("sourceGames")
        waiting_results = {
            str(game["id"])
            for game in (source_games if isinstance(source_games, list) else [])
            if isinstance(game, dict)
            and game.get("state") in {"STARTED", "PAUSED"}
            and feed_states.get(str(game.get("id")), {}).get("state") == "COMPLETED"
        }
        # Commit HTML observations before optional rendered enrichment, including on refusal.
        item["event"] = encode_event(event)
        interval = (
            self.live_interval()
            if event.status == "live"
            else (
                self.settings.loltv_finished_refresh_seconds
                if complete(event, acquired)
                else self.settings.loltv_incomplete_refresh_seconds
            )
        )
        item["due"] = time.time() + interval
        self.remember_games(item, event)
        self.checkpoint()
        if self.settings.loltv_feed_enabled and not complete(event, acquired):
            from metiquo_worker.loltv_feed import FeedReader

            def publish_map(updated: LoltvEvent) -> None:
                self.publish([updated])
                item["event"] = encode_event(updated)
                states = updated.payload.get("feedStates")
                if isinstance(states, dict):
                    item["feedStates"] = {**feed_states, **states}
                self.remember_games(item, updated)
                self.checkpoint()

            event = FeedReader(self.settings, self.policy, self.state, self.details).enrich(
                client, html, event, acquired | waiting_results, publish_map
            )
            if complete(event, acquired):
                item["due"] = time.time() + self.settings.loltv_finished_refresh_seconds
        if (
            self.settings.loltv_render_live
            and not complete(event, acquired)
            and event.status in {"live", "finished"}
        ):
            from metiquo_worker.loltv_browser import render_details

            event = render_details(event, html, self.settings, self.policy, self.details, acquired)
            self.publish([event])
            item["event"] = encode_event(event)
            if event.status == "finished" and complete(event, acquired):
                item["due"] = time.time() + self.settings.loltv_finished_refresh_seconds
        self.remember_games(item, event)
        if event.status == "live":
            # Due from the final read, so the next wakeup cannot race this request.
            states = item.get("feedStates")
            active = has_active_feed(event, states if isinstance(states, dict) else {})
            item["due"] = time.time() + max(
                self.live_interval(),
                0 if active else self.settings.loltv_listing_interval_seconds,
            )

    def acquired_games(self, item: dict[str, object]) -> set[str]:
        entries = item.get("completedGames")
        return (
            {
                key
                for key, at in entries.items()
                if isinstance(at, (int, float))
                and time.time() - at < self.settings.loltv_finished_refresh_seconds
            }
            if isinstance(entries, dict)
            else set()
        )

    def remember_games(self, item: dict[str, object], event: LoltvEvent) -> None:
        rendered = event.payload.get("rendered")
        maps = rendered.get("maps") if isinstance(rendered, dict) else None
        previous = item.get("completedGames")
        entries = dict(previous) if isinstance(previous, dict) else {}
        if isinstance(maps, list):
            for game in maps:
                if isinstance(game, dict) and game.get("sourceGameId") and complete_map(game):
                    entries[str(game["sourceGameId"])] = time.time()
        item["completedGames"] = entries

    def run(self) -> None:
        deadline = time.monotonic() + self.settings.loltv_cycle_seconds
        self.state["cycleStartedAt"] = time.time()
        with httpx.Client(
            timeout=self.settings.loltv_timeout_seconds,
            follow_redirects=False,
            headers={"Accept": "text/html", "User-Agent": "Metiquo/0.1 (+public-esports-pages)"},
        ) as client:
            while time.monotonic() < deadline:
                self.policy.check()
                tasks: list[tuple[int, float, str, str]] = []
                for key, page in self.pages.items():
                    due = float(cast(float, page.get("due", 0)))
                    if due <= time.time() and key not in self.visited:
                        tasks.append((1, due, "listing", key))
                for key, item in self.events.items():
                    event = decode_event(cast(dict[str, object], item["event"]))
                    due = float(cast(float, item.get("due", 0)))
                    if (
                        event.status in {"live", "finished"}
                        and due <= time.time()
                        and (
                            event.status == "live"
                            and time.time() - self.live_attempts.get(key, 0) >= self.live_interval()
                            or event.url not in self.visited
                        )
                    ):
                        tasks.append((0 if event.status == "live" else 2, due, "detail", key))
                if not tasks:
                    break
                _, _, kind, key = min(tasks)
                url = (
                    key
                    if kind == "listing"
                    else decode_event(cast(dict[str, object], self.events[key]["event"])).url
                )
                self.visited.add(url)
                errors_before = len(cast(list[object], self.details["errors"]))
                try:
                    if kind == "listing":
                        self.read_listing(client, key)
                    else:
                        self.live_attempts[key] = time.time()
                        self.read_detail(client, key)
                except (LoltvBlocked, LoltvBudgetExhausted):
                    raise
                except (ValueError, httpx.HTTPError, RuntimeError) as error:
                    cast(list[object], self.details["errors"]).append(
                        {"url": url, "error": type(error).__name__, "message": str(error)[:250]}
                    )
                    target = self.pages[key] if kind == "listing" else self.events[key]
                    live = (
                        kind == "detail"
                        and decode_event(cast(dict[str, object], target["event"])).status == "live"
                    )
                    target["due"] = time.time() + (
                        max(60, self.live_interval())
                        if live
                        else self.settings.loltv_incomplete_refresh_seconds
                    )
                    logger.warning("LoLTV page failed: %s (%s)", url, type(error).__name__)
                if kind == "detail":
                    item = self.events[key]
                    if decode_event(cast(dict[str, object], item["event"])).status == "live":
                        failed = len(cast(list[object], self.details["errors"])) > errors_before
                        attempts = int(cast(int, item.get("liveErrors", 0))) + 1 if failed else 0
                        item["liveErrors"] = attempts
                        if failed:
                            item["due"] = time.time() + max(
                                self.live_interval(), min(120, 60 * attempts)
                            )
                self.checkpoint()
        self.details["knownEvents"] = len(self.events)
        self.details["pendingDetails"] = sum(
            decode_event(cast(dict[str, object], item["event"])).status in {"live", "finished"}
            and float(cast(float, item.get("due", 0))) <= time.time()
            for item in self.events.values()
        )
        self.details["coverage"] = {
            "from": str(self.first),
            "to": str(self.last),
            "results": self.state.get("resultsBoundary"),
            "upcoming": self.state.get("upcomingBoundary"),
        }


def sync_loltv(engine: Engine, settings: Settings) -> UUID:
    with source_lock(engine, LOCK_ID):
        policy = LoltvPolicy(engine, settings)
        policy.check()
        run_id = start_run(engine, SOURCE, "days:-7..+7")
        collector = Collector(engine, settings, policy, run_id)
        error: Exception | None = None
        try:
            archived, _ = discover_archived_events(collector.first, collector.last)
            if archived:
                with Session(engine) as session:
                    known_ids = set(
                        session.scalars(
                            select(MatchSourceLink.source_id).where(
                                MatchSourceLink.provider == SOURCE,
                                MatchSourceLink.source_id.in_(
                                    [event.source_id for event in archived]
                                ),
                            )
                        )
                    )
                collector.seed_archived_events(archived, known_ids)
            collector.run()
            if not collector.details["errors"]:
                policy.healthy()
        except LoltvBudgetExhausted:
            collector.details["deferred"] = "request-budget"
        except Exception as failure:
            error = failure
            if isinstance(failure, LoltvBlocked):
                collector.details.update(
                    {
                        "blocked": True,
                        "reason": failure.reason,
                        "httpStatus": failure.status,
                        "retryAt": failure.retry_at,
                    }
                )
        finally:
            collector.checkpoint()
            with Session(engine) as session, session.begin():
                run = session.get(IngestionRun, run_id)
                assert run is not None
                run.status = "failed" if error or collector.details["errors"] else "succeeded"
                run.finished_at = datetime.now(UTC)
                run.error = (
                    type(error).__name__
                    if error
                    else "Some source pages failed"
                    if collector.details["errors"]
                    else None
                )
                run.details = collector.details
        if error:
            raise error
        # Historical matching runs after source pages close; it cannot keep a live page polling.
        if collector.observed_ids:
            with Session(engine) as session:
                ids = set(
                    session.scalars(
                        select(MatchSourceLink.match_id).where(
                            MatchSourceLink.provider == SOURCE,
                            MatchSourceLink.source_id.in_(collector.observed_ids),
                        )
                    )
                )
            try:
                matched = sync_oracle_match_details(
                    engine, match_ids=ids, source_timezone=settings.oracle_date_timezone
                )
                with Session(engine) as session, session.begin():
                    run = session.get(IngestionRun, run_id)
                    assert run is not None
                    run.details = {**run.details, "oracle": matched}
            except Exception:
                logger.exception("Oracle reconciliation failed after LoLTV publication")
        return run_id
