"""Contrats du miroir privé, des fixtures et de leur priorité."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from metiquo.config import Settings
from metiquo.contracts.enums import DataMode
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.local_transports import (
    LocalFixtureTransport,
    MirrorSnapshot,
    MirrorTransport,
    prioritized_transports,
)
from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.ingestion.transport import (
    DownloadReceipt,
    SourceMetadata,
    SourceRef,
    TransportPolicy,
)
from tests.ingestion.transport_contract import assert_source_transport_contract

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "oracles_elixir" / "sample_2026.csv"
NOW = datetime(2026, 9, 5, 18, tzinfo=UTC)
VALIDATED_AT = datetime(2026, 9, 4, 18, tzinfo=UTC)
CLOCK = FixedClock(UtcInstant(NOW))
SOURCE = SourceRef(
    provider="oracles_elixir",
    year=2026,
    source_id="sample-2026",
    locator="fixture://sample-2026",
    source_name="sample_2026.csv",
    mutable=True,
)


def _policy() -> TransportPolicy:
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "mock",
            "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "odds_provider": "mock",
        }
    )
    return TransportPolicy.from_settings(settings)


class StaticResolver:
    def __init__(self, snapshot: MirrorSnapshot) -> None:
        self.snapshot = snapshot

    def latest_validated(self, source: SourceRef) -> MirrorSnapshot:
        del source
        return self.snapshot


class StubTransport:
    def __init__(self, name: str, policy: TransportPolicy) -> None:
        self._name = name
        self._policy = policy

    @property
    def name(self) -> str:
        return self._name

    @property
    def policy(self) -> TransportPolicy:
        return self._policy

    def probe(self, source: SourceRef) -> SourceMetadata:
        raise NotImplementedError(source)

    def download(self, source: SourceRef, destination: Path) -> DownloadReceipt:
        raise NotImplementedError(source, destination)


def test_local_fixture_satisfies_shared_contract(tmp_path: Path) -> None:
    payload = FIXTURE.read_bytes()
    policy = _policy()

    assert_source_transport_contract(
        factory=lambda content: LocalFixtureTransport(
            policy=policy,
            fixtures={SOURCE.source_id: FIXTURE},
            data_mode=DataMode.MOCK,
            clock=CLOCK,
        ),
        policy=policy,
        source=SOURCE,
        payload=payload,
        destination=tmp_path / "fixture.part",
    )


def test_mirror_satisfies_contract_without_inventing_confirmation(tmp_path: Path) -> None:
    payload = FIXTURE.read_bytes()
    policy = _policy()

    def factory(content: bytes) -> MirrorTransport:
        store = FilesystemObjectStore(tmp_path / "store")
        stored = store.put_source(year=2026, chunks=(content,), source_kind="csv")
        snapshot = MirrorSnapshot(
            year=2026,
            sha256=stored.sha256,
            byte_size=len(content),
            content_type="text/csv",
            validated_at=VALIDATED_AT,
            source_confirmed_at=None,
        )
        return MirrorTransport(
            policy=policy,
            object_store=store,
            resolver=StaticResolver(snapshot),
            clock=CLOCK,
        )

    transport = factory(payload)
    metadata = transport.probe(SOURCE)
    assert metadata.source_is_confirmed is False
    assert metadata.source_confirmed_at is None
    assert metadata.last_modified_at == VALIDATED_AT

    assert_source_transport_contract(
        factory=factory,
        policy=policy,
        source=SOURCE,
        payload=payload,
        destination=tmp_path / "mirror.part",
    )


def test_fixture_is_impossible_in_real_mode() -> None:
    with pytest.raises(ValueError, match=r"interdit.*real"):
        LocalFixtureTransport(
            policy=_policy(),
            fixtures={SOURCE.source_id: FIXTURE},
            data_mode=DataMode.REAL,
            clock=CLOCK,
        )


def test_transport_priority_is_explicit_for_real_and_mock() -> None:
    policy = _policy()
    api = StubTransport("google-drive-api", policy)
    public = StubTransport("google-drive-public-http", policy)
    mirror = StubTransport("validated-private-mirror", policy)
    fixture = LocalFixtureTransport(
        policy=policy,
        fixtures={SOURCE.source_id: FIXTURE},
        data_mode=DataMode.MOCK,
        clock=CLOCK,
    )

    real = prioritized_transports(
        data_mode=DataMode.REAL,
        api=api,
        public_http=public,
        mirror=mirror,
    )
    mock = prioritized_transports(
        data_mode=DataMode.MOCK,
        api=None,
        public_http=public,
        mirror=mirror,
        fixture=fixture,
    )

    assert [transport.name for transport in real] == [
        "google-drive-api",
        "google-drive-public-http",
        "validated-private-mirror",
    ]
    assert [transport.name for transport in mock] == ["local-fixture"]

    with pytest.raises(ValueError, match=r"interdite.*real"):
        prioritized_transports(
            data_mode=DataMode.REAL,
            api=api,
            public_http=public,
            mirror=mirror,
            fixture=fixture,
        )
