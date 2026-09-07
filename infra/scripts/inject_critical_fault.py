"""Exercice CI explicite : autoriser à tort une observation exactement au cutoff."""

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def inject(root: Path) -> dict[str, str]:
    path = root / "python/metiquo/features/temporal.py"
    before = path.read_bytes()
    content = before.decode("utf-8")
    for original, faulty in (
        ("if value >= self.at)", "if value > self.at)"),
        ("if maximum >= cutoff:", "if maximum > cutoff:"),
    ):
        if content.count(original) != 1:
            raise ValueError("Le contrôle temporel a changé : exercice à réviser explicitement")
        content = content.replace(original, faulty)
    after = content.encode("utf-8")
    path.write_bytes(after)
    return {
        "file": path.relative_to(root).as_posix(),
        "beforeSha256": hashlib.sha256(before).hexdigest(),
        "afterSha256": hashlib.sha256(after).hexdigest(),
    }


if __name__ == "__main__":
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Cette injection est réservée au checkout éphémère de l'exercice CI.")
    print(json.dumps(inject(ROOT), sort_keys=True))
