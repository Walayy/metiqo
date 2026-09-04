"""Processus d'attente temporaire utilisé avant le ticket worker FND-008."""

import signal
import threading

from metiquo.config import load_settings


def main() -> None:
    """Valider la configuration et attendre un signal d'arrêt."""

    load_settings()
    stopped = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        stopped.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    stopped.wait()


if __name__ == "__main__":
    main()
