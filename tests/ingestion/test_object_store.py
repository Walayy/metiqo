"""Tests du backend filesystem adressé par hash."""

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from metiquo.ingestion.object_store import FilesystemObjectStore, ObjectCollisionError


def test_object_is_promoted_with_complete_layout(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path / "store")
    payload = b"gameid,league\n1,LCK\n"

    stored = store.put_source(
        year=2026,
        chunks=(payload[:8], payload[8:]),
        source_kind="csv",
        manifest={"sourceFileId": "drive-2026", "rows": 1},
        schema={"columns": ["gameid", "league"]},
        quality_report={"blocking": 0},
    )

    digest = hashlib.sha256(payload).hexdigest()
    expected_directory = tmp_path / "store" / "year=2026" / f"sha256={digest}"
    assert stored.sha256 == digest
    assert stored.source_path == expected_directory / "source.csv"
    assert stored.object_key == f"year=2026/sha256={digest}/source.csv"
    assert stored.reused is False
    assert stored.source_path.read_bytes() == payload
    assert {path.name for path in expected_directory.iterdir()} == {
        "manifest.json",
        "quality-report.json",
        "schema.json",
        "source.csv",
    }
    assert (expected_directory / "manifest.json").read_text() == (
        '{"rows":1,"sourceFileId":"drive-2026"}\n'
    )
    assert not list((tmp_path / "store" / "year=2026").glob(".tmp-*"))


def test_same_hash_is_reused_without_mutating_existing_object(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)
    first = store.put_source(
        year=2025,
        chunks=(b"immutable",),
        manifest={"version": 1},
    )
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in first.object_directory.iterdir()
    }

    second = store.put_source(
        year=2025,
        chunks=(b"imm", b"utable"),
        source_kind="csv",
        manifest={"version": 2},
        schema={"must": "not be added"},
    )
    after = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in first.object_directory.iterdir()
    }

    assert second.reused is True
    assert second.source_path == first.source_path
    assert second.source_kind == "bin"
    assert before == after


def test_failed_stream_leaves_no_partial_object(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)

    def broken_chunks() -> Iterator[bytes]:
        yield b"partial"
        raise OSError("source interrompue")

    with pytest.raises(OSError, match="source interrompue"):
        store.put_source(year=2024, chunks=broken_chunks())

    year_directory = tmp_path / "year=2024"
    assert list(year_directory.iterdir()) == []


def test_corrupted_existing_object_is_never_reused(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)
    stored = store.put_source(year=2023, chunks=(b"trusted",))
    stored.source_path.write_bytes(b"tampered")

    with pytest.raises(ObjectCollisionError, match="contient le hash"):
        store.put_source(year=2023, chunks=(b"trusted",))


def test_open_validates_the_address_and_returns_source(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)
    stored = store.put_source(year=2022, chunks=(b"payload",), source_kind="csv")

    with store.open_source(year=2022, sha256=stored.sha256) as stream:
        assert stream.read() == b"payload"

    with pytest.raises(ValueError, match="digest hexadécimal"):
        store.open_source(year=2022, sha256="../escape")
