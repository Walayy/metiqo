"""Assertions partagées par les implémentations SourceTransport."""

import hashlib
from collections.abc import Callable
from pathlib import Path

from metiquo.ingestion.transport import SourceRef, SourceTransport, TransportPolicy


def assert_source_transport_contract(
    *,
    factory: Callable[[bytes], SourceTransport],
    policy: TransportPolicy,
    source: SourceRef,
    payload: bytes,
    destination: Path,
) -> None:
    transport = factory(payload)
    assert isinstance(transport, SourceTransport)
    assert transport.name
    assert transport.policy == policy

    metadata = transport.probe(source)
    assert metadata.source == source
    assert metadata.transport == transport.name
    assert metadata.content_length == len(payload)

    receipt = transport.download(source, destination)
    assert receipt.source == source
    assert receipt.transport == transport.name
    assert receipt.destination == destination
    assert receipt.byte_size == len(payload)
    assert receipt.sha256 == hashlib.sha256(payload).hexdigest()
    assert destination.read_bytes() == payload
