"""A shutdown observed between HTTP chunks leaves no partial file behind."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from metiquo.foundation.cancellation import cancellation_scope
from metiquo.ingestion.google_drive_public import GoogleDrivePublicHttpTransport, PublicHttpStream
from metiquo.worker.contracts import CancellationToken, JobCancelled
from tests.ingestion.test_google_drive_public import SOURCE, FakePublicClient, _policy


def test_cancelled_stream_is_closed_and_partial_file_removed(tmp_path: Path) -> None:
    token = CancellationToken()
    closed = []

    def chunks() -> Iterator[bytes]:
        try:
            yield b"gameid,league\n"
            token.cancel()
            yield b"1,LCK\n"
        finally:
            closed.append(True)

    transport = GoogleDrivePublicHttpTransport(
        policy=_policy(),
        client=FakePublicClient([PublicHttpStream(200, {"content-type": "text/csv"}, chunks())]),
    )
    destination = tmp_path / "download.part"
    with cancellation_scope(token.raise_if_cancelled), pytest.raises(JobCancelled):
        transport.download(SOURCE, destination)
    assert closed == [True]
    assert not destination.exists()
