"""Exercice optionnel du bootstrap CLI et de la session via Next et Chromium."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command

from tests.integration.test_migrations import alembic_config
from tests.integration.test_owner_sessions import FIXTURE_PASSWORD


@pytest.mark.integration
def test_owner_browser_exercise(postgresql_url: str, tmp_path: Path) -> None:
    if os.environ.get("RUN_OWNER_BROWSER") != "1":
        pytest.skip("RUN_OWNER_BROWSER=1 requis pour construire et lancer Chromium")
    command.upgrade(alembic_config(postgresql_url), "head")
    password_file = tmp_path / "owner-fixture.txt"
    password_file.write_text(FIXTURE_PASSWORD, encoding="utf-8")
    environment = {
        **os.environ,
        "APP_ENV": "test",
        "APP_DATA_MODE": "mock",
        "ODDS_PROVIDER": "mock",
        "AUTH_MODE": "owner",
        "DATABASE_URL": postgresql_url,
        "E2E_AUTH_MODE": "owner",
        "E2E_DATABASE_URL": postgresql_url,
        "CI": "true",
        "PYTHONIOENCODING": "utf-8",
    }
    bootstrap = subprocess.run(
        [
            sys.executable,
            "-m",
            "metiquo.cli",
            "auth",
            "bootstrap-owner",
            "--username",
            "owner",
            "--password-file",
            str(password_file),
            "--json",
        ],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert bootstrap.returncode == 0, bootstrap.stderr
    assert json.loads(bootstrap.stdout)["ownerId"]
    assert FIXTURE_PASSWORD not in bootstrap.stdout + bootstrap.stderr
    pnpm = shutil.which("pnpm")
    assert pnpm is not None
    browser = subprocess.run(
        [pnpm, "exec", "playwright", "test", "owner-session.spec.ts"],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        shell=os.name == "nt",
    )
    assert browser.returncode == 0, browser.stdout + browser.stderr
