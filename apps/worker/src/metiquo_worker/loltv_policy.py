"""One PostgreSQL-backed request budget for every Loltv collector process."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from random import SystemRandom
from urllib.parse import urlsplit

from metiquo_core.config import Settings
from metiquo_core.models import CollectorState
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

SOURCE = "loltv"
RANDOM = SystemRandom()


class LoltvBudgetExhausted(RuntimeError):
    """The durable queue resumes when the shared fixed-window budget is available."""


class LoltvBlocked(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        reason: str = "unknown",
        retry_at: float = 0.0,
    ):
        super().__init__(message)
        self.status = status
        self.reason = reason
        self.retry_at = retry_at


def retry_after_seconds(value: str | None, now: float) -> float:
    if not value:
        return 0.0
    try:
        if value.strip().isdigit():
            return float(value.strip())
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return 0.0
        return max(0.0, parsed.timestamp() - now)
    except (ValueError, TypeError, OverflowError):
        return 0.0


class LoltvPolicy:
    def __init__(self, engine: Engine, settings: Settings):
        self.engine = engine
        self.settings = settings
        with Session(engine) as db, db.begin():
            db.execute(
                insert(CollectorState).values(source=SOURCE, data={}).on_conflict_do_nothing()
            )

    def read(self) -> dict[str, object]:
        with Session(self.engine) as db:
            row = db.get(CollectorState, SOURCE)
            assert row is not None
            return dict(row.data)

    def checkpoint(self, value: dict[str, object]) -> None:
        with Session(self.engine) as db, db.begin():
            row = db.get(CollectorState, SOURCE, with_for_update=True)
            assert row is not None
            row.data = {**row.data, "checkpoint": value}

    def page_completed(self, value: dict[str, object] | None = None) -> None:
        """Start the next pause after the whole read; only checkpoint durable data."""
        with Session(self.engine) as db, db.begin():
            row = db.get(CollectorState, SOURCE, with_for_update=True)
            assert row is not None
            row.data = {
                **row.data,
                "lastPageCompletedAt": time.time(),
                **({"checkpoint": value} if value is not None else {}),
            }

    def check(self) -> None:
        data, now = self.read(), time.time()
        self._check(data, now)
        start, count = data.get("browserBudgetStart"), data.get("browserBudgetCount")
        if (
            isinstance(start, (int, float))
            and isinstance(count, int)
            and now - start < self.settings.loltv_budget_window_seconds
            and count >= self.settings.loltv_browser_request_budget
        ):
            raise LoltvBudgetExhausted("LoLTV natural browser request budget exhausted")

    @staticmethod
    def _check(data: dict[str, object], now: float) -> None:
        until = data.get("blockedUntil", 0)
        if isinstance(until, (int, float)) and until > now:
            raise LoltvBlocked(
                "Loltv cooldown active until " + datetime.fromtimestamp(until, UTC).isoformat(),
                reason="cooldown",
                retry_at=until,
            )

    def before_request(self, wait: Callable[[float], None] | None = None) -> None:
        delay = RANDOM.uniform(
            min(self.settings.loltv_min_delay_seconds, self.settings.loltv_max_delay_seconds),
            max(self.settings.loltv_min_delay_seconds, self.settings.loltv_max_delay_seconds),
        )
        while True:
            with Session(self.engine) as db, db.begin():
                row = db.get(CollectorState, SOURCE, with_for_update=True)
                assert row is not None
                now = time.time()
                self._check(row.data, now)
                start = row.data.get("budgetStart", 0)
                count = row.data.get("budgetCount", 0)
                if (
                    not isinstance(start, (int, float))
                    or now - start >= self.settings.loltv_budget_window_seconds
                ):
                    start, count = now, 0
                count = count if isinstance(count, int) else 0
                if count >= self.settings.loltv_request_budget:
                    raise LoltvBudgetExhausted("LoLTV shared request budget exhausted")
                previous = max(
                    (
                        float(value)
                        for key in ("lastRequestAt", "lastPageCompletedAt")
                        if isinstance(value := row.data.get(key), (int, float))
                    ),
                    default=0.0,
                )
                remaining = previous + delay - now
                if remaining <= 0:
                    row.data = {
                        **row.data,
                        "lastRequestAt": now,
                        "budgetStart": start,
                        "budgetCount": count + 1,
                    }
                    return
            (wait or time.sleep)(min(remaining, 1) if wait else min(remaining, 60))

    def record_traffic(self, summary: dict[str, object]) -> None:
        with Session(self.engine) as db, db.begin():
            row = db.get(CollectorState, SOURCE, with_for_update=True)
            assert row is not None
            row.data = {**row.data, "network": summary}

    def browser_request(self) -> None:
        """Count natural requests without routing (which would disable HTTP cache).

        This observation happens as a request starts, so the final in-flight
        request cannot be undone. The caller closes the context at the limit.
        """
        with Session(self.engine) as db, db.begin():
            row = db.get(CollectorState, SOURCE, with_for_update=True)
            assert row is not None
            now = time.time()
            self._check(row.data, now)
            start = row.data.get("browserBudgetStart", 0)
            count = row.data.get("browserBudgetCount", 0)
            if not isinstance(start, (int, float)) or (
                now - start >= self.settings.loltv_budget_window_seconds
            ):
                start, count = now, 0
            count = (count if isinstance(count, int) else 0) + 1
            row.data = {**row.data, "browserBudgetStart": start, "browserBudgetCount": count}
        if count >= self.settings.loltv_browser_request_budget:
            raise LoltvBudgetExhausted("LoLTV natural browser request budget exhausted")

    def block(
        self,
        status: int | None,
        reason: str,
        retry_after: str | None = None,
        *,
        request_url: str | None = None,
        resource_type: str | None = None,
    ) -> LoltvBlocked:
        parsed = urlsplit(request_url) if request_url else None
        # Keep the refused resource, never its query tokens or fragment.
        resource_url = f"{parsed.scheme}://{parsed.hostname}{parsed.path}" if parsed else None
        with Session(self.engine) as db, db.begin():
            row = db.get(CollectorState, SOURCE, with_for_update=True)
            assert row is not None
            now = time.time()
            previous_until = row.data.get("blockedUntil", 0)
            count = row.data.get("consecutiveBlocks", 0)
            streak = int(count) if isinstance(count, int) else 0
            # Concurrent failing subresources belong to the same refusal.
            if not isinstance(previous_until, (int, float)) or previous_until <= now:
                streak += 1
            duration = max(
                self.settings.loltv_block_cooldown_seconds,
                min(
                    21600,
                    self.settings.loltv_block_cooldown_seconds * 2 ** min(max(streak - 1, 0), 6),
                ),
            )
            until = max(
                now + duration,
                now + retry_after_seconds(retry_after, now),
                float(previous_until) if isinstance(previous_until, (int, float)) else 0,
            )
            row.data = {
                **row.data,
                "blockedUntil": until,
                "consecutiveBlocks": streak,
                "lastBlockAt": now,
                "lastBlockStatus": status,
                "lastBlockReason": reason,
                "lastBlockUrl": resource_url,
                "lastBlockResourceType": resource_type,
            }
        return LoltvBlocked(
            f"Loltv blocked ({reason}, http_status={status or 'unknown'})",
            status=status,
            reason=reason,
            retry_at=until,
        )

    def healthy(self) -> None:
        with Session(self.engine) as db, db.begin():
            row = db.get(CollectorState, SOURCE, with_for_update=True)
            assert row is not None
            self._check(row.data, time.time())
            row.data = {**row.data, "consecutiveBlocks": 0, "blockedUntil": 0}
