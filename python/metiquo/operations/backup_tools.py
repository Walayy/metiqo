"""Outils PostgreSQL de sauvegarde et erreurs sans credentials."""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.engine import URL


class BackupError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class PostgresTools:
    """Libpq reçoit les credentials par environnement, jamais dans les arguments."""

    def __init__(
        self,
        url: URL,
        *,
        dump_command: tuple[str, ...] = ("pg_dump",),
        environment_overrides: Mapping[str, str] | None = None,
        timeout: int = 3600,
    ) -> None:
        self.dump_command, self.timeout = dump_command, timeout
        self.environment = {
            **os.environ,
            "PGHOST": url.host or "localhost",
            "PGPORT": str(url.port or 5432),
            "PGUSER": url.username or "",
            "PGPASSWORD": url.password or "",
            "PGDATABASE": url.database or "",
            "PGCONNECT_TIMEOUT": "10",
        }
        for parameter in ("sslmode", "sslrootcert", "sslcert", "sslkey", "connect_timeout"):
            value = url.query.get(parameter)
            if isinstance(value, str):
                self.environment[f"PG{parameter.upper()}"] = value
        self.environment.update(environment_overrides or {})

    def dump(self, snapshot: str, target: Path) -> None:
        try:
            with target.open("xb") as stream:
                result = subprocess.run(
                    [
                        *self.dump_command,
                        "--format=custom",
                        "--no-owner",
                        "--no-acl",
                        "--no-password",
                        f"--snapshot={snapshot}",
                    ],
                    stdout=stream,
                    stderr=subprocess.PIPE,
                    env=self.environment,
                    timeout=self.timeout,
                    check=False,
                )
                stream.flush()
                os.fsync(stream.fileno())
            if result.returncode:
                raise BackupError("BACKUP_DUMP_FAILED")
            with target.open("rb") as stream:
                if stream.read(5) != b"PGDMP":
                    raise BackupError("BACKUP_DUMP_INVALID")
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackupError("BACKUP_DUMP_UNAVAILABLE") from error
