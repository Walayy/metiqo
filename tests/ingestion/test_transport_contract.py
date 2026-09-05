"""Contrat de transport et dérivation de sa politique depuis la configuration."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from metiquo.config import Settings
from metiquo.ingestion.transport import (
    DownloadReceipt,
    RetryPolicy,
    SourceMetadata,
    SourceRef,
    SourceTransport,
    TransportPolicy,
)
from tests.ingestion.transport_contract import assert_source_transport_contract

NOW = datetime(2026, 9, 5, 15, tzinfo=UTC)
SOURCE = SourceRef(
    provider="oracles_elixir",
    year=2026,
    source_id="drive-file",
    locator="https://drive.google.com/file/d/drive-file/view",
    source_name="2026 match data",
    mutable=True,
)


class ContractFixtureTransport:
    def __init__(self, payload: bytes, policy: TransportPolicy) -> None:
        self._payload = payload
        self._policy = policy

    @property
    def name(self) -> str:
        return "contract-fixture"

    @property
    def policy(self) -> TransportPolicy:
        return self._policy

    def probe(self, source: SourceRef) -> SourceMetadata:
        return SourceMetadata(
            source=source,
            transport=self.name,
            probed_at=NOW,
            content_length=len(self._payload),
            content_type="text/csv",
        )

    def download(self, source: SourceRef, destination: Path) -> DownloadReceipt:
        destination.write_bytes(self._payload)
        return DownloadReceipt(
            source=source,
            transport=self.name,
            destination=destination,
            byte_size=len(self._payload),
            sha256=hashlib.sha256(self._payload).hexdigest(),
            started_at=NOW,
            completed_at=NOW,
            content_type="text/csv",
        )


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "app_data_mode": "mock",
        "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
        "odds_provider": "mock",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_reference_transport_satisfies_shared_contract(tmp_path: Path) -> None:
    policy = TransportPolicy.from_settings(_settings())

    assert_source_transport_contract(
        factory=lambda payload: ContractFixtureTransport(payload, policy),
        policy=policy,
        source=SOURCE,
        payload=b"gameid,league\n1,LCK\n",
        destination=tmp_path / "source.part",
    )


def test_transport_protocol_is_structural() -> None:
    policy = TransportPolicy.from_settings(_settings())
    transport = ContractFixtureTransport(b"payload", policy)

    assert isinstance(transport, SourceTransport)


def test_policy_is_derived_from_validated_settings() -> None:
    policy = TransportPolicy.from_settings(
        _settings(
            oe_connect_timeout_seconds=2.5,
            oe_read_timeout_seconds=9,
            oe_max_download_bytes=1234,
            oe_max_redirects=2,
            oe_retry_max_attempts=3,
            oe_retry_base_seconds=0.5,
            oe_retry_max_seconds=8,
        )
    )

    assert policy == TransportPolicy(
        connect_timeout_seconds=2.5,
        read_timeout_seconds=9,
        download_timeout_seconds=900,
        max_download_bytes=1234,
        max_redirects=2,
        retry=RetryPolicy(3, 0.5, 8),
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"oe_connect_timeout_seconds": 0},
        {"oe_read_timeout_seconds": 0},
        {"oe_max_download_bytes": 0},
        {"oe_max_redirects": 11},
        {"oe_retry_max_attempts": 0},
        {"oe_retry_base_seconds": 31, "oe_retry_max_seconds": 30},
    ],
)
def test_invalid_transport_policy_configuration_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        _settings(**overrides)


def test_contract_values_reject_wrong_provider_and_digest() -> None:
    with pytest.raises(ValueError, match="uniquement oracles_elixir"):
        SourceRef(
            provider="another_source",
            year=2026,
            source_id="id",
            locator="https://example.test",
            source_name="data",
            mutable=False,
        )

    with pytest.raises(ValueError, match="SHA-256"):
        DownloadReceipt(
            source=SOURCE,
            transport="fixture",
            destination=Path("source.part"),
            byte_size=1,
            sha256="invalid",
            started_at=NOW,
            completed_at=NOW,
        )
