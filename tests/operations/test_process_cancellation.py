"""A slow child command must not delay cooperative worker shutdown."""

import sys
import time
from threading import Timer

import pytest

from metiquo.foundation.cancellation import cancellation_scope
from metiquo.operations.backup_tools import run_process
from metiquo.worker.contracts import CancellationToken, JobCancelled


def test_child_process_is_reaped_on_cancellation() -> None:
    token = CancellationToken()
    timer = Timer(0.5, token.cancel)
    started = time.monotonic()
    timer.start()
    try:
        with cancellation_scope(token.raise_if_cancelled), pytest.raises(JobCancelled):
            run_process([sys.executable, "-c", "import time; time.sleep(30)"], timeout=40)
        assert time.monotonic() - started < 5
    finally:
        timer.cancel()
        timer.join()
