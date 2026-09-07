"""Exécutables réels pour les exercices PostgreSQL et age locaux ou CI."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import Engine

from metiquo.operations.backup_tools import PostgresTools


def postgres_tools(engine: Engine) -> PostgresTools:
    container = os.environ.get("TEST_PG_CONTAINER")
    if not container and (shutil.which("pg_dump") is None or shutil.which("pg_restore") is None):
        pytest.skip("Clients PostgreSQL ou TEST_PG_CONTAINER requis")
    prefix = (
        (
            "docker",
            "exec",
            "-i",
            "-e",
            "PGHOST",
            "-e",
            "PGPORT",
            "-e",
            "PGUSER",
            "-e",
            "PGPASSWORD",
            "-e",
            "PGDATABASE",
            container,
        )
        if container
        else ()
    )
    return PostgresTools(
        engine.url,
        dump_command=(*prefix, "pg_dump"),
        restore_command=(*prefix, "pg_restore"),
        environment_overrides={"PGHOST": "127.0.0.1", "PGPORT": "5432"} if container else {},
    )


def age_key(directory: Path) -> tuple[str, str, Path]:
    age = os.environ.get("TEST_AGE_BINARY") or shutil.which("age")
    if not age:
        pytest.skip("age ou TEST_AGE_BINARY requis")
    keygen = str(Path(age).with_name("age-keygen.exe" if os.name == "nt" else "age-keygen"))
    key = directory / "restore-identity.txt"
    subprocess.run([keygen, "-o", str(key)], check=True, capture_output=True)
    recipient = subprocess.run(
        [keygen, "-y", str(key)], check=True, capture_output=True, text=True
    ).stdout.strip()
    return age, recipient, key
