"""Cycle de vie du worker sans scheduler métier."""

import logging
from threading import Event

from metiquo.worker.runner import PostgresJobRunner


class WorkerRuntime:
    """Attendre des jobs futurs tout en garantissant un arrêt coopératif."""

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        runner: PostgresJobRunner | None = None,
        poll_seconds: float = 1,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("La période de polling doit être positive")
        self._logger = logger or logging.getLogger("metiquo.worker")
        self._shutdown = Event()
        self._started = Event()
        self._runner, self._poll_seconds = runner, poll_seconds

    def run(self) -> int:
        """Signaler le démarrage, attendre, puis confirmer l'arrêt propre."""

        self._logger.info("worker.started")
        self._started.set()
        if self._runner is None:
            self._shutdown.wait()
        else:
            while not self._shutdown.is_set():
                if not self._runner.run_once():
                    self._shutdown.wait(self._poll_seconds)
        self._logger.info("worker.stopped")
        return 0

    def request_stop(self) -> None:
        self._shutdown.set()
        if self._runner is not None:
            self._runner.request_stop()

    def wait_until_started(self, timeout_seconds: float) -> bool:
        return self._started.wait(timeout_seconds)
