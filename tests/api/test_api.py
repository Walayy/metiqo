"""Tests du squelette FastAPI et de ses frontières de disponibilité."""

import asyncio
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI
from httpx2 import ASGITransport, AsyncClient, Response

from metiquo.api.app import create_app
from metiquo.api.readiness import ReadinessCheck
from metiquo.config import Settings
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import FixedClock, UtcInstant


@dataclass
class StubReadinessProbe:
    result: ReadinessCheck
    calls: int = 0

    def check(self) -> ReadinessCheck:
        self.calls += 1
        return self.result


def build_test_settings() -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "mock",
            "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "odds_provider": "mock",
        }
    )


def get(app: FastAPI, path: str) -> Response:
    async def send_request() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(send_request())


def test_health_does_not_probe_external_dependency() -> None:
    probe = StubReadinessProbe(ReadinessCheck(available=False))
    app = create_app(settings=build_test_settings(), readiness_probe=probe)

    response = get(app, "/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert probe.calls == 0


def test_ready_succeeds_when_database_and_migrations_are_ready() -> None:
    probe = StubReadinessProbe(ReadinessCheck(available=True))
    app = create_app(settings=build_test_settings(), readiness_probe=probe)

    response = get(app, "/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {"database": {"status": "available", "reasonCode": None}},
    }


def test_ready_fails_when_database_is_unavailable() -> None:
    probe = StubReadinessProbe(ReadinessCheck(available=False, reason_code="DATABASE_UNREACHABLE"))
    app = create_app(settings=build_test_settings(), readiness_probe=probe)

    response = get(app, "/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {
            "database": {
                "status": "unavailable",
                "reasonCode": "DATABASE_UNREACHABLE",
            }
        },
    }


def test_system_status_exposes_mode_and_injected_utc_time() -> None:
    probe = StubReadinessProbe(ReadinessCheck(available=True))
    clock = FixedClock(UtcInstant.parse("2026-09-04T18:00:00Z"))
    app = create_app(settings=build_test_settings(), readiness_probe=probe, clock=clock)

    response = get(app, "/api/v1/system/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "apiVersion": "0.1.0",
        "dataMode": "mock",
        "generatedAt": "2026-09-04T18:00:00Z",
        "dependencies": {"database": {"status": "available", "reasonCode": None}},
    }


def test_http_errors_use_problem_details() -> None:
    app = create_app(
        settings=build_test_settings(),
        readiness_probe=StubReadinessProbe(ReadinessCheck(available=True)),
    )

    response = get(app, "/missing")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Ressource introuvable",
        "status": 404,
        "detail": "Ressource introuvable",
        "instance": "/missing",
        "code": "HTTP_404",
        "context": {},
    }


def test_business_errors_use_problem_details() -> None:
    app = create_app(
        settings=build_test_settings(),
        readiness_probe=StubReadinessProbe(ReadinessCheck(available=True)),
    )
    test_router = APIRouter()

    @test_router.get("/test-error")
    def raise_business_error() -> None:
        raise BusinessError(
            ErrorCode.CONFLICT,
            "État incompatible",
            context={"resource": "test"},
        )

    app.include_router(test_router)

    response = get(app, "/test-error")

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "CONFLICT"
    assert response.json()["context"] == {"resource": "test"}


def test_validation_errors_use_problem_details_without_echoing_input() -> None:
    app = create_app(
        settings=build_test_settings(),
        readiness_probe=StubReadinessProbe(ReadinessCheck(available=True)),
    )
    test_router = APIRouter()

    @test_router.get("/validated")
    def validated(limit: int) -> dict[str, int]:
        return {"limit": limit}

    app.include_router(test_router)
    invalid_value = "sensitive-invalid-value"

    response = get(app, f"/validated?limit={invalid_value}")

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["title"] == "Requête invalide"
    assert invalid_value not in response.text
