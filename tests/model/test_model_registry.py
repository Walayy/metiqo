"""Stockage adressé par contenu des artefacts de modèles."""

from pathlib import Path

import pytest

from metiquo.ingestion.object_store import FilesystemObjectStore
from metiquo.models import ModelArtifactChecksumError, ModelArtifactStore


def test_model_artifact_checksum_is_verified_before_loading(tmp_path: Path) -> None:
    store = ModelArtifactStore(FilesystemObjectStore(tmp_path))
    payload = b"metiquo-model-artifact-v1"

    reference = store.put(
        payload,
        year=2026,
        artifact_format="application/x-metiqo-model",
        code_commit="abcdef1",
    )
    repeated = store.put(
        payload,
        year=2026,
        artifact_format="application/x-metiqo-model",
        code_commit="abcdef1",
    )

    assert repeated == reference
    assert store.load(reference) == payload
    assert reference.object_key == (f"year=2026/sha256={reference.sha256}/source.bin")

    source = tmp_path / "year=2026" / f"sha256={reference.sha256}" / "source.bin"
    source.write_bytes(b"tampered-model")
    with pytest.raises(ModelArtifactChecksumError, match="checksum physique"):
        store.load(reference)
