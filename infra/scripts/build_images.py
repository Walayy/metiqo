"""Construire les images avec une révision Git vérifiée, absente si le checkout est modifié."""

import argparse
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def code_revision(root: Path) -> str | None:
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return (
        revision
        if not status and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", revision)
        else None
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    revision = code_revision(ROOT)
    if args.require_clean and revision is None:
        print("Release refusée : une révision Git propre est obligatoire.")
        return 1
    print(f"Révision des images : {revision or 'absente ; entraînement réel indisponible'}")
    environment = {**os.environ, "BUILD_CODE_COMMIT": revision or ""}
    subprocess.run(
        ["docker", "compose", "config", "--quiet"], cwd=ROOT, env=environment, check=True
    )
    subprocess.run(
        ["docker", "compose", "--profile", "mock", "--profile", "production", "build"],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
