from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from metiquo_api.admin import create_admin_router
from metiquo_api.auth_config import AuthSettings
from metiquo_core.models import ScriptRun, WorkerLogEntry
from metiquo_worker.worker_logs import bind_run, emit, prune
from sqlalchemy import select
from sqlalchemy.orm import Session


@pytest.mark.integration
def test_worker_logs_are_scoped_paginated_sanitized_and_admin_only(database, monkeypatch):
    engine, _ = database
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        run = ScriptRun(
            script_id="stake-markets",
            trigger="schedule",
            status="succeeded",
            requested_at=now,
            available_at=now,
            started_at=now,
            finished_at=now,
        )
        db.add(run)
        db.flush()
        run_id = run.id
    binding = bind_run("stake-markets", run_id)
    try:
        emit(engine, 2, "run_started")
        emit(
            engine,
            2,
            "stake_market_ambiguous",
            event_id="845833",
            context={"kind": "ValueError", "cookie": "super-secret-cookie"},
        )
        emit(
            engine,
            2,
            "stake_cycle_interrupted",
            event_id="https://stake.bet/private?token=secret",
            context={
                "kind": "RuntimeError",
                "password": "postgresql://user:secret@db/metiquo",
                "frames": ["stake_browser.py:event:358", "C:/private/token"],
            },
        )
    finally:
        binding.reset()
    emit(engine, 1, "worker_started")
    with Session(engine) as db:
        rows = db.scalars(select(WorkerLogEntry).order_by(WorkerLogEntry.id)).all()
        assert len(rows) == 4
        assert [row.run_id for row in rows[:3]] == [run_id] * 3
        assert rows[-1].run_id is None
        assert rows[2].event_id is None
        assert "secret" not in str(rows[2].context)
        assert rows[2].context == {
            "kind": "RuntimeError",
            "frames": ["stake_browser.py:event:358"],
        }
        info_id, warning_id, error_id = [row.id for row in rows[:3]]

    app = FastAPI()
    app.include_router(
        create_admin_router(
            engine, AuthSettings(auth_secret="isolated-test-key-that-is-at-least-32-characters")
        )
    )
    with TestClient(app, base_url="http://localhost:8080") as client:
        path = f"/api/v1/admin/worker-logs?workerId=2&runId={run_id}"
        assert client.get(path).status_code == 401
        monkeypatch.setattr(
            "metiquo_api.admin.authenticated_user",
            lambda *_: SimpleNamespace(id=uuid4(), role="user"),
        )
        assert client.get(path).status_code == 403
        monkeypatch.setattr(
            "metiquo_api.admin.authenticated_user",
            lambda *_: SimpleNamespace(id=uuid4(), role="admin"),
        )
        newest_response = client.get(f"{path}&limit=1")
        assert newest_response.status_code == 200, newest_response.text
        newest = newest_response.json()
        assert newest["items"][0]["id"] == error_id and newest["hasMore"] is True
        assert newest["run"]["id"] == str(run_id)
        older = client.get(f"{path}&before={error_id}&limit=1").json()
        assert older["items"][0]["id"] == warning_id
        after = client.get(f"{path}&after={info_id}&limit=1").json()
        assert after["items"][0]["id"] == warning_id and after["hasMore"] is True
        filtered = client.get(f"{path}&level=error&q=absent").json()
        assert filtered["items"] == []
        assert [entry["id"] for entry in filtered["incidents"]] == [error_id, warning_id]
        assert client.get(f"{path}&q=845833").json()["items"][0]["id"] == warning_id
        assert client.get(f"{path}&before=1&after=1").status_code == 422
        assert client.get("/api/v1/admin/worker-logs?workerId=0").status_code == 422
        assert client.get(f"/api/v1/admin/worker-logs?workerId=1&runId={run_id}").status_code == 404
        services = client.get("/api/v1/admin/scripts").json()["workers"]
        assert [service["id"] for service in services] == [1, 2, 3]
        outside = client.get("/api/v1/admin/worker-logs?workerId=1").json()["items"]
        assert len(outside) == 1 and outside[0]["scriptId"] is None
        assert outside[0]["runId"] is None

    with Session(engine) as db, db.begin():
        old = db.get(WorkerLogEntry, info_id)
        assert old is not None
        old.recorded_at = now - timedelta(days=15)
    with TestClient(app, base_url="http://localhost:8080") as client:
        retained = client.get(f"/api/v1/admin/worker-logs?workerId=2&runId={run_id}").json()
        assert info_id not in [entry["id"] for entry in retained["items"]]
    prune(engine)
    with Session(engine) as db:
        assert db.get(WorkerLogEntry, info_id) is None
        assert db.get(WorkerLogEntry, warning_id) is not None
