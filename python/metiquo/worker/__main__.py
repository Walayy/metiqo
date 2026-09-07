"""Point d'entrée du processus worker."""

import os
import signal
from types import FrameType
from uuid import uuid4

from sqlalchemy import create_engine

from metiquo.config import load_settings
from metiquo.contracts.enums import DataMode
from metiquo.foundation.observability import configure_json_logging
from metiquo.worker.handlers import default_handlers
from metiquo.worker.queue import PostgresJobQueue
from metiquo.worker.runner import PostgresJobRunner
from metiquo.worker.runtime import WorkerRuntime


def main() -> int:
    """Valider la configuration et exécuter le cycle de vie sans job."""

    settings = load_settings()
    configure_json_logging()
    engine = (
        create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
        if settings.app_data_mode is DataMode.REAL
        else None
    )
    runner = (
        PostgresJobRunner(
            PostgresJobQueue(engine),
            default_handlers(engine, settings),
            owner=f"worker-{os.getpid()}-{uuid4().hex[:8]}",
        )
        if engine is not None
        else None
    )
    runtime = WorkerRuntime(runner=runner)

    def request_stop(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        runtime.request_stop()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    try:
        return runtime.run()
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
