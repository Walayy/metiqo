"""Les données privées exigent la session Owner et les cookies restent hors JSON."""

import asyncio

import pytest
from alembic import command
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

from metiquo.api.app import create_app
from metiquo.auth.service import OwnerAuthService
from metiquo.config import AuthMode
from tests.integration.test_entity_aliases import _seed_teams
from tests.integration.test_migrations import alembic_config
from tests.integration.test_owner_sessions import FIXTURE_PASSWORD
from tests.integration.test_postgres_canonical_api import _settings


@pytest.mark.integration
def test_owner_login_cookie_protected_reads_and_logout(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = _settings(postgresql_url, "mock").model_copy(
        update={
            "auth_mode": AuthMode.OWNER,
            "app_public_origin": "https://localhost:3000",
        }
    )
    owner_id = OwnerAuthService(engine, settings).bootstrap("owner", FIXTURE_PASSWORD)
    app = create_app(settings=settings)

    async def exercise() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://localhost:3000",
            headers={"Origin": "https://localhost:3000", "X-Metiquo-CSRF": "1"},
        ) as client:
            assert (await client.get("/health")).status_code == 200
            assert (await client.get("/api/v1/opportunities")).status_code == 401
            assert (await client.get("/api/v1/auth/session")).json()["authenticated"] is False
            wrong = await client.post(
                "/api/v1/auth/login",
                json={"username": "owner", "password": "wrong-fixture-password"},
            )
            assert wrong.status_code == 401
            logged_in = await client.post(
                "/api/v1/auth/login", json={"username": "owner", "password": FIXTURE_PASSWORD}
            )
            assert logged_in.status_code == 200
            cookie = logged_in.headers["set-cookie"]
            assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
            assert "Path=/" in cookie and "Domain=" not in cookie
            assert FIXTURE_PASSWORD not in logged_in.text and "token" not in logged_in.text.lower()
            assert logged_in.json()["owner"]["id"] == str(owner_id)
            assert (await client.get("/api/v1/opportunities")).status_code == 200
            assert (await client.get("/api/v1/auth/session")).json()["authenticated"] is True
            assert (await client.post("/api/v1/auth/logout")).status_code == 204
            assert (await client.get("/api/v1/opportunities")).status_code == 401

    asyncio.run(exercise())
    with engine.connect() as connection:
        events = connection.execute(
            text("SELECT actor, action FROM ops.audit_events WHERE action = 'auth.login_succeeded'")
        ).all()
        assert [(row.actor, row.action) for row in events] == [
            (f"owner:{owner_id}", "auth.login_succeeded")
        ]
    engine.dispose()


@pytest.mark.integration
def test_owner_identity_overrides_client_supplied_audit_actor(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    team_id, _ = _seed_teams(engine)
    settings = _settings(postgresql_url, "real").model_copy(
        update={"auth_mode": AuthMode.OWNER, "app_public_origin": "https://localhost:3000"}
    )
    owner_id = OwnerAuthService(engine, settings).bootstrap("owner", FIXTURE_PASSWORD)
    app = create_app(settings=settings)

    async def exercise() -> str:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://localhost:3000",
            headers={"Origin": "https://localhost:3000", "X-Metiquo-CSRF": "1"},
        ) as client:
            logged_in = await client.post(
                "/api/v1/auth/login", json={"username": "owner", "password": FIXTURE_PASSWORD}
            )
            assert logged_in.status_code == 200
            created = await client.post(
                "/api/v1/admin/aliases",
                headers={"Idempotency-Key": "owner-alias-attribution"},
                json={
                    "provider": "fixture-provider",
                    "alias": "Owner approved alias",
                    "canonicalId": str(team_id),
                    "reviewer": "spoofed-reviewer",
                    "reason": "Attribution proof",
                },
            )
            assert created.status_code == 200, created.text
            return str(created.json()["data"]["aliasId"])

    alias_id = asyncio.run(exercise())
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT approved_by FROM core.entity_aliases WHERE id=:id"), {"id": alias_id}
            )
            == f"owner:{owner_id}"
        )
        actors = connection.scalars(
            text("SELECT actor FROM ops.audit_events WHERE target_id=:id"), {"id": alias_id}
        ).all()
        assert actors and set(actors) == {f"owner:{owner_id}"}
    engine.dispose()
