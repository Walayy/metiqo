"""One PostgreSQL-backed request budget for every SofaScore collector process."""

import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from random import SystemRandom
from urllib.parse import urlsplit

from metiquo_core.config import Settings
from metiquo_core.models import CollectorState
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

SOURCE = "sofascore"
RANDOM = SystemRandom()


class SofaScoreBlocked(RuntimeError):
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


class SofaScorePolicy:
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
        self._check(self.read(), time.time())

    @staticmethod
    def _check(data: dict[str, object], now: float) -> None:
        until = data.get("blockedUntil", 0)
        if isinstance(until, (int, float)) and until > now:
            raise SofaScoreBlocked(
                "SofaScore cooldown active until " + datetime.fromtimestamp(until, UTC).isoformat(),
                reason="cooldown",
                retry_at=until,
            )

    def before_request(self) -> None:
        delay = RANDOM.uniform(
            min(
                self.settings.sofascore_min_delay_seconds, self.settings.sofascore_max_delay_seconds
            ),
            max(
                self.settings.sofascore_min_delay_seconds, self.settings.sofascore_max_delay_seconds
            ),
        )
        while True:
            with Session(self.engine) as db, db.begin():
                row = db.get(CollectorState, SOURCE, with_for_update=True)
                assert row is not None
                now = time.time()
                self._check(row.data, now)
                previous = max(
                    (
                        float(value)
                        for key in ("lastRequestAt", "lastPageCompletedAt")
                        if isinstance(value := row.data.get(key), (int, float))
                    ),
                    default=0.0,
                )
                wait = previous + delay - now
                if wait <= 0:
                    row.data = {**row.data, "lastRequestAt": now}
                    return
            time.sleep(min(wait, 60))

    def block(
        self,
        status: int | None,
        reason: str,
        retry_after: str | None = None,
        *,
        request_url: str | None = None,
        resource_type: str | None = None,
    ) -> SofaScoreBlocked:
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
                self.settings.sofascore_block_cooldown_seconds,
                min(
                    21600,
                    self.settings.sofascore_block_cooldown_seconds
                    * 2 ** min(max(streak - 1, 0), 6),
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
        return SofaScoreBlocked(
            f"SofaScore blocked ({reason}, http_status={status or 'unknown'})",
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
