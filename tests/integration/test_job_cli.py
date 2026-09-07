"""Commandes opérateur de suivi, annulation et relance explicite."""

import json
from importlib import import_module

import pytest
from alembic import command
from sqlalchemy import create_engine

from metiquo.worker.queue import PostgresJobQueue
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _settings


@pytest.mark.integration
def test_job_cli_cancel_rerun_and_safe_status(
    postgresql_url: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    queue = PostgresJobQueue(engine)
    job = queue.enqueue("paper.report", {"private": "do not print"}, key="cli", scope="paper:EUR")
    cli = import_module("metiquo.cli.main")
    monkeypatch.setattr(cli, "load_settings", lambda: _settings(postgresql_url, "real"))
    for action, expected in (("show", "queued"), ("cancel", "cancelled")):
        assert cli.main(["jobs", action, str(job.job_id), "--json"]) == 0
        output = capsys.readouterr().out
        assert "do not print" not in output
        assert json.loads(output)["job"]["status"] == expected
    assert (
        cli.main(
            [
                "jobs",
                "rerun",
                str(job.job_id),
                "--key",
                "explicit-cli",
                "--actor",
                "operator",
                "--reason",
                "ready",
                "--json",
            ]
        )
        == 0
    )
    rerun = json.loads(capsys.readouterr().out)["job"]
    assert rerun["rerunOf"] == str(job.job_id) and rerun["status"] == "queued"
    engine.dispose()
