"""Cycle de vie du worker sans scheduler métier."""

import logging
from threading import Event


class WorkerRuntime:
    """Attendre des jobs futurs tout en garantissant un arrêt coopératif."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("metiquo.worker")
        self._shutdown = Event()
        self._started = Event()

    def run(self) -> int:
        """Signaler le démarrage, attendre, puis confirmer l'arrêt propre."""

        self._logger.info("worker.started")
        self._started.set()
        self._shutdown.wait()
        self._logger.info("worker.stopped")
        return 0

    def request_stop(self) -> None:
        self._shutdown.set()

    def wait_until_started(self, timeout_seconds: float) -> bool:
        return self._started.wait(timeout_seconds)
