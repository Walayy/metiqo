"""Preuve exécutable du gate P2 sur une base PostgreSQL réellement vide."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_ingestion_gate_demo_rebuilds_from_empty_database(postgresql_url: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "infra/scripts/demo_ingestion_gate.py",
            "--database-url",
            postgresql_url,
            "--json",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    report = cast(dict[str, object], json.loads(result.stdout))

    assert report["ok"] is True
    assert report["database"] == "ephemeral"
    assert report["backfillStatus"] == "succeeded"
    assert report["migrationRevision"] == "20260906_0018"
    idempotence = cast(dict[str, object], report["idempotence"])
    assert idempotence["canonicalStateSha256"] == (
        "8cc193e74ab3b0ca7ff8deb1df226a6b0155767ef41c73ef0ee014e489687ef8"
    )
    assert idempotence["rowCount"] == 12
    assert idempotence["secondRunUnchanged"] == 12
    assert idempotence["snapshotId"]

    quota = cast(dict[str, object], report["quota"])
    assert quota["ingestedSnapshotCount"] == 0
    assert quota["freshness"] == "degraded"
    assert quota["reusedSnapshotId"] == idempotence["snapshotId"]

    quarantine = cast(dict[str, object], report["quarantine"])
    assert quarantine["reasonCode"] == "SCHEMA_INCOMPATIBLE"
    assert quarantine["currentSnapshotId"] == quota["reusedSnapshotId"]
    assert report["requireFresh"] == {
        "errorCode": "FRESH_DATA_REQUIRED",
        "exitCode": 3,
    }
    assert report["additiveSchema"] == {"freshness": "fresh"}
    assert report["retroactiveChange"] == {
        "affectedFrom": "2026-01-10",
        "revisionCount": 1,
        "updated": 1,
    }

    manifest = cast(dict[str, object], report["manifestVerification"])
    assert manifest["snapshotId"]
    assert len(cast(str, manifest["sha256"])) == 64
    assert cast(int, manifest["byteSize"]) > 0
