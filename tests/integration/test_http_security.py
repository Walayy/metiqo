"""Frontières HTTP testées contre l'API réelle et des compteurs PostgreSQL partagés."""

import asyncio
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from alembic import command
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

from metiquo.api.app import create_app
from metiquo.auth.rate_limit import HttpRateLimiter
from metiquo.auth.service import OwnerAuthService
from metiquo.config import AuthMode
from metiquo.foundation.time import FixedClock, UtcInstant
from tests.integration.test_job_queue import NOW
from tests.integration.test_migrations import alembic_config
from tests.integration.test_owner_sessions import FIXTURE_PASSWORD
from tests.integration.test_postgres_canonical_api import _settings

ORIGIN = "https://localhost:3000"
CSRF_HEADERS = {"Origin": ORIGIN, "X-Metiquo-CSRF": "1"}


@pytest.mark.integration
def test_csrf_cors_limits_validation_and_safe_errors(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = _settings(postgresql_url, "mock").model_copy(
        update={"auth_mode": AuthMode.OWNER, "app_public_origin": ORIGIN}
    )
    service = OwnerAuthService(engine, settings)
    service.bootstrap("owner", FIXTURE_PASSWORD)
    app = create_app(settings=settings)

    @app.get("/api/v1/security-fixture-error")
    def failure() -> None:
        raise RuntimeError("private-fixture-password=must-never-leak")

    async def exercise() -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
            payload = {"username": "owner", "password": FIXTURE_PASSWORD}
            for headers in (
                {},
                {"Origin": ORIGIN},
                {"X-Metiquo-CSRF": "1"},
                {**CSRF_HEADERS, "Origin": "null"},
                {**CSRF_HEADERS, "Origin": ORIGIN + ".attacker.test"},
                {**CSRF_HEADERS, "Sec-Fetch-Site": "cross-site"},
            ):
                refused = await client.post("/api/v1/auth/login", json=payload, headers=headers)
                assert refused.status_code == 403
                assert "set-cookie" not in refused.headers
            preflight = await client.options(
                "/api/v1/auth/login",
                headers={
                    "Origin": "https://attacker.test",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert preflight.status_code == 403
            assert "access-control-allow-origin" not in preflight.headers
            excessive = await client.post(
                "/api/v1/auth/login", content=b"x" * 65537, headers=CSRF_HEADERS
            )
            assert excessive.status_code == 413

            async def chunks() -> AsyncIterator[bytes]:
                yield b"x" * 40000
                yield b"y" * 40000

            streamed = await client.post(
                "/api/v1/auth/login", content=chunks(), headers=CSRF_HEADERS
            )
            assert streamed.status_code == 413
            malformed = await client.post(
                "/api/v1/auth/login",
                json={**payload, "unexpected": "private-input"},
                headers=CSRF_HEADERS,
            )
            assert malformed.status_code == 422 and "private-input" not in malformed.text
            login = await client.post("/api/v1/auth/login", json=payload, headers=CSRF_HEADERS)
            assert login.status_code == 200
            failure_response = await client.get("/api/v1/security-fixture-error")
            assert failure_response.status_code == 500
            assert failure_response.json()["code"] == "INTERNAL_ERROR"
            assert "private-fixture" not in failure_response.text
            assert failure_response.headers["x-content-type-options"] == "nosniff"
            assert failure_response.headers["x-frame-options"] == "DENY"
            assert "max-age=" in failure_response.headers["strict-transport-security"]
            assert failure_response.headers["cache-control"] == "no-store"
            for _ in range(3):
                assert (
                    await client.post(
                        "/api/v1/auth/login",
                        json={"username": "unknown", "password": "wrong"},
                        headers=CSRF_HEADERS,
                    )
                ).status_code == 401
            limited = await client.post("/api/v1/auth/login", json=payload, headers=CSRF_HEADERS)
            assert limited.status_code == 429
            assert int(limited.headers["retry-after"]) > 0
            assert (await client.get("/api/v1/opportunities")).status_code == 200
            assert (await client.post("/api/v1/auth/logout")).status_code == 403
            assert (
                await client.post("/api/v1/auth/logout", headers=CSRF_HEADERS)
            ).status_code == 204

    asyncio.run(exercise())
    metrics = app.state.api_metrics.snapshot()
    assert metrics.request_count == 19 and metrics.failure_count == 1
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM ops.http_rate_limits")) <= 3
    engine.dispose()


@pytest.mark.integration
def test_rate_limits_share_atomic_budgets_between_processes(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    first = HttpRateLimiter(engine, FixedClock(UtcInstant(NOW)))
    second = HttpRateLimiter(engine, FixedClock(UtcInstant(NOW)))
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = tuple(pool.map(lambda i: (first if i % 2 else second).check("login"), range(12)))
    assert outcomes.count(0) == 5
    restarted = HttpRateLimiter(engine, FixedClock(UtcInstant(NOW)))
    assert restarted.check("login") > 0
    future = HttpRateLimiter(engine, FixedClock(UtcInstant(NOW + timedelta(minutes=1))))
    assert future.check("login") == 0
    engine.dispose()
