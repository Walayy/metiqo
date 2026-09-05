"""Transport Google Drive API v3 sans fuite de credential."""

import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from metiquo.config import Settings
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.google_drive_api import (
    DriveHttpStream,
    GoogleDriveApiTransport,
)
from metiquo.ingestion.source_errors import (
    SourceNotFound,
    SourcePermissionDenied,
    SourceQuotaExceeded,
    SourceRateLimited,
    SourceTooLarge,
    SourceTransportError,
)
from metiquo.ingestion.transport import SourceRef, TransportPolicy
from tests.ingestion.transport_contract import assert_source_transport_contract

NOW = datetime(2026, 9, 5, 16, tzinfo=UTC)
CLOCK = FixedClock(UtcInstant(NOW))
SOURCE = SourceRef(
    provider="oracles_elixir",
    year=2026,
    source_id="drive-file-2026",
    locator="https://drive.google.com/file/d/drive-file-2026/view",
    source_name="2026 match data",
    mutable=True,
)


class FakeDriveClient:
    def __init__(self, responses: list[DriveHttpStream]) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[str, str, float, float, int]] = []

    def get(
        self,
        url: str,
        *,
        bearer: str,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        max_redirects: int,
    ) -> DriveHttpStream:
        self.calls.append(
            (url, bearer, connect_timeout_seconds, read_timeout_seconds, max_redirects)
        )
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


def _metadata_response(size: int) -> DriveHttpStream:
    return DriveHttpStream(
        200,
        {"etag": "metadata-etag"},
        (
            json.dumps(
                {
                    "id": SOURCE.source_id,
                    "name": SOURCE.source_name,
                    "mimeType": "application/gzip",
                    "size": str(size),
                    "modifiedTime": "2026-09-05T12:30:00Z",
                }
            ).encode(),
        ),
    )


def _success_client(payload: bytes) -> FakeDriveClient:
    return FakeDriveClient(
        [
            _metadata_response(len(payload)),
            DriveHttpStream(
                200,
                {"content-type": "application/gzip", "content-length": str(len(payload))},
                (payload[:3], payload[3:11], payload[11:]),
            ),
        ]
    )


def test_google_drive_api_satisfies_shared_transport_contract(tmp_path: Path) -> None:
    payload = b"gameid,league\n1,LCK\n"
    policy = _policy()

    def factory(content: bytes) -> GoogleDriveApiTransport:
        return GoogleDriveApiTransport(
            policy=policy,
            bearer=SecretStr("authorized-bearer"),
            client=_success_client(content),
            clock=CLOCK,
        )

    assert_source_transport_contract(
        factory=factory,
        policy=policy,
        source=SOURCE,
        payload=payload,
        destination=tmp_path / "source.part",
    )


@pytest.mark.parametrize(
    ("status", "reason", "error_type", "retryable"),
    [
        (404, "notFound", SourceNotFound, False),
        (403, "insufficientPermissions", SourcePermissionDenied, False),
        (403, "downloadQuotaExceeded", SourceQuotaExceeded, True),
        (429, "rateLimitExceeded", SourceRateLimited, True),
    ],
)
def test_drive_errors_are_classified_before_any_file_is_written(
    tmp_path: Path,
    status: int,
    reason: str,
    error_type: type[SourceTransportError],
    retryable: bool,
) -> None:
    body = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode()
    client = FakeDriveClient([DriveHttpStream(status, {}, (body,))])
    transport = GoogleDriveApiTransport(
        policy=_policy(),
        bearer=SecretStr("credential-value"),
        client=client,
        clock=CLOCK,
    )
    destination = tmp_path / "source.part"

    with pytest.raises(error_type) as captured:
        transport.download(SOURCE, destination)

    assert captured.value.retryable is retryable
    assert destination.exists() is False


def test_bearer_is_absent_from_repr_and_safe_error() -> None:
    credential = "credential-that-must-never-leak"
    client = FakeDriveClient([DriveHttpStream(403, {}, (b"{}",))])
    transport = GoogleDriveApiTransport(
        policy=_policy(),
        bearer=SecretStr(credential),
        client=client,
        clock=CLOCK,
    )

    with pytest.raises(SourcePermissionDenied) as captured:
        transport.probe(SOURCE)

    assert credential not in repr(transport)
    assert credential not in str(captured.value)
    assert credential not in repr(captured.value.to_dict())


def test_size_limit_removes_partial_download(tmp_path: Path) -> None:
    client = FakeDriveClient(
        [DriveHttpStream(200, {"content-type": "application/gzip"}, (b"1234", b"5678"))]
    )
    transport = GoogleDriveApiTransport(
        policy=_policy(max_bytes=6),
        bearer=SecretStr("authorized"),
        client=client,
        clock=CLOCK,
    )
    destination = tmp_path / "source.part"

    with pytest.raises(SourceTooLarge):
        transport.download(SOURCE, destination)

    assert destination.exists() is False


def test_api_preexisting_destination_is_never_removed(tmp_path: Path) -> None:
    destination = tmp_path / "source.part"
    destination.write_bytes(b"keep-me")
    transport = GoogleDriveApiTransport(
        policy=_policy(),
        bearer=SecretStr("authorized"),
        client=FakeDriveClient(
            [DriveHttpStream(200, {"content-type": "application/gzip"}, (b"new",))]
        ),
        clock=CLOCK,
    )

    with pytest.raises(FileExistsError):
        transport.download(SOURCE, destination)

    assert destination.read_bytes() == b"keep-me"


def test_transport_is_enabled_only_when_bearer_is_configured() -> None:
    without = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "real",
            "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "odds_provider": "disabled",
        }
    )
    with_bearer = without.model_copy(update={"oe_google_drive_bearer": SecretStr("authorized")})

    assert GoogleDriveApiTransport.from_settings(without) is None
    assert GoogleDriveApiTransport.from_settings(with_bearer) is not None
    assert "authorized" not in repr(with_bearer)

    with pytest.raises(ValueError, match="ne peut pas être vide"):
        without.model_copy().model_validate(
            {
                **without.model_dump(),
                "oe_google_drive_bearer": "   ",
            }
        )
