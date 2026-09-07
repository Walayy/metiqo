"""Préparer des fixtures pour l'UID de production et rendre leur propriété au runner."""

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest


def prepare_storage(image: str, directory: Path, request: pytest.FixtureRequest) -> None:
    original_mode = stat.S_IMODE(directory.stat().st_mode)
    directory.chmod(0o755)

    def own(uid: int, gid: int) -> None:
        script = """
import os
from pathlib import Path
root = Path('/fixture')
for path in root.rglob('*'):
    os.chown(path, int(os.environ['FIXTURE_UID']), int(os.environ['FIXTURE_GID']))
"""
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--read-only",
                "--network",
                "none",
                "--user",
                "0:0",
                "--cap-drop",
                "ALL",
                "--cap-add",
                "CHOWN",
                "--cap-add",
                "DAC_OVERRIDE",
                "--mount",
                f"type=bind,source={directory.resolve()},target=/fixture",
                "-e",
                f"FIXTURE_UID={uid}",
                "-e",
                f"FIXTURE_GID={gid}",
                image,
                "python",
                "-c",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr

    uid = os.getuid() if hasattr(os, "getuid") else 0
    gid = os.getgid() if hasattr(os, "getgid") else 0

    def restore() -> None:
        own(uid, gid)
        directory.chmod(original_mode)

    request.addfinalizer(restore)
    own(10001, 10001)


def storage_matches(image: str, directory: Path, pattern: str) -> bool:
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--read-only",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--mount",
            f"type=bind,source={directory.resolve()},target=/fixture,readonly",
            "-e",
            f"FIXTURE_PATTERN={pattern}",
            image,
            "python",
            "-c",
            "import json,os; from pathlib import Path; "
            "print(json.dumps(any(Path('/fixture').glob(os.environ['FIXTURE_PATTERN']))))",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return bool(json.loads(result.stdout))
