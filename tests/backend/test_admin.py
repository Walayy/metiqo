from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from metiquo_api.main import create_app
from metiquo_core.config import Settings
from metiquo_core.models import (
    AdminAudit,
    AppUser,
    AuthRateLimit,
    AuthSession,
    ScriptRun,
    WorkerStatus,
)
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session
from test_auth import HEADERS, ORIGIN, request_code, verify
from test_auth import auth as _auth_fixture

auth = _auth_fixture

pytestmark = pytest.mark.integration


def login_admin(auth):
    client, engine, config, sent, app = auth
    with Session(engine) as db, db.begin():
        db.add(
            AppUser(
                auth_issuer="metiquo:email",
                auth_subject="admin@metiquo.fr",
                email="admin@metiquo.fr",
                role="admin",
            )
        )
        db.add(
            WorkerStatus(
                id=1,
                seen_at=datetime.now(UTC),
                scripts=["lol-catalog", "oracle-latest", "oracle-full"],
            )
        )
    response = verify(client, request_code(client, "admin@metiquo.fr"), sent[-1][1])
    assert response.status_code == 200
    return response.json()["user"]["id"]


def test_admin_routes_require_a_current_admin_session_and_origin(auth):
    client, engine, config, sent, _ = auth
    assert client.get("/api/v1/admin/users").status_code == 401
    verify(client, request_code(client), sent[-1][1])
    assert client.get("/api/v1/admin/scripts").status_code == 403
    admin_id = login_admin(auth)
    assert client.get("/api/v1/admin/users").headers["cache-control"] == "no-store"
    assert (
        client.post(
            "/api/v1/admin/scripts/lol-catalog/run", headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/admin/users/{admin_id}", json={"role": "user", "disabled": False}
        ).status_code
        == 409
    )
    with Session(engine) as db, db.begin():
        db.get(AppUser, UUID(admin_id)).role = "user"
    assert client.get("/api/v1/admin/users").status_code == 403


def test_user_management_revokes_sessions_and_blocks_suspended_login(auth):
    client, engine, config, sent, app = auth
    user = verify(client, request_code(client), sent[-1][1]).json()["user"]
    old_token = client.cookies[config.session_cookie]
    login_admin(auth)
    path = f"/api/v1/admin/users/{user['id']}"
    assert client.get("/api/v1/admin/users?q=person").json()["total"] == 1
    assert client.get("/api/v1/admin/users?q=%25").json()["total"] == 0
    assert client.patch(path, json={"role": "user", "disabled": True}).status_code == 200
    with TestClient(app, base_url=ORIGIN, headers=HEADERS) as other:
        other.cookies.set(config.session_cookie, old_token)
        assert other.get("/api/v1/auth/session").json()["user"] is None
        with Session(engine) as db, db.begin():
            db.execute(delete(AuthRateLimit))
        challenge = request_code(other)
        code = sent[-1][1]
        wrong = "000000" if code != "000000" else "111111"
        assert verify(other, challenge, wrong).status_code == 400
        assert verify(other, challenge, code).status_code == 423
    assert client.patch(path, json={"role": "admin", "disabled": False}).status_code == 200
    with Session(engine) as db:
        assert db.get(AppUser, UUID(user["id"])).role == "admin"
        assert db.scalar(select(func.count()).select_from(AdminAudit)) == 2
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.user_id == UUID(user["id"]))
            )
            == 0
        )
    assert client.post(f"{path}/revoke-sessions").status_code == 200


def test_schedule_preview_version_conflicts_pause_and_manual_queue(auth):
    client, engine, config, _, app = auth
    login_admin(auth)
    preview = client.post(
        "/api/v1/admin/scripts/preview", json={"cron": "0 4 * * *", "timezone": "Europe/Paris"}
    )
    assert preview.status_code == 200 and len(preview.json()["upcoming"]) == 3
    body = {"cron": "0 5 * * 1", "timezone": "UTC", "enabled": False, "revision": 1}
    assert client.patch("/api/v1/admin/scripts/lol-catalog", json=body).status_code == 200
    assert client.patch("/api/v1/admin/scripts/lol-catalog", json=body).status_code == 409
    assert (
        client.post(
            "/api/v1/admin/scripts/preview", json={"cron": "0 0 31 2 *", "timezone": "UTC"}
        ).status_code
        == 422
    )
    token = client.cookies[config.session_cookie]

    def launch(_):
        with TestClient(app, base_url=ORIGIN, headers=HEADERS) as other:
            other.cookies.set(config.session_cookie, token)
            return other.post("/api/v1/admin/scripts/lol-catalog/run").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(launch, range(2))) == [202, 409]
    data = client.get("/api/v1/admin/scripts").json()
    catalog = next(row for row in data["items"] if row["id"] == "lol-catalog")
    assert catalog["nextRunAt"] is None and catalog["activeRun"]["status"] == "queued"
    with Session(engine) as db, db.begin():
        assert db.scalar(select(func.count()).select_from(ScriptRun)) == 1
        db.get(WorkerStatus, 1).seen_at = datetime.now(UTC) - timedelta(minutes=3)
    assert not client.get("/api/v1/admin/scripts").json()["worker"]["online"]
    assert client.post("/api/v1/admin/scripts/oracle-latest/run").status_code == 409
    assert client.post("/api/v1/admin/scripts/arbitrary-shell/run").status_code == 404


def test_administration_database_privileges(database):
    engine, _ = database
    for statement in [
        "UPDATE app_users SET role = 'user', disabled = false WHERE false",
        "UPDATE script_schedules SET cron = '0 4 * * *' WHERE false",
        "SELECT * FROM script_runs",
        "SELECT * FROM worker_status",
    ]:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL ROLE metiquo_api"))
            conn.execute(text(statement))


def test_admin_queue_and_reads_work_with_restricted_api_role(auth):
    client, engine, config, _, _ = auth
    login_admin(auth)
    settings = Settings(
        database_url=engine.url.set(username="metiquo_api", password="test-api").render_as_string(
            hide_password=False
        )
    )
    with TestClient(create_app(settings, config), base_url=ORIGIN, headers=HEADERS) as restricted:
        restricted.cookies.set(config.session_cookie, client.cookies[config.session_cookie])
        assert restricted.get("/api/v1/admin/users").status_code == 200
        assert restricted.get("/api/v1/admin/scripts").status_code == 200
        assert restricted.post("/api/v1/admin/scripts/lol-catalog/run").status_code == 202
    for role, statement in [
        ("metiquo_api", "UPDATE script_runs SET status='succeeded' WHERE false"),
        ("metiquo_api", "UPDATE worker_status SET seen_at=now() WHERE false"),
        ("metiquo_worker", "SELECT * FROM app_users"),
        ("metiquo_worker", "SELECT * FROM admin_audit"),
    ]:
        with pytest.raises(ProgrammingError), engine.begin() as conn:
            conn.execute(text(f"SET LOCAL ROLE {role}"))
            conn.execute(text(statement))
