"""Compteurs HTTP bornés au processus, sans labels issus des données utilisateur."""

from threading import Lock

from metiquo.contracts.system import ApiProcessMetrics


class ApiMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._count, self._failures, self._milliseconds = 0, 0, 0.0

    def observe(self, status: int, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("Durée HTTP négative")
        with self._lock:
            self._count += 1
            self._failures += int(status >= 500)
            self._milliseconds += seconds * 1000

    def snapshot(self) -> ApiProcessMetrics:
        with self._lock:
            return ApiProcessMetrics(
                request_count=self._count,
                failure_count=self._failures,
                mean_latency_ms=self._milliseconds / self._count if self._count else None,
            )
