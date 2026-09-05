"""Transport public Drive borné et sans contournement des pages HTML."""

from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import pytest

from metiquo.config import Settings
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.google_drive_public import (
    GoogleDrivePublicHttpTransport,
    PublicHttpStream,
)
from metiquo.ingestion.source_errors import UnexpectedHtmlResponse
from metiquo.ingestion.transport import SourceRef, TransportPolicy
from tests.ingestion.transport_contract import assert_source_transport_contract

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "oracles_elixir"
NOW = datetime(2026, 9, 5, 17, tzinfo=UTC)
CLOCK = FixedClock(UtcInstant(NOW))
SOURCE = SourceRef(
    provider="oracles_elixir",
    year=2026,
    source_id="public-drive-file",
    locator="https://drive.google.com/file/d/public-drive-file/view",
    source_name="2026 match data",
    mutable=True,
)


class FakePublicClient:
    def __init__(self, responses: list[PublicHttpStream]) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[str, float, float, int]] = []

    def get(
        self,
        url: str,
        *,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        max_redirects: int,
    ) -> PublicHttpStream:
        self.calls.append((url, connect_timeout_seconds, read_timeout_seconds, max_redirects))
        return self.responses.popleft()


def _policy(max_bytes: int = 1024) -> TransportPolicy:
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "real",
            "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "odds_provider": "disabled",
            "oe_max_download_bytes": max_bytes,
        }
    )
    return TransportPolicy.from_settings(settings)


def _success_client(payload: bytes) -> FakePublicClient:
    headers = {
        "content-type": "application/gzip",
        "content-length": str(len(payload)),
        "etag": "public-etag",
    }
    return FakePublicClient(
        [
            PublicHttpStream(200, headers, (payload[:8], payload[8:])),
            PublicHttpStream(200, headers, (payload[:3], payload[3:11], payload[11:])),
        ]
    )


def test_public_http_satisfies_shared_transport_contract(tmp_path: Path) -> None:
    payload = b"gameid,league\n1,LCK\n"
    policy = _policy()

    assert_source_transport_contract(
        factory=lambda content: GoogleDrivePublicHttpTransport(
            policy=policy,
            client=_success_client(content),
            clock=CLOCK,
        ),
        policy=policy,
        source=SOURCE,
        payload=payload,
        destination=tmp_path / "source.part",
    )


@pytest.mark.parametrize(
    ("fixture", "message"),
    [
        ("quota.html", "quota"),
        ("consent.html", "consentement"),
        ("login.html", "connexion"),
    ],
)
def test_html_200_pages_are_refused_before_writing(
    tmp_path: Path, fixture: str, message: str
) -> None:
    body = (FIXTURES / fixture).read_bytes()
    client = FakePublicClient([PublicHttpStream(200, {"content-type": "text/html"}, (body,))])
    transport = GoogleDrivePublicHttpTransport(policy=_policy(), client=client, clock=CLOCK)
    destination = tmp_path / "source.part"

    with pytest.raises(UnexpectedHtmlResponse, match=message):
        transport.download(SOURCE, destination)

    assert destination.exists() is False


def test_html_magic_is_rejected_even_with_binary_content_type(tmp_path: Path) -> None:
    body = (FIXTURES / "quota.html").read_bytes()
    client = FakePublicClient(
        [PublicHttpStream(200, {"content-type": "application/octet-stream"}, (body,))]
    )
    destination = tmp_path / "source.part"

    with pytest.raises(UnexpectedHtmlResponse):
        GoogleDrivePublicHttpTransport(policy=_policy(), client=client, clock=CLOCK).download(
            SOURCE, destination
        )

    assert destination.exists() is False


def test_quota_html_is_detected_even_with_http_403(tmp_path: Path) -> None:
    body = (FIXTURES / "quota.html").read_bytes()
    client = FakePublicClient([PublicHttpStream(403, {"content-type": "text/html"}, (body,))])
    destination = tmp_path / "source.part"

    with pytest.raises(UnexpectedHtmlResponse, match="quota"):
        GoogleDrivePublicHttpTransport(policy=_policy(), client=client, clock=CLOCK).download(
            SOURCE, destination
        )

    assert destination.exists() is False


def test_public_url_has_no_quota_bypass_parameter(tmp_path: Path) -> None:
    payload = b"payload"
    client = _success_client(payload)
    transport = GoogleDrivePublicHttpTransport(policy=_policy(), client=client, clock=CLOCK)

    transport.probe(SOURCE)
    transport.download(SOURCE, tmp_path / "source.part")

    assert len(client.calls) == 2
    for url, connect_timeout, read_timeout, max_redirects in client.calls:
        assert "drive.google.com/uc?" in url
        assert "export=download" in url
        assert "id=public-drive-file" in url
        assert "confirm=" not in url
        assert (connect_timeout, read_timeout, max_redirects) == (10, 60, 3)


def test_preexisting_destination_is_never_removed(tmp_path: Path) -> None:
    destination = tmp_path / "source.part"
    destination.write_bytes(b"keep-me")
    transport = GoogleDrivePublicHttpTransport(
        policy=_policy(),
        client=FakePublicClient(
            [PublicHttpStream(200, {"content-type": "application/gzip"}, (b"new",))]
        ),
        clock=CLOCK,
    )

    with pytest.raises(FileExistsError):
        transport.download(SOURCE, destination)

    assert destination.read_bytes() == b"keep-me"
