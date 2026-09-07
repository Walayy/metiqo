"""Construire le bundle avec des secrets sentinelles et inspecter les chunks publics."""

import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_frontend_bundle_excludes_server_secrets() -> None:
    if os.environ.get("RUN_BUNDLE_SECRET_SCAN") != "1":
        pytest.skip("RUN_BUNDLE_SECRET_SCAN=1 requis pour construire le bundle")
    pnpm = shutil.which("pnpm")
    assert pnpm is not None
    database_canary = f"server-database-{uuid4().hex}"
    bearer_canary = f"server-bearer-{uuid4().hex}"
    result = subprocess.run(
        [pnpm, "run", "build:web"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        shell=os.name == "nt",
        env={
            **os.environ,
            "APP_DATA_MODE": "mock",
            "DATABASE_URL": f"postgresql+psycopg://user:{database_canary}@postgres:5432/metiquo",
            "OE_GOOGLE_DRIVE_BEARER": bearer_canary,
        },
    )
    assert result.returncode == 0, result.stdout + result.stderr
    files = tuple((ROOT / "apps/web/.next/static").rglob("*"))
    chunks = [path for path in files if path.is_file() and path.suffix in {".js", ".json", ".map"}]
    assert chunks
    for path in chunks:
        content = path.read_bytes()
        assert database_canary.encode() not in content, f"Database canary in {path.name}"
        assert bearer_canary.encode() not in content, f"Provider canary in {path.name}"
    assert database_canary not in result.stdout + result.stderr
    assert bearer_canary not in result.stdout + result.stderr
