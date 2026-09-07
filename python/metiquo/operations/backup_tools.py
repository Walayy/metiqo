"""Outils PostgreSQL de sauvegarde et erreurs sans credentials."""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import IO

from sqlalchemy.engine import URL

from metiquo.foundation.cancellation import checkpoint


class BackupError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            checkpoint()
            digest.update(chunk)
    return digest.hexdigest()


def run_process(
    arguments: list[str],
    *,
    timeout: int,
    stdin: IO[bytes] | int | None = None,
    stdout: IO[bytes] | int = subprocess.DEVNULL,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    checkpoint()
    deadline = time.monotonic() + timeout
    with subprocess.Popen(
        arguments, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, env=env
    ) as process:
        try:
            while True:
                checkpoint()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(arguments, timeout)
                try:
                    output, errors = process.communicate(timeout=min(0.2, remaining))
                    return subprocess.CompletedProcess(
                        arguments, process.returncode, output, errors
                    )
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            process.terminate()
            try:
                process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            raise


class PostgresTools:
    """Libpq reçoit les credentials par environnement, jamais dans les arguments."""

    def __init__(
        self,
        url: URL,
        *,
        dump_command: tuple[str, ...] = ("pg_dump",),
        restore_command: tuple[str, ...] = ("pg_restore",),
        environment_overrides: Mapping[str, str] | None = None,
        timeout: int = 3600,
    ) -> None:
        self.dump_command, self.timeout = dump_command, timeout
        self.restore_command = restore_command
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
                result = run_process(
                    [
                        *self.dump_command,
                        "--format=custom",
                        "--no-owner",
                        "--no-acl",
                        "--no-password",
                        f"--snapshot={snapshot}",
                    ],
                    stdout=stream,
                    env=self.environment,
                    timeout=self.timeout,
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

    def restore(self, source: Path, database: str) -> None:
        try:
            with source.open("rb") as stream:
                result = run_process(
                    [
                        *self.restore_command,
                        "--dbname",
                        database,
                        "--single-transaction",
                        "--exit-on-error",
                        "--no-owner",
                        "--no-acl",
                        "--no-password",
                    ],
                    stdin=stream,
                    stdout=subprocess.DEVNULL,
                    env={**self.environment, "PGDATABASE": database},
                    timeout=self.timeout,
                )
            if result.returncode:
                raise BackupError("RESTORE_DATABASE_FAILED")
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BackupError("RESTORE_DATABASE_UNAVAILABLE") from error
