"""Durable source pause/budget; auxiliary failures do not trigger a global pause."""

import time

from metiquo_core.config import Settings
from metiquo_core.models import CollectorState
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


class StakeDeferred(RuntimeError):
    def __init__(self, reason: str, retry_at: float):
        self.reason, self.retry_at = reason, retry_at
        super().__init__(reason)


class StakePolicy:
    def __init__(self, engine: Engine, settings: Settings):
        self.engine, self.settings = engine, settings
        self.pending_requests = 0
        with Session(engine) as db, db.begin():
            db.execute(
                insert(CollectorState).values(source="stake", data={}).on_conflict_do_nothing()
            )
        self.flush()

    def flush(self) -> None:
        now = time.time()
        with Session(self.engine) as db, db.begin():
            row = db.get(CollectorState, "stake", with_for_update=True)
            assert row is not None
            data = dict(row.data)
            start = data.get("budgetStart", now)
            count = data.get("requestCount", 0)
            self.window_start = float(start) if isinstance(start, (float, int)) else now
            self.request_count = int(count) if isinstance(count, (float, int)) else 0
            if now - self.window_start >= self.settings.stake_budget_window_seconds:
                self.window_start, self.request_count = now, 0
            self.request_count += self.pending_requests
            self.pending_requests = 0
            blocked = data.get("blockedUntil", 0)
            self.blocked_until = float(blocked) if isinstance(blocked, (float, int)) else 0
            row.data = {
                **data,
                "budgetStart": self.window_start,
                "requestCount": self.request_count,
            }

    def check(self) -> None:
        if self.blocked_until > time.time():
            raise StakeDeferred("cooldown", self.blocked_until)
        if self.request_count + self.pending_requests >= self.settings.stake_request_budget:
            raise StakeDeferred(
                "request_budget", self.window_start + self.settings.stake_budget_window_seconds
            )

    def block(self, reason: str, retry_after: float = 0) -> None:
        pause = max(self.settings.stake_block_cooldown_seconds, retry_after)
        until = time.time() + pause
        self.flush()
        with Session(self.engine) as db, db.begin():
            row = db.get(CollectorState, "stake", with_for_update=True)
            assert row is not None
            data = dict(row.data)
            if pause > 0:
                data.update(blockedUntil=until, blockedReason=reason)
            else:
                data.pop("blockedUntil", None)
                data.pop("blockedReason", None)
            row.data = data
        self.blocked_until = until
        raise StakeDeferred(reason, until)
