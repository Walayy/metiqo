"""Headed local Chrome: discovered navigation and guarded public DOM reads only."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from metiquo_core.config import Settings
from patchright.sync_api import Locator, Request, Response, sync_playwright
from pydantic import ValidationError

from metiquo_worker.loltv_policy import retry_after_seconds
from metiquo_worker.stake_audit import (
    DEFAULT_URL,
    launch_context,
    public_url,
    response_kind,
)
from metiquo_worker.stake_policy import StakePolicy
from metiquo_worker.stake_types import Capture, EventMetadata, Listing, validate_event_url

SCRIPT = Path(__file__).with_name("sources") / "stake_scrape.js"


class StakeEventStopped(RuntimeError):
    def __init__(self, metadata: EventMetadata, reason: str):
        self.metadata, self.reason = metadata, reason
        super().__init__(reason)


class StakeEventTransition(RuntimeError):
    def __init__(self, metadata: EventMetadata):
        self.metadata = metadata
        super().__init__("Event changed phase during market traversal")


class StakeCycleComplete(RuntimeError):
    """Bound reached: persist completed events and resume the oldest ones next cycle."""


class StakeBrowser:
    def __init__(self, settings: Settings, policy: StakePolicy):
        self.settings, self.policy = settings, policy
        self.source_script = SCRIPT.read_text(encoding="utf-8")
        self.requests = 0
        self.actions = 0
        self.refusals: list[dict[str, object]] = []
        self.pending_main_refusals: list[dict[str, object]] = []
        self.pending_retry_after = 0.0
        self.last_action = 0.0
        self.deadline = time.monotonic() + settings.stake_cycle_seconds
        self.discovered: set[str] = {DEFAULT_URL}
        self.on_discovery: Callable[[list[EventMetadata]], None] | None = None

    def __enter__(self) -> Self:
        self.policy.check()
        self.runtime = sync_playwright().start()
        try:
            self.context = launch_context(self.runtime, self.settings.stake_profile_dir)
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            for extra in self.context.pages[1:]:
                extra.close()
            self.page.on("request", self._request)
            self.page.on("response", self._response)
        except BaseException:
            self.runtime.stop()
            raise
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            self.context.close()
        finally:
            try:
                self.runtime.stop()
            finally:
                self.policy.flush()

    def _request(self, _: Request) -> None:
        self.requests += 1
        self.policy.pending_requests += 1

    def _response(self, response: Response) -> None:
        kind = response_kind(response.status, response.headers, response.url)
        main = response.request.is_navigation_request() and response.frame == self.page.main_frame
        if kind:
            refusal: dict[str, object] = {
                "at": datetime.now(UTC).isoformat(),
                "url": public_url(response.url),
                "status": response.status,
                "impact": "pending" if main else "auxiliary",
                "kind": kind,
            }
            if len(self.refusals) < 100:
                self.refusals.append(refusal)
            if main:
                self.pending_main_refusals.append(refusal)
                self.pending_retry_after = max(
                    self.pending_retry_after,
                    retry_after_seconds(response.headers.get("retry-after"), time.time()),
                )

    def _resolve_main_refusals(self) -> None:
        for refusal in self.pending_main_refusals:
            refusal["impact"] = "nonblocking"
        self.pending_main_refusals.clear()
        self.pending_retry_after = 0.0

    def _block_main_refusal(self, reason: str | None = None) -> None:
        for refusal in self.pending_main_refusals:
            refusal["impact"] = "blocking"
        kind = reason or str(self.pending_main_refusals[0]["kind"])
        self.policy.block(kind, self.pending_retry_after)

    def _block_visible_protection(self, reason: str) -> None:
        if self.pending_main_refusals:
            self._block_main_refusal(reason)
        else:
            self.policy.block(reason)

    def checkpoint(self) -> None:
        if self.settings.worker_stop_file and self.settings.worker_stop_file.exists():
            raise StakeCycleComplete("stop_requested")
        self.policy.check()
        if time.monotonic() >= self.deadline or self.actions >= self.settings.stake_max_actions:
            raise StakeCycleComplete("cycle_budget")

    def wait(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.checkpoint()
            self.page.wait_for_timeout(min(200, max(1, int((end - time.monotonic()) * 1000))))

    def before_action(self) -> None:
        self.policy.flush()
        self.checkpoint()
        self.wait(
            max(0, self.last_action + self.settings.stake_min_delay_seconds - time.monotonic())
        )
        self.actions += 1
        self.last_action = time.monotonic()

    def navigate(self, url: str) -> None:
        if url not in self.discovered:
            raise ValueError("Navigation URL was not discovered in the public DOM")
        self.before_action()
        self.pending_main_refusals.clear()
        self.pending_retry_after = 0.0
        self.page.goto(
            url, wait_until="domcontentloaded", timeout=self.settings.stake_timeout_seconds * 1000
        )
        self.wait(2)
        if self.page.title().casefold() in {"un instant…", "just a moment...", "just a moment…"}:
            self._block_visible_protection("challenge")
        if self.page.get_by_text("You are being rate limited", exact=False).count():
            self._block_visible_protection("rate_limited")

    def _listing(self, game: str, mode: str = "listing") -> Listing:
        end = time.monotonic() + self.settings.stake_timeout_seconds
        previous: object = None
        stable = 0
        while True:
            self.checkpoint()
            data = Listing.model_validate(
                self.page.evaluate(self.source_script, {"mode": mode, "game": game})
            )
            self.discovered.update(data.links)
            shape = ([e.source_id for e in data.fixtures], data.more, data.ready)
            stable = stable + 1 if previous == shape else 0
            previous = shape
            if data.ready and stable >= 2:
                if mode != "hub":
                    self._resolve_main_refusals()
                return data
            if time.monotonic() >= end:
                if self.pending_main_refusals:
                    self._block_main_refusal()
                raise ValueError("Public sports listing did not become ready")
            self.wait(0.5)

    def fixtures(self, game: str) -> list[EventMetadata]:
        self.navigate(DEFAULT_URL)
        hub = self._listing(game, "hub")
        urls = {u for u in hub.links if u.endswith(f"/sports/esports/{game}")}
        if len(urls) != 1:
            if self.pending_main_refusals:
                self._block_main_refusal()
            raise ValueError("Configured esport is not exposed by the public hub")
        self._resolve_main_refusals()
        self.navigate(urls.pop())
        listing = self._listing(game)
        fixtures: dict[str, EventMetadata] = {}
        for _ in range(100):
            if self.on_discovery is not None:
                self.on_discovery(listing.fixtures)
            fixtures.update({e.source_id: e for e in listing.fixtures})
            if not listing.more:
                return list(fixtures.values())
            previous = set(fixtures)
            self.click(
                self.page.locator("#main-content").get_by_role(
                    "button", name=listing.more, exact=True
                )
            )
            listing = self._listing(game)
            if not ({e.source_id for e in listing.fixtures} - previous):
                self.wait(2)
                listing = self._listing(game)
                if not ({e.source_id for e in listing.fixtures} - previous):
                    raise ValueError("Listing pagination did not progress")
        raise ValueError("Listing pagination bound reached")

    def click(self, locator: Locator, *, game: str | None = None) -> None:
        self.before_action()
        if game is not None:
            metadata = self.read(game, metadata_only=True).metadata
            if not metadata.eligible(datetime.now(UTC), self.settings.stake_start_guard_seconds):
                raise ValueError("Event state changed before market navigation")
        if locator.count() != 1 or locator.evaluate(
            "e => !!e.closest('[data-testid=fixture-outcome]')"
        ):
            raise ValueError("Only a unique non-betting navigation control may be clicked")
        locator.click(timeout=10000)
        self.wait(0.5)

    def read(self, game: str, *, metadata_only: bool = False) -> Capture:
        self.checkpoint()
        data = self.page.evaluate(
            self.source_script,
            {
                "mode": "metadata" if metadata_only else "capture",
                "game": game,
                "guardSeconds": self.settings.stake_start_guard_seconds,
            },
        )
        capture = Capture.model_validate(data)
        metadata = capture.metadata
        if metadata.status == "closed":
            self._resolve_main_refusals()
            raise StakeEventStopped(metadata, metadata.status)
        return capture

    def stable_capture(self, game: str) -> Capture:
        end = time.monotonic() + self.settings.stake_timeout_seconds
        previous: object = None
        stable = 0
        while time.monotonic() < end:
            try:
                capture = self.read(game)
            except ValidationError:
                if not self.pending_main_refusals:
                    raise
                self.wait(1)
                continue
            shape = (
                [(t.id, t.disabled) for t in capture.tabs],
                [(m.label, m.expanded, len(m.selections)) for m in capture.markets],
            )
            stable = stable + 1 if previous == shape else 0
            if (
                stable >= 2
                and capture.metadata.eligible(
                    datetime.now(UTC), self.settings.stake_start_guard_seconds
                )
                and capture.markets
            ):
                self._resolve_main_refusals()
                return capture
            previous = shape
            self.wait(1)
        if self.pending_main_refusals:
            self._block_main_refusal()
        raise ValueError("No stable markets for an identified scheduled or live event")

    def expanded_capture(self, game: str) -> Capture:
        capture = self.stable_capture(game)
        for index in range(len(capture.markets)):
            self.read(game, metadata_only=True)
            group = self.page.locator(".groups .secondary-accordion").nth(index)
            if not capture.markets[index].expanded:
                self.click(group.locator(":scope > .header"), game=game)
                capture = self.stable_capture(game)
            for label in ("Tout", "Charger Plus", "Afficher plus"):
                if label in capture.markets[index].controls:
                    self.read(game, metadata_only=True)
                    self.click(group.get_by_role("button", name=label, exact=True), game=game)
                    capture = self.stable_capture(game)
        return capture

    def event(self, fixture: EventMetadata) -> tuple[list[Capture], EventMetadata]:
        validate_event_url(fixture.url, fixture.game)
        self.navigate(fixture.url)
        capture = self.expanded_capture(fixture.game)
        captures = [capture]
        visited = {capture.tab}
        pending = [t.id for t in capture.tabs if not t.disabled and t.id not in visited]
        while pending:
            target = pending.pop(0)
            if target in visited:
                continue
            self.read(fixture.game, metadata_only=True)
            self.click(self.page.locator(".groups").get_by_test_id(target), game=fixture.game)
            capture = self.expanded_capture(fixture.game)
            if capture.tab != target:
                raise ValueError("Market tab did not become active")
            captures.append(capture)
            visited.add(target)
            pending.extend(
                t.id
                for t in capture.tabs
                if not t.disabled and t.id not in visited and t.id not in pending
            )
        closing = self.read(fixture.game, metadata_only=True).metadata
        if any(c.metadata.status != closing.status for c in captures):
            raise StakeEventTransition(closing)
        return captures, closing
