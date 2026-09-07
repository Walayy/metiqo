"""Exercise real worker writes and SIGTERM with a read-only root and PostgreSQL."""

import json
import os
import subprocess
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine

from metiquo.api.app import create_app
from metiquo.worker.queue import PostgresJobQueue
from tests.integration.test_backfill import _seed_catalogs
from tests.integration.test_migrations import alembic_config
from tests.integration.test_real_admin_api import ReadyProbe, _request, _settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_packaged_worker_sync_and_signal_shutdown(postgresql_url: str, tmp_path: Path) -> None:
    image = os.environ.get("TEST_OPS_IMAGE")
    postgres = os.environ.get("TEST_PG_CONTAINER")
    if not image or not postgres:
        pytest.skip("TEST_OPS_IMAGE and TEST_PG_CONTAINER required")
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    _seed_catalogs(engine, dataset="league_of_legends_match_data", years=range(2026, 2027))
    settings = _settings(postgresql_url, "real").model_copy(update={"object_store_root": tmp_path})
    app = create_app(settings=settings, readiness_probe=ReadyProbe())
    receipt = _request(
        app,
        "POST",
        "/api/v1/admin/oracles-elixir/sync?year=2026",
        headers={"Idempotency-Key": "container-ops-sync"},
    )
    assert receipt.status_code == 202
    job_id = UUID(receipt.json()["data"]["jobId"])
    environment = {
        **os.environ,
        "DATABASE_URL": engine.url.set(host="127.0.0.1", port=5432).render_as_string(
            hide_password=False
        ),
    }
    common = [
        "--read-only",
        "--network",
        f"container:{postgres}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--tmpfs",
        "/tmp:mode=1777",
        "-e",
        "DATABASE_URL",
        "-e",
        "APP_ENV=test",
        "-e",
        "APP_DATA_MODE=real",
        "-e",
        "AUTH_MODE=disabled",
        "-e",
        "ODDS_PROVIDER=disabled",
        "-e",
        "OBJECT_STORE_ROOT=/data",
        "-e",
        "WORKER_SCHEDULER_ENABLED=false",
    ]
    for name in ("raw", "models", "quarantine", "backups", "work"):
        folder = tmp_path / name
        folder.mkdir()
        folder.chmod(0o777)
        common.extend(["--mount", f"type=bind,source={folder},target=/data/{name}"])
    common.extend(
        [
            "--mount",
            f"type=bind,source={ROOT / 'tests/fixtures/oracles_elixir'},target=/fixtures,readonly",
        ]
    )
    script = """
import json
from pathlib import Path
from sqlalchemy import create_engine
from metiquo.config import load_settings
from metiquo.contracts.enums import DataMode
from metiquo.ingestion.sync import OracleElixirYearSync
from metiquo.ingestion.local_transports import LocalFixtureTransport
from metiquo.ingestion.transport import TransportPolicy
from metiquo.worker.handlers import default_handlers
from metiquo.worker.queue import PostgresJobQueue
from metiquo.worker.runner import PostgresJobRunner
settings = load_settings()
def fixture_transport(self, source, fixture_path):
    return (LocalFixtureTransport(policy=TransportPolicy.from_settings(settings),
        fixtures={source.source_id: Path('/fixtures/dq_valid.csv')}, data_mode=DataMode.MOCK),)
OracleElixirYearSync._transports = fixture_transport
engine = create_engine(settings.database_url.get_secret_value())
try:
    runner = PostgresJobRunner(PostgresJobQueue(engine),
        default_handlers(engine, settings), owner='packaged-worker')
    assert runner.run_once()
finally:
    engine.dispose()
print(json.dumps({'readonlyRootSync': True}))
"""
    result = subprocess.run(
        ["docker", "run", "--rm", *common, image, "python", "-c", script],
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["readonlyRootSync"]
    queue = PostgresJobQueue(engine)
    assert queue.get(job_id).status == "succeeded"
    assert list((tmp_path / "raw").glob("**/source.csv"))
    assert not list((tmp_path / "work").iterdir())
    stop_job = queue.enqueue("test.shutdown", {}, key="container-shutdown", scope="test:shutdown")
    signal_script = """
from pathlib import Path
import metiquo.worker.__main__ as worker
class WaitingHandler:
    def handle(self, context):
        Path('/data/work/entered').write_text('ready')
        context.cancellation.wait(60)
        context.cancellation.raise_if_cancelled()
worker.default_handlers = lambda engine, settings: {'test.shutdown': WaitingHandler()}
raise SystemExit(worker.main())
"""
    container = "metiquo-ops010-" + uuid4().hex[:12]
    try:
        started = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container,
                *common,
                image,
                "python",
                "-c",
                signal_script,
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert started.returncode == 0, started.stderr
        deadline = time.monotonic() + 20
        while not (tmp_path / "work/entered").exists():
            assert time.monotonic() < deadline
            time.sleep(0.1)
        stopped = subprocess.run(
            ["docker", "stop", "--time", "10", container],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert stopped.returncode == 0, stopped.stderr
        state = subprocess.run(
            ["docker", "inspect", container, "--format", "{{.State.ExitCode}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert state.stdout.strip() == "0", "SIGTERM must not reach Docker's forced kill"
        assert queue.get(stop_job.job_id).status == "cancelled"
        logs = subprocess.run(
            ["docker", "logs", container], capture_output=True, text=True, check=True
        )
        assert "worker.stopped" in logs.stdout + logs.stderr
        assert environment["DATABASE_URL"] not in logs.stdout + logs.stderr
    finally:
        subprocess.run(
            ["docker", "rm", "-f", container], capture_output=True, check=False, timeout=20
        )
        app.state.real_admin_engine.dispose()
        engine.dispose()
