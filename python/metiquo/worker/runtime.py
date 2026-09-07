"""Cycle de vie du worker sans scheduler métier."""

import logging
from threading import Event, Thread
from typing import Protocol

from metiquo.worker.runner import PostgresJobRunner


class Scheduler(Protocol):
    def tick(self) -> None: ...


class WorkerRuntime:
    """Attendre des jobs futurs tout en garantissant un arrêt coopératif."""

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        runner: PostgresJobRunner | None = None,
        poll_seconds: float = 1,
        scheduler: Scheduler | None = None,
        schedule_seconds: float = 15,
    ) -> None:
        if poll_seconds <= 0 or schedule_seconds <= 0:
            raise ValueError("La période de polling doit être positive")
        self._logger = logger or logging.getLogger("metiquo.worker")
        self._shutdown = Event()
        self._started = Event()
        self._runner, self._poll_seconds = runner, poll_seconds
        self._scheduler, self._schedule_seconds = scheduler, schedule_seconds

    def run(self) -> int:
        """Signaler le démarrage, attendre, puis confirmer l'arrêt propre."""

        self._logger.info("worker.started")
        self._started.set()
        schedule_thread = Thread(target=self._schedule, name="job-scheduler", daemon=True)
        if self._scheduler is not None:
            schedule_thread.start()
        try:
            if self._runner is None:
                self._shutdown.wait()
            else:
                while not self._shutdown.is_set():
                    try:
                        if self._runner.run_once():
                            continue
                    except Exception:
                        self._logger.error("worker.queue_unavailable")
                    self._shutdown.wait(self._poll_seconds)
        finally:
            self._shutdown.set()
            if self._scheduler is not None:
                schedule_thread.join(timeout=5)
        self._logger.info("worker.stopped")
        return 0

    def _schedule(self) -> None:
        while not self._shutdown.is_set():
            try:
                assert self._scheduler is not None
                self._scheduler.tick()
            except Exception:
                self._logger.error("worker.scheduler_failed")
            self._shutdown.wait(self._schedule_seconds)

    def request_stop(self) -> None:
        self._shutdown.set()
        if self._runner is not None:
            self._runner.request_stop()

    def wait_until_started(self, timeout_seconds: float) -> bool:
        return self._started.wait(timeout_seconds)
