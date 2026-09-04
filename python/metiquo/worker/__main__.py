"""Point d'entrée du processus worker."""

import signal
from types import FrameType

from metiquo.config import load_settings
from metiquo.foundation.observability import configure_json_logging
from metiquo.worker.runtime import WorkerRuntime


def main() -> int:
    """Valider la configuration et exécuter le cycle de vie sans job."""

    load_settings()
    configure_json_logging()
    runtime = WorkerRuntime()

    def request_stop(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        runtime.request_stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    return runtime.run()


if __name__ == "__main__":
    raise SystemExit(main())
