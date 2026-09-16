"""Content-addressed files, written before publishing their database references."""

import hashlib
import os
import tempfile
import threading
from pathlib import Path

_write_lock = threading.Lock()


def store_bytes(root: Path, namespace: str, data: bytes, suffix: str) -> tuple[str, str]:
    digest = hashlib.sha256(data).hexdigest()
    relative = Path("catalog") / namespace / digest[:2] / f"{digest}.{suffix}"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    # Different source URLs can resolve to the same image. Serialize publication
    # within the worker, including verification reads (Windows open-file semantics).
    # The source's PostgreSQL lock already excludes another publishing process.
    with _write_lock:
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError("Stored catalog artifact checksum mismatch")
        else:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                temporary = Path(output.name)
            try:
                with temporary.open("wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    return digest, relative.as_posix()


def verify_artifact(root: Path, relative: str, digest: str) -> bool:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return False
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() == digest
