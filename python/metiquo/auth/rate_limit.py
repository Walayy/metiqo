"""Budgets globaux du compte unique, sans confiance dans les IP de proxy."""

from datetime import UTC, datetime
from threading import Lock
from typing import Literal

from sqlalchemy import Engine, text

from metiquo.foundation.time import Clock

type SensitiveAction = Literal["login", "mutation"]


class HttpRateLimiter:
    def __init__(self, engine: Engine | None, clock: Clock) -> None:
        self.engine, self.clock = engine, clock
        self._local: dict[str, tuple[int, int]] = {}
        self._lock = Lock()

    def check(self, action: SensitiveAction) -> int:
        """Retourner Retry-After, zéro si les budgets autorisent cette tentative."""
        limits = (
            (("login-minute", 60, 5), ("login-quarter", 900, 20))
            if action == "login"
            else (("mutation-minute", 60, 60),)
        )
        now = int(self.clock.now().value.timestamp())
        retry_after = 0
        if self.engine is None:
            with self._lock:
                for bucket, seconds, limit in limits:
                    start = now // seconds * seconds
                    old_start, used = self._local.get(bucket, (start, 0))
                    used = 1 if start > old_start else min(used + 1, limit + 1)
                    start = max(start, old_start)
                    self._local[bucket] = start, used
                    if used > limit:
                        retry_after = max(retry_after, start + seconds - now)
            return retry_after
        with self.engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            for bucket, seconds, limit in limits:
                window_start = datetime.fromtimestamp(now // seconds * seconds, UTC)
                stored = connection.execute(
                    text("""
                        INSERT INTO ops.http_rate_limits (bucket, window_start, attempts)
                        VALUES (:bucket, :start, 1)
                        ON CONFLICT (bucket) DO UPDATE SET
                          attempts = CASE WHEN EXCLUDED.window_start > http_rate_limits.window_start
                            THEN 1 ELSE LEAST(http_rate_limits.attempts + 1, :maximum) END,
                          window_start = GREATEST(http_rate_limits.window_start,
                                                  EXCLUDED.window_start)
                        RETURNING window_start, attempts
                    """),
                    {"bucket": bucket, "start": window_start, "maximum": limit + 1},
                ).one()
                if stored.attempts > limit:
                    retry_after = max(
                        retry_after, int(stored.window_start.timestamp()) + seconds - now
                    )
        return retry_after
