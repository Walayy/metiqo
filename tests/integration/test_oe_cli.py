"""Parcours CLI Oracle's Elixir contre PostgreSQL réel et ObjectStore local."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "oracles_elixir" / "dq_valid.csv"
YEAR = 2099


def _alembic_config(url: str) -> Config:
    config = Config(ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    return config


def _run(environment: dict[str, str], *arguments: str) -> tuple[int, dict[str, object]]:
    result = subprocess.run(
        [sys.executable, "-m", "metiquo.cli", *arguments, "--json"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    payload = result.stdout if result.returncode == 0 else result.stderr
    return result.returncode, cast(dict[str, object], json.loads(payload))


@pytest.mark.integration
def test_oe_cli_machine_readable_end_to_end(postgresql_url: str, tmp_path: Path) -> None:
    command.upgrade(_alembic_config(postgresql_url), "head")
    fixture = tmp_path / "dq_valid_cli.csv"
    game_id = f"OE-CLI-{uuid4().hex}"
    fixture.write_text(
        FIXTURE.read_text(encoding="utf-8")
        .replace("OE-001", game_id)
        .replace("2026-01-10", "2027-01-10"),
        encoding="utf-8",
    )
    fallback = tmp_path / "sources.json"
    fallback.write_text(
        json.dumps(
            {
                "version": 1,
                "sources": [
                    {
                        "year": YEAR,
                        "drive_file_id": "fixture_cli_2099",
                        "mutable": True,
                        "origin": "validated-bootstrap",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "APP_DATA_MODE": "mock",
        "DATABASE_URL": postgresql_url,
        "OBJECT_STORE_ROOT": str(tmp_path / "object-store"),
        "ODDS_PROVIDER": "mock",
        "OE_ALLOW_STALE": "false",
        "OE_REQUIRE_FRESH": "false",
        "OE_CURRENT_YEAR": str(YEAR),
        "OE_SOURCE_CATALOG_PATH": str(fallback),
    }

    code, catalog = _run(environment, "catalog", "refresh")
    assert code == 0
    assert catalog["ok"] is True
    assert catalog["origin"] == "validated-bootstrap"

    code, first = _run(
        environment,
        "sync",
        "--year",
        str(YEAR),
        "--require-fresh",
        "--fixture",
        str(fixture),
    )
    assert code == 0
    assert first["ok"] is True
    assert cast(dict[str, object], first["load"])["inserted"] == 12
    snapshot_id = cast(str, first["snapshotId"])

    code, second = _run(
        environment,
        "sync",
        "--year",
        str(YEAR),
        "--require-fresh",
        "--fixture",
        str(fixture),
    )
    assert code == 0
    assert second["snapshotId"] == snapshot_id
    assert cast(dict[str, object], second["load"])["unchanged"] == 12

    code, verified = _run(environment, "verify", "--snapshot", snapshot_id)
    assert code == 0
    assert verified["status"] == "validated"

    code, difference = _run(
        environment,
        "diff",
        "--left",
        snapshot_id,
        "--right",
        snapshot_id,
    )
    assert code == 0
    assert difference["identical"] is True

    code, rebuilt = _run(environment, "rebuild-canonical", "--from", "2027-01-01")
    assert code == 0
    assert rebuilt["canonicalRowsFromDate"] == 12

    code, backfill = _run(
        environment,
        "backfill",
        "--from-year",
        str(YEAR),
        "--to-year",
        str(YEAR),
        "--fixture",
        str(fixture),
    )
    assert code == 0
    assert backfill["status"] == "succeeded"


def test_oe_cli_documents_stable_exit_codes() -> None:
    from metiquo.cli.main import ExitCode

    assert {member.name: member.value for member in ExitCode} == {
        "SUCCESS": 0,
        "USAGE_OR_CONFIGURATION": 2,
        "FRESH_DATA_REQUIRED": 3,
        "SOURCE_FAILURE": 4,
        "INTEGRITY_FAILURE": 5,
        "PARTIAL_BACKFILL": 6,
    }
